import os
import time
import threading
import configparser
import snap7
from snap7 import util
from  gateway.plc import log


class PLCClient:
    """
    作者：尉
    创建日期：2025/12/08
    PLC 客户端类，支持多线程安全访问（通过互斥锁实现）
    """

    connect_lock = threading.RLock()  # 单PLC链接建立 操作的互斥锁，避免并发链接报错

    def __init__(self, config_path: str, logger: log.AppLogger, heart: bool = False) -> None:
        """
        参数
        config_path:str 配置文件相对路径
        logger:log.AppLogger 日志存储
        heart = False 是否配置PLC心跳(一个PLC只需要开一个)
        """
        self.logger = logger
        
        self.config_path = config_path
        self.client = None
        self.connected = False
        self.monitor_thread = None
        self.stop_monitor = False

        # -------------------------- 关键优化1：初始化互斥锁 --------------------------
        self.client_lock = threading.RLock()  # 保护 client 操作的互斥锁
        self.connect_timeout = 5  # 连接等待超时时间（秒）
        self.lock_timeout = 3  # 锁获取超时时间（秒，防止死锁）

        # 和PLC通讯的心跳开关，一个PLC开一个心跳即可
        self.heart = heart
        self.heart_thread = None
        self.stop_heart = False

        # 加载配置
        self.load_config()

        # 初始化连接
        self.connect()

        # 启动监控线程
        self.start_monitor()

        # 心跳线程
        if heart:
            self.start_heart()


    def load_config(self):
        """从配置文件加载 PLC 连接参数（无修改）"""
        try:
            if not os.path.exists(self.config_path):
                raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

            config = configparser.ConfigParser()
            config.read(self.config_path, encoding='utf-8')

            self.plc_ip = config.get('PLC', 'ip', fallback='192.168.0.1')
            self.plc_rack = config.getint('PLC', 'rack', fallback=0)
            self.plc_slot = config.getint('PLC', 'slot', fallback=1)
            self.plc_port = config.getint('PLC', 'port', fallback=102)
            self.check_interval = config.getint('MONITOR', 'check_interval', fallback=2)
            self.db_number = config.getint('MONITOR', 'db_number', fallback=1)
            self.byte_offset = config.getint('MONITOR', 'byte_offset', fallback=1)
            self.bit_index = config.getint('MONITOR', 'bit_index', fallback=0)

            self.logger.info(f"加载 PLC 配置: IP={self.plc_ip}, RACK={self.plc_rack}, "
                        f"SLOT={self.plc_slot}, PORT={self.plc_port}")
            self.logger.info(f"健康检查地址为：DB{self.db_number},BYTE{self.byte_offset},BIT{self.bit_index}")

        except Exception as e:
            self.logger.error(f"加载配置文件失败: {e}")
            raise

    def _log_execution_time(self, func_name:str, elapsed, precision=4):
        """
        记录执行时间
            统计读写超时时间，便于查找网络问题
            """
        self.logger.debug(f"函数 {func_name} 执行时间: {elapsed:.{precision}f} 秒")
        if elapsed > 0.2:
            self.logger.warning(f"函数 {func_name} 执行时间过长: {elapsed:.{precision}f} 秒")


    # -------------------------- 关键优化2：连接方法加锁 --------------------------
    def connect(self):
        """创建并建立 PLC 连接（加锁避免多线程重复连接）"""
        # 尝试获取锁，超时则返回失败
        if not PLCClient.connect_lock.acquire(timeout=3):
            self.logger.error("获取连接锁超时，连接失败!")
            return False

        try:
            # 已连接则直接返回
            if self.connected and self.client:
                self.logger.warning("PLC 已处于连接状态，无需重复连接")
                return True
            self.logger.warning("...尝试重连PLC链接中...")
            # 创建客户端实例
            self.client = snap7.client.Client()
            self.client.connect(self.plc_ip, self.plc_rack, self.plc_slot, self.plc_port)

            if self.client.get_connected():
                self.connected = True
                pdu_size = self.client.get_pdu_length()
                self.logger.info(f"成功连接到 PLC: {self.plc_ip} 协商PDU大小：{pdu_size}")
                return True
            else:
                self.connected = False
                self.logger.error(f"连接到 PLC 失败: {self.plc_ip}")
                return False

        except Exception as e:
            self.connected = False
            self.logger.error(f"连接 PLC 时发生异常: {e}")
            return False
        finally:
            # 无论成功失败，都释放锁
            PLCClient.connect_lock.release()

    # -------------------------- 关键优化3：断开连接加锁 --------------------------
    def disconnect(self):
        """断开 PLC 连接（加锁保证资源安全释放）"""
        if not PLCClient.connect_lock.acquire(timeout=3):
            self.logger.error("获取断开锁超时，释放资源失败")
            return

        try:
            if self.client:
                self.client.disconnect()
                self.client.destroy()
                self.client = None
                self.connected = False
                self.logger.info("已断开 PLC 连接")
        except Exception as e:
            self.logger.error(f"断开 PLC 连接时发生异常: {e}")
        finally:
            PLCClient.connect_lock.release()

    # -------------------------- 关键优化4：连接检查加锁 --------------------------
    def check_connection(self):
        if not self.client_lock.acquire(timeout=self.lock_timeout):
            self.logger.error("获取连接检查锁超时")
            return False

        try:
            if not self.client:
                was_connected = self.connected
                self.connected = False
                if was_connected:
                    self.logger.error("PLC 客户端未初始化，连接已断开")
                return False

            # 尝试读取一个字节来检查连接状态
            self.client.db_read(self.db_number, self.byte_offset, 1)

            # 连接正常
            if not self.connected:
                self.connected = True
                self.logger.info("PLC 连接已恢复")
            else:
                self.logger.info("周期性监测PLC连接状态：正常")
            return True

        except Exception as e:
            was_connected = self.connected
            self.connected = False

            # 只有状态发生变化时才记录日志，避免重复日志
            if was_connected:
                self.logger.error(f"PLC 连接异常: {e}")
            return False

        finally:
            self.client_lock.release()


    def reconnect(self):
        """尝试重新连接 PLC（无修改，依赖 connect 加锁）"""

        self.logger.warning("尝试重新连接 PLC...")
        self.disconnect()
        time.sleep(0.5)
        return self.connect()

    def monitor_task(self):
        """监控任务（无修改，依赖 check_connection 加锁）"""
        self.logger.info("启动 PLC 连接监控任务")
        while not self.stop_monitor:
            try:
                if not self.check_connection():
                    self.reconnect()
                time.sleep(self.check_interval)
            except Exception as e:
                self.logger.error(f"链接监控任务发生异常: {e}")
                time.sleep(self.check_interval)

    def start_monitor(self):
        """启动监控线程（无修改）"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.logger.warning("链接健康监控线程已在运行")
            return
        self.stop_monitor = False
        self.monitor_thread = threading.Thread(target=self.monitor_task)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        self.logger.info("PLC 连接健康监控线程已启动")



    def stop_monitor_thread(self):
        """停止监控线程（无修改）"""
        self.stop_monitor = True
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        self.logger.info("PLC 连接监控已停止")



    def heart_task(self):
        """
                写给 PLC的通讯心跳
                原则上一个PLC只需要一个链接去写，即只有一个链接的 self.heart 开关是打开的
        """
        self.logger.info("启动 PLC心跳 任务")
        try:
            while not self.stop_heart:
                try:
                    time.sleep(self.check_interval)
                    if not (self.connected and self.client):
                        self.logger.warning(f"链接异常，跳过心跳执行读写！")
                    if self.writeDB_NegateBit(self.db_number, self.byte_offset, self.bit_index):
                        self.logger.info(f"写给PLC心跳信号 成功")
                    else:
                        self.logger.error(f"错误：写给PLC心跳信号 失败！")
                except Exception as e:
                    self.logger.error(f"心跳读写任务发生异常: {e}")
        except Exception as e:
            self.logger.error(f"！！！！！- 心跳线程异常退出 - ！！！！！: {e}")

    def start_heart(self):
        """启动监控线程（无修改）"""
        if self.heart_thread and self.heart_thread.is_alive():
            self.logger.warning("PLC 心跳任务已在运行")
            return
        self.stop_heart = False
        self.heart_thread = threading.Thread(target=self.heart_task)
        self.heart_thread.daemon = True
        self.heart_thread.start()
        self.logger.info("PLC 心跳任务已启动")

    def stop_heart_thread(self):
        """停止监控线程（无修改）"""
        self.stop_heart = True
        if self.heart_thread and self.heart_thread.is_alive():
            self.heart_thread.join(timeout=5)
        self.logger.info("PLC 心跳任务已停止")



    def __del__(self):
        """析构函数（无修改）"""
        self.stop_monitor_thread()
        self.stop_heart_thread()
        self.disconnect()

    # -------------------------- 关键优化5：等待连接就绪（提升可用性） --------------------------
    def wait_for_connection(self, timeout=2):
        """等待 PLC 连接就绪（避免未连接时直接抛错）"""
        start_time = time.time()
        while True:
            # 超时判断
            if timeout and (time.time() - start_time) > timeout:
                self.logger.error(f"等待 PLC 连接超时（{timeout} 秒）")
                return False
            # 连接就绪则返回
            if self.connected and self.client:
                return True
            # 未就绪则等待
            self.logger.warning("等待 PLC 连接就绪...")
            time.sleep(1)


    # ------------------------   boolen （加锁+bug修复） ------------------------
    def readDB_Bit(self, db_num: int, byte_offset: int, bit_offset: int):
        start_time = time.perf_counter()
        # 等待连接就绪（超时 5 秒）
        if not self.wait_for_connection(timeout=self.connect_timeout):
            self.logger.error(f"读取DB{db_num}.DBX{byte_offset}.{bit_offset}失败：PLC 未连接")
            return False, None

        # 获取锁，超时则返回失败
        if not self.client_lock.acquire(timeout=self.lock_timeout):
            self.logger.error(f"读取DB{db_num}.DBX{byte_offset}.{bit_offset}失败：获取锁超时")
            return False, None

        try:
            buffer = self.client.db_read(db_num, byte_offset, 1)
            value = util.get_bool(buffer, 0, bit_offset)
            self.logger.debug(f"成功读取DB{db_num}.DBX{byte_offset}.{bit_offset}值: {value}")
            return True, value
        except Exception as e:
            self.logger.error(f"读取DB{db_num}.DBX{byte_offset}.{bit_offset}值时出现异常错误: {e}")
            return False, None
        finally:
            self.client_lock.release()
            # 记录执行时间
            elapsed = time.perf_counter() - start_time
            self._log_execution_time("readDB_Bit", elapsed)


    def writeDB_Bit(self, db_num: int, byte_offset: int, bit_offset: int, value: bool):
        start_time = time.perf_counter()
        if not self.wait_for_connection(timeout=self.connect_timeout):
            self.logger.error(f"写入DB{db_num}.DBX{byte_offset}.{bit_offset}失败：PLC 未连接")
            return False

        if not self.client_lock.acquire(timeout=self.lock_timeout):
            self.logger.error(f"写入DB{db_num}.DBX{byte_offset}.{bit_offset}失败：获取锁超时")
            return False

        try:
            boolData = self.client.db_read(db_num, byte_offset, 1)
            util.set_bool(boolData, 0, bit_offset, value)
            self.client.db_write(db_num, byte_offset, boolData)
            self.logger.debug(f"成功写入DB{db_num}.DBX{byte_offset}.{bit_offset}值: {value}")
            return True
        except Exception as e:
            self.logger.error(f"写入DB{db_num}.DBX{byte_offset}.{bit_offset}值时出现异常错误: {e}")
            return False
        finally:
            self.client_lock.release()
            # 记录执行时间
            elapsed = time.perf_counter() - start_time
            self._log_execution_time("writeDB_Bit", elapsed)

    # -------------------------- bug修复1：移除多余的 self 参数 --------------------------
    def writeDB_SetBit(self, db_num: int, byte_offset: int, bit_offset: int):
        # 原代码：result = self.writeDB_Bit(self, ...) → 多传了 self，导致参数错误
        return self.writeDB_Bit(db_num, byte_offset, bit_offset, True)

    def writeDB_ResetBit(self, db_num: int, byte_offset: int, bit_offset: int):
        # 原代码：result = self.writeDB_Bit(self, ...) → 修复参数
        return self.writeDB_Bit(db_num, byte_offset, bit_offset, False)


    def writeDB_NegateBit(self, db_num: int, byte_offset: int, bit_offset: int):
        if not self.wait_for_connection(timeout=self.connect_timeout):
            self.logger.error(f"取反DB{db_num}.DBX{byte_offset}.{bit_offset}失败：PLC 未连接")
            return False

        try:
            # -------------------------- bug修复2：逻辑判断错误 --------------------------
            res, bitValue = self.readDB_Bit(db_num, byte_offset, bit_offset)
            # 原代码：if res: raise → 应该是 if not res（读取失败才抛错）
            if not res:
                raise Exception("bit位取反时原值读取失败")
            result = self.writeDB_Bit(db_num, byte_offset, bit_offset, not bitValue)
            self.logger.debug(f"成功取反DB{db_num}.DBX{byte_offset}.{bit_offset}值")
            return result
        except Exception as e:
            self.logger.error(f"取反 DB{db_num}.DBX{byte_offset}.{bit_offset}时出现异常错误: {e}")
            return False

    # ------------------------   int （加锁优化） ------------------------

    def readDB_Int(self, db_num: int, byte_offset: int):
        start_time = time.perf_counter()
        if not self.wait_for_connection(timeout=self.connect_timeout):
            self.logger.error(f"读取DB{db_num}.INT{byte_offset}失败：PLC 未连接")
            return False, None

        if not self.client_lock.acquire(timeout=self.lock_timeout):
            self.logger.error(f"读取DB{db_num}.INT{byte_offset}失败：获取锁超时")
            return False, None

        try:
            bufferData = self.client.db_read(db_num, byte_offset, 2)
            value = util.get_int(bufferData, 0)
            self.logger.debug(f"成功读取DB{db_num}.INT{byte_offset}值: {value}")
            return True, value
        except Exception as e:
            self.logger.error(f"读取DB{db_num}.INT{byte_offset}值时出现异常错误: {e}")
            return False, None
        finally:
            self.client_lock.release()
            # 记录执行时间
            elapsed = time.perf_counter() - start_time
            self._log_execution_time("readDB_Int", elapsed)

    def writeDB_Int(self, db_num: int, byte_offset: int, value: int):
        start_time = time.perf_counter()
        if not self.wait_for_connection(timeout=self.connect_timeout):
            self.logger.error(f"写入DB{db_num}.INT{byte_offset}失败：PLC 未连接")
            return False

        if not self.client_lock.acquire(timeout=self.lock_timeout):
            self.logger.error(f"写入DB{db_num}.INT{byte_offset}失败：获取锁超时")
            return False

        try:
            bufferData = bytearray(2)
            util.set_int(bufferData, 0, value)
            self.client.db_write(db_num, byte_offset, bufferData)
            self.logger.debug(f"成功写入DB{db_num}.INT{byte_offset}值: {value}")
            return True
        except Exception as e:
            self.logger.error(f"写入DB{db_num}.INT{byte_offset}值{value}时出现异常错误: {e}")
            return False
        finally:
            self.client_lock.release()
            # 记录执行时间
            elapsed = time.perf_counter() - start_time
            self._log_execution_time("writeDB_Int", elapsed)

    # ------------------------   DInt/Real/LReal/String （统一加锁优化） ------------------------
    # 以下方法仅添加“锁机制”和“等待连接就绪”，逻辑与原代码一致，不再重复标注
    def readDB_DInt(self, db_num: int, byte_offset: int):
        start_time = time.perf_counter()
        if not self.wait_for_connection(timeout=self.connect_timeout):
            self.logger.error(f"读取DB{db_num}.DINT{byte_offset}失败：PLC 未连接")
            return False, None

        if not self.client_lock.acquire(timeout=self.lock_timeout):
            self.logger.error(f"读取DB{db_num}.DINT{byte_offset}失败：获取锁超时")
            return False, None

        try:
            bufferData = self.client.db_read(db_num, byte_offset, 4)
            value = util.get_dint(bufferData, 0)
            self.logger.debug(f"成功读取DB{db_num}.DINT{byte_offset}值: {value}")
            return True, value
        except Exception as e:
            self.logger.error(f"读取DB{db_num}.DINT{byte_offset}值时出现异常错误: {e}")
            return False, None
        finally:
            self.client_lock.release()
            # 记录执行时间
            elapsed = time.perf_counter() - start_time
            self._log_execution_time("readDB_DInt", elapsed)


    def writeDB_DInt(self, db_num: int, byte_offset: int, value: int):
        start_time = time.perf_counter()
        if not self.wait_for_connection(timeout=self.connect_timeout):
            self.logger.error(f"写入DB{db_num}.DINT{byte_offset}失败：PLC 未连接")
            return False

        if not self.client_lock.acquire(timeout=self.lock_timeout):
            self.logger.error(f"写入DB{db_num}.DINT{byte_offset}失败：获取锁超时")
            return False

        try:
            bufferData = bytearray(4)
            util.set_dint(bufferData, 0, value)
            self.client.db_write(db_num, byte_offset, bufferData)
            self.logger.debug(f"成功写入DB{db_num}.DINT{byte_offset}值: {value}")
            return True
        except Exception as e:
            self.logger.error(f"写入DB{db_num}.DINT{byte_offset}值时出现异常错误: {e}")
            return False
        finally:
            self.client_lock.release()
            # 记录执行时间
            elapsed = time.perf_counter() - start_time
            self._log_execution_time("writeDB_DInt", elapsed)


    def readDB_Real(self, db_num: int, byte_offset: int):
        start_time = time.perf_counter()
        if not self.wait_for_connection(timeout=self.connect_timeout):
            self.logger.error(f"读取DB{db_num}.REAL{byte_offset}失败：PLC 未连接")
            return False, None

        if not self.client_lock.acquire(timeout=self.lock_timeout):
            self.logger.error(f"读取DB{db_num}.REAL{byte_offset}失败：获取锁超时")
            return False, None

        try:
            bufferData = self.client.db_read(db_num, byte_offset, 4)
            value = util.get_real(bufferData, 0)
            self.logger.debug(f"成功读取DB{db_num}.REAL{byte_offset}值: {value}")
            return True, value
        except Exception as e:
            self.logger.error(f"读取DB{db_num}.REAL{byte_offset}值时出现异常错误: {e}")
            return False, None
        finally:
            self.client_lock.release()
            # 记录执行时间
            elapsed = time.perf_counter() - start_time
            self._log_execution_time("readDB_Real", elapsed)


    def writeDB_Real(self, db_num: int, byte_offset: int, value: float):
        start_time = time.perf_counter()
        if not self.wait_for_connection(timeout=self.connect_timeout):
            self.logger.error(f"写入DB{db_num}.REAL{byte_offset}失败：PLC 未连接")
            return False

        if not self.client_lock.acquire(timeout=self.lock_timeout):
            self.logger.error(f"写入DB{db_num}.REAL{byte_offset}失败：获取锁超时")
            return False

        try:
            bufferData = bytearray(4)
            util.set_real(bufferData, 0, value)
            self.client.db_write(db_num, byte_offset, bufferData)
            self.logger.debug(f"成功写入DB{db_num}.REAL{byte_offset}值: {value}")
            return True
        except Exception as e:
            self.logger.error(f"写入DB{db_num}.REAL{byte_offset}值时出现异常错误: {e}")
            return False
        finally:
            self.client_lock.release()
            # 记录执行时间
            elapsed = time.perf_counter() - start_time
            self._log_execution_time("writeDB_Real", elapsed)


    def readDB_LReal(self, db_num: int, byte_offset: int):
        start_time = time.perf_counter()
        if not self.wait_for_connection(timeout=self.connect_timeout):
            self.logger.error(f"读取DB{db_num}.LREAL{byte_offset}失败：PLC 未连接")
            return False, None

        if not self.client_lock.acquire(timeout=self.lock_timeout):
            self.logger.error(f"读取DB{db_num}.LREAL{byte_offset}失败：获取锁超时")
            return False, None

        try:
            bufferData = self.client.db_read(db_num, byte_offset, 8)
            value = util.get_lreal(bufferData, 0)
            self.logger.debug(f"成功读取DB{db_num}.LREAL{byte_offset}值: {value}")
            return True, value
        except Exception as e:
            self.logger.error(f"读取DB{db_num}.LREAL{byte_offset}值时出现异常错误: {e}")
            return False, None
        finally:
            self.client_lock.release()
            # 记录执行时间
            elapsed = time.perf_counter() - start_time
            self._log_execution_time("readDB_LReal", elapsed)


    def writeDB_LReal(self, db_num: int, byte_offset: int, value: float):
        start_time = time.perf_counter()
        if not self.wait_for_connection(timeout=self.connect_timeout):
            self.logger.error(f"写入DB{db_num}.LREAL{byte_offset}失败：PLC 未连接")
            return False

        if not self.client_lock.acquire(timeout=self.lock_timeout):
            self.logger.error(f"写入DB{db_num}.LREAL{byte_offset}失败：获取锁超时")
            return False

        try:
            bufferData = bytearray(8)
            util.set_lreal(bufferData, 0, value)
            self.client.db_write(db_num, byte_offset, bufferData)
            self.logger.debug(f"成功写入DB{db_num}.LREAL{byte_offset}值: {value}")
            return True
        except Exception as e:
            self.logger.error(f"写入DB{db_num}.LREAL{byte_offset}值时出现异常错误: {e}")
            return False
        finally:
            self.client_lock.release()
            # 记录执行时间
            elapsed = time.perf_counter() - start_time
            self._log_execution_time("writeDB_LReal", elapsed)


    def readDB_String(self, db_num: int, byte_offset: int, size: int, encoding='gbk'):
        start_time = time.perf_counter()
        if not self.wait_for_connection(timeout=self.connect_timeout):
            self.logger.error(f"读取DB{db_num}.String{byte_offset}.{size}失败：PLC 未连接")
            return False, None

        if not self.client_lock.acquire(timeout=self.lock_timeout):
            self.logger.error(f"读取DB{db_num}.String{byte_offset}.{size}失败：获取锁超时")
            return False, None

        """
                读取字符串，支持中文

                参数:
                    db_num: DB块编号
                    byte_offset: 字节偏移量
                    size: 字符串长度
                    encoding: 字符串编码格式，默认为gbk

                返回:
                    (成功状态, 字符串内容) 或 (失败状态, None)
                """
        try:
            # 读取字符串数据（包括2字节的头部）
            buffer = self.client.db_read(db_num, byte_offset, size + 2 )

            # 获取实际字符串长度（第二个字节）
            actual_length = buffer[1]

            # 提取字符串数据（从第2字节开始，取实际长度）
            string_bytes = buffer[2:2 + actual_length]

            # 解码字符串
            try:
                # 尝试使用指定编码解码
                string_value = string_bytes.decode(encoding)
                self.logger.debug(f"成功读取DB{db_num}.String{byte_offset}.{size}值: {string_value}")
                return True, string_value
            except UnicodeDecodeError:
                """
                如果编码失败，尝试去掉末尾一个字节重新编码，解决 尾部半个中文字符的问题
                """
                try:
                    string_value = string_bytes[:-1].decode(encoding)
                    self.logger.debug(f"成功读取DB{db_num}.String{byte_offset}.{size}值: {string_value}")
                    return True, string_value
                except UnicodeDecodeError as e:
                    self.logger.error(f"无法解码字符串: {e}")
                    return False, None

        except Exception as e:
            self.logger.error(f"读取DB{db_num}.String{byte_offset}.{size}值时出现异常错误: {e}")
            return False, None

        finally:
            self.client_lock.release()
            # 记录执行时间
            elapsed = time.perf_counter() - start_time
            self._log_execution_time("readDB_String", elapsed)


    def writeDB_String(self, db_num: int, byte_offset: int, size: int, string_value: str):
        start_time = time.perf_counter()
        if not self.wait_for_connection(timeout=self.connect_timeout):
            self.logger.error(f"写入DB{db_num}.String{byte_offset}.{size}失败：PLC 未连接")
            return False

        if not self.client_lock.acquire(timeout=self.lock_timeout):
            self.logger.error(f"写入DB{db_num}.String{byte_offset}.{size}失败：获取锁超时")
            return False

        """
               向PLC写入字符串（支持中文）

               参数:
                   db_num: DB块编号
                   byte_offset: 字节偏移量
                   string_value: 要写入的字符串
                   encoding: 编码格式，默认为gbk
                   size: 字符串最大长度（包括头部）

               返回:
                   (成功状态, 错误信息)
               """
        try:
            encoding = 'gbk'
            # 将字符串编码为字节
            try:
                string_bytes = string_value.encode(encoding)
            except UnicodeEncodeError as e:
                self.logger.error(f"写入字符串{string_value}时编码出错: {e}")
                return False

            # 检查长度是否超出限制
            max_content_length = size
            if len(string_bytes) > max_content_length :
                # 截断字符串
                truncated_bytes = string_bytes[:max_content_length]
                try:
                    # 尝试解码截断后的字节，确保不会在字符中间截断
                    truncated_str = truncated_bytes.decode(encoding)
                    string_bytes = truncated_str.encode(encoding)
                    self.logger.warning(f"字符串长度超出限制，已截断为: {truncated_str}")
                except:
                    # 如果解码失败，可能出现窃取半个中文字符的问题，尝试去掉末尾字符重试
                    truncated_str = truncated_bytes[:-1].decode(encoding)
                    string_bytes = truncated_str.encode(encoding)
                    self.logger.warning(f"字符串长度超出限制，已截断为: {truncated_str}")

            # 创建PLC字符串格式
            # 西门子字符串格式:
            # 第一个字节: 最大长度 (max_length)
            # 第二个字节: 实际长度 (actual_length)
            # 接着是字符串数据，剩余部分填充0
            buffer = bytearray(size+2)
            buffer[0] = size  # 最大长度
            buffer[1] = len(string_bytes)  # 实际长度

            # 复制字符串数据
            buffer[2:2 + len(string_bytes)] = string_bytes

            # 剩余部分填充0（可选，但建议填充以确保一致性）
            for i in range(2 + len(string_bytes), size+2):
                buffer[i] = 0

            # 写入PLC
            self.client.db_write(db_num, byte_offset, buffer)
            self.logger.debug(f"成功写入字符串到DB{db_num}.{byte_offset}.{size}: {string_value} (编码: {encoding})")
            return True

        except Exception as e:
            self.logger.error(f"写入DB{db_num}.String{byte_offset}.{size}值时出现异常错误: {e}")
            return False
        finally:
            self.client_lock.release()
            # 记录执行时间
            elapsed = time.perf_counter() - start_time
            self._log_execution_time("writeDB_String", elapsed)


 # ------------------------   批量读取字节码 （加锁优化） ------------------------
    def readDB_Byte(self, db_num: int, byte_offset: int, size: int):
        start_time = time.perf_counter()
        if not self.wait_for_connection(timeout=self.connect_timeout):
            self.logger.error(f"读取DB{db_num}.Byte{byte_offset}.{size}失败：PLC 未连接")
            return False, None

        if not self.client_lock.acquire(timeout=self.lock_timeout):
            self.logger.error(f"读取DB{db_num}.Byte{byte_offset}.{size}失败：获取锁超时")
            return False, None

        try:
            bufferData = self.client.db_read(db_num, byte_offset, size)
            value = bufferData
            self.logger.debug(f"成功读取DB{db_num}.Byte{byte_offset}.{size}值: {value}")
            return True, value
        except Exception as e:
            self.logger.error(f"读取DB{db_num}.Byte{byte_offset}.{size}值时出现异常错误: {e}")
            return False, None
        finally:
            self.client_lock.release()
            # 记录执行时间
            elapsed = time.perf_counter() - start_time
            self._log_execution_time("readDB_Byte", elapsed)

    # ------------------------   批量写入字节码 （加锁优化） ------------------------
    def writeDB_Byte(self, db_num: int, byte_offset: int, write_data: bytearray):
        start_time = time.perf_counter()
        if not self.wait_for_connection(timeout=self.connect_timeout):
            self.logger.error(f"写入DB{db_num}.Byte{byte_offset}.{len(write_data)}失败：PLC 未连接")
            return False, None

        if not self.client_lock.acquire(timeout=self.lock_timeout):
            self.logger.error(f"写入DB{db_num}.Byte{byte_offset}.{len(write_data)}失败：获取锁超时")
            return False, None

        try:
            result = self.client.db_write(db_num, byte_offset, write_data)
            self.logger.debug(f"成功写入DB{db_num}.Byte{byte_offset}.{len(write_data)}写入结果代码: {result}")
            return True
        except Exception as e:
            self.logger.error(f"写入DB{db_num}.Byte{byte_offset}.{len(write_data)}值时出现异常错误: {e}")
            return False, None
        finally:
            self.client_lock.release()
            # 记录执行时间
            elapsed = time.perf_counter() - start_time
            self._log_execution_time("writeDB_Byte", elapsed)


# -------------------------- 多线程测试示例 --------------------------
if __name__ == '__main__':
    def thread_task1():
        """线程1：读取 bool 量"""
        while True:
            plc_client.readDB_Bit(10108, 2500, 0)
            time.sleep(1)  # 模拟高频读取

    def thread_task2():
        """线程2：读取 int 量"""
        while True:
            plc_client.readDB_Int(10108, 2502)
            time.sleep(1)

    def thread_task3():
        """线程3：写入 string 量"""
        while True:
            plc_client.writeDB_String(10108, 32, 17, str(time.time())[:10])
            time.sleep(1)

    try:
        logger = log.AppLogger('PLC')
        plc_client = PLCClient('../config/PLC1_CONF.ini', logger, True)

        # 创建 3 个并发线程
        threads = [
            threading.Thread(target=thread_task1, daemon=True),
            threading.Thread(target=thread_task2, daemon=True),
            threading.Thread(target=thread_task3, daemon=True)
        ]

        # 启动所有线程
        for t in threads:
            t.start()
            print(f"线程 {t.name} 启动成功")

        print("程序开始运行，按 Ctrl+C 停止")
        # 主线程等待
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("程序被用户中断")
    except Exception as e:
        print(f"程序运行异常: {e}")
    finally:
        if 'plc_client' in locals():
            plc_client.stop_monitor_thread()
            plc_client.stop_heart_thread()
            plc_client.disconnect()