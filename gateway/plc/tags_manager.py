"""
作者：尉
创建日期：2025/12/18
"""

#import snap7
from gateway.plc.client import PLCClient
from gateway.plc.log import AppLogger
from gateway.plc.monitor import VariableMonitor
#from snap7 import types
from snap7.util import *
from typing import Dict, List, Any, Optional
#import struct
import threading
import time
import logging

class DBPLCTag():
    """DB区域PLC标签的封装类"""

    def __init__(self,
                 logger: AppLogger,
                 name: str,
                 tagpath: str,
                 db_number: int,
                 start_offset: int,
                 size: int,
                 data_type: str,
                 bit_index: Optional[int] = None,
                 plc: str = "",
                 group: str = "",
                 config_monitor : int = 0,
                 default_value = None,
                 description: str = ""):
        """
        初始化DB区域PLC标签
        :param plc: 归属PLC名
        :param group: 标签组，后面可以作为 task 任务组，把任务执行的一组标签放在同一个组里
        :param tagpath:  标签完整路径，包含name，全局应该唯一，可作为标签id
        :param name: 标签名称
        :param db_number: DB块号
        :param start_offset: 起始偏移量
        :param size: 数据大小 (字节数)
        :param data_type: 数据类型 ('bool', 'int', 'dint', 'real', 'string'等)
        :param bit_index: 位索引 (仅对bool类型有效)
        :param description: 标签描述
        :param default_value: 初始默认值
        :param config_monitor: 是否配置监听，0-不配置，1-配置
        :param logger: 日志文件
        :param monitor：值变化监控器
        """

        self.plc = plc
        self.group = group
        self.name = name
        self.tagpath = tagpath
        self.db_number = db_number
        self.start_offset = start_offset
        self.size = size
        self.data_type = data_type
        self.bit_index = bit_index
        self.description = description
        self.default_value = default_value
        self.config_monitor = config_monitor

        # 组合监听属性
        self.monitor = VariableMonitor(tagpath, logger, initial_value=default_value)
        if config_monitor:
            self.monitor.start_consumer()

        # 当前值和待写入值
        self._value = None
        self._pending_write_value = None
        self._last_update_time = 0
        self._value_lock = threading.RLock()



    @property
    def value(self) -> Any:
        """获取标签当前值"""
        with self._value_lock:
            return self._value

    @value.setter
    def value(self, new_value: Any):
        """设置标签值，但不立即写入PLC"""
        with self._value_lock:
            self._value = new_value
            self._last_update_time = time.time()
            self.monitor.value = new_value

    def set_pending_write_value(self, value: Any):
        """设置待写入值"""
        with self._value_lock:
            self._pending_write_value = value

    def get_pending_write_value(self) -> Any:
        """获取待写入值"""
        with self._value_lock:
            return self._pending_write_value

    def clear_pending_write_value(self):
        """清除待写入值"""
        with self._value_lock:
            self._pending_write_value = None

    def has_pending_write(self) -> bool:
        """检查是否有待写入值"""
        with self._value_lock:
            return self._pending_write_value is not None

    def get_address_info(self) -> Dict[str, Any]:
        """获取标签地址信息"""
        return {
            'db_number': self.db_number,
            'start_offset': self.start_offset,
            'size': self.size,
            'data_type': self.data_type,
            'bit_index': self.bit_index
        }

    def __str__(self):
        return f"DBPLCTag(tagpath={self.tagpath}, value={self.value}, type={self.data_type})"


class DBPLCTagManager:
    """DB区域PLC标签管理器（静态类）"""

    # 单例实例
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(DBPLCTagManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, logger:AppLogger, plc_client_async:PLCClient, plc_client_sync:PLCClient):
        if not self._initialized:
            self.tags: Dict[str, DBPLCTag] = {}
            self._plc_client_async = plc_client_async
            self._plc_client_sync = plc_client_sync
            self._lock = threading.RLock()
            self._initialized = True
            self.logger = logger

            # 周期性（异步）读取线程
            self._background_async_read_thread = None
            self._read_running = False

            # 周期性（异步）写入线程
            self._background_async_write_thread = None
            self._write_running = False
            #200ms周期间隔
            self.interval = 0.2
            #启动异步读取线程
            #self.start_background_async_read()



    @classmethod
    def initialize(cls, logger:AppLogger, plc_client_async:PLCClient, plc_client_sync:PLCClient, tag_definitions: List[Dict]):
        """初始化标签管理器"""
        instance = cls(logger, plc_client_async, plc_client_sync)

        # 创建所有标签
        for tag_def in tag_definitions:
            instance.create_tag(**tag_def)

        logger.info(f"DB区域PLC标签管理器已初始化，共创建 {len(instance.tags)} 个标签")
        return instance

    def create_tag(self,
                   name: str,
                   tagpath:str,
                   db_number: int,
                   start_offset: int,
                   size: int,
                   data_type: str,
                   bit_index: Optional[int] = None,
                   plc: str = "",
                   group: str = "",
                   config_monitor: int = 0,
                   default_value: Optional[Any] = None,
                   description: str = "") -> DBPLCTag:
        """创建并注册一个新标签"""
        with self._lock:
            if tagpath in self.tags:
                self.logger.warning(f"标签 {tagpath} 已存在，将被覆盖")

            tag = DBPLCTag(
                logger=self.logger,
                name=name,
                tagpath=tagpath,
                db_number=db_number,
                start_offset=start_offset,
                size=size,
                data_type=data_type,
                bit_index=bit_index,
                plc=plc,
                group=group,
                config_monitor=config_monitor,
                default_value=default_value,
                description=description
            )

            self.tags[tagpath] = tag
            self.logger.info(f"已创建DB标签: {tagpath}")
            return tag

    def get_tag(self, tagpath: str) -> Optional[DBPLCTag]:
        """获取指定名称的标签"""
        with self._lock:
            return self.tags.get(tagpath)

    def get_all_tags(self) -> Dict[str, DBPLCTag]:
        """获取所有标签"""
        with self._lock:
            return self.tags.copy()

    def get_tags_by_db(self, db_number: int) -> Dict[str, DBPLCTag]:
        """按DB块号获取标签"""
        with self._lock:
            return {tagpath: tag for tagpath, tag in self.tags.items() if tag.db_number == db_number}

    def get_tags_by_group(self, group_prefix: str) -> Dict[str, DBPLCTag]:
        """按组前缀获取标签"""
        with self._lock:
            return {tagpath: tag for tagpath, tag in self.tags.items() if tagpath.startswith(group_prefix)}

    def read_tag(self, tagpath: str) -> Any:
        """读取单个标签的值（实时从PLC读取）"""
        tag = self.get_tag(tagpath)
        if tag is None:
            raise ValueError(f"未找到标签: {tagpath}")

        if self._plc_client_sync is None:
            raise RuntimeError("未设置PLC客户端")

        # 获取变量配置信息
        address_info = tag.get_address_info()
        db_number = address_info['db_number']
        start_offset = address_info['start_offset']
        size = address_info['size']
        data_type = address_info['data_type']
        bit_index = address_info['bit_index']

        # PLC读取数据
        if data_type == "bool":
            result,value = self._plc_client_sync.readDB_Bit(db_number, start_offset, bit_index)
        elif data_type == "int":
            result,value = self._plc_client_sync.readDB_Int(db_number, start_offset)
        elif data_type == "dint":
            result,value = self._plc_client_sync.readDB_DInt(db_number, start_offset)
        elif data_type == "real":
            result,value = self._plc_client_sync.readDB_Real(db_number, start_offset)
        elif data_type == "lreal":
            result,value = self._plc_client_sync.readDB_LReal(db_number, start_offset)
        elif data_type == "string":
            result,value = self._plc_client_sync.readDB_String(db_number, start_offset, size)
        else:
            self.logger.error(f"未知的数据类型: {address_info['data_type']},读取失败！")
            return None
        if  result:
            tag.value = value
            return value
        else:
            self.logger.error(f"读取标签 {tagpath} 失败！")
            return None


    def write_tag(self, tagpath: str, value: Any, immediate: bool = True) -> bool:
        """写入单个标签的值

        :param tagpath: 标签路径
        :param value: 要写入的值
        :param immediate: 是否立即写入PLC，如果为False则缓存待写入值
        :return: 是否成功
        """
        tag = self.get_tag(tagpath)
        if tag is None:
            raise ValueError(f"未找到标签: {tagpath}")

        if immediate:
            # 立即写入PLC
            if self._plc_client_sync is None:
                raise RuntimeError("未设置PLC客户端")

            # 获取变量配置信息
            address_info = tag.get_address_info()
            db_number = address_info['db_number']
            start_offset = address_info['start_offset']
            size = address_info['size']
            data_type = address_info['data_type']
            bit_index = address_info['bit_index']

            # 向PLC写入数据
            if data_type == "bool":
                result = self._plc_client_sync.writeDB_Bit(db_number, start_offset, bit_index, value)
            elif data_type == "int":
                result = self._plc_client_sync.writeDB_Int(db_number, start_offset, value)
            elif data_type == "dint":
                result = self._plc_client_sync.writeDB_DInt(db_number, start_offset, value)
            elif data_type == "real":
                result = self._plc_client_sync.writeDB_Real(db_number, start_offset, value)
            elif data_type == "lreal":
                result = self._plc_client_sync.writeDB_LReal(db_number, start_offset, value)
            elif data_type == "string":
                result = self._plc_client_sync.writeDB_String(db_number, start_offset, size, value)
            else:
                self.logger.error(f"未知的数据类型: {address_info['data_type']},写入失败！")
                return False
            if result:
                # 写入成功，立马更新标签当前值
                tag.value = value
                return True
            else:
                self.logger.error(f"写入标签 {tagpath} 失败！")
                return False

        else:
            # 缓存待写入值，等待批量写入
            tag.set_pending_write_value(value)
            return True

    def read_all_tags(self) -> Dict[str, Any]:
        """批量读取所有标签的值"""
        if self._plc_client_async is None:
            raise RuntimeError("未设置PLC客户端")

        # 按DB块分组标签
        grouped_tags = self._group_tags_by_db()

        results = {}

        # 处理每个分组
        for db_number, tags in grouped_tags.items():
            # 计算读取范围
            start_offset, end_offset = self._calculate_read_range(tags)
            read_size = end_offset - start_offset + 1

            try:
                # 读取数据
                result, data = self._plc_client_async.readDB_Byte(db_number, start_offset, read_size)

                # 解析每个标签的值
                for tag in tags:
                    relative_offset = tag.start_offset - start_offset
                    tag_data = data[relative_offset : relative_offset + tag.size]

                    if tag.data_type == 'bool' and tag.bit_index is not None:
                        try:
                            value = get_bool(tag_data, 0, tag.bit_index)
                        except Exception as e:
                            value = None
                            self.logger.error(f"解析tag：{tag.tagpath}发生错误[{e}]，请检查变量配置是否正确！")
                    elif tag.data_type == 'int':
                        try:
                            value = get_int(tag_data, 0)
                        except Exception as e:
                            value = None
                            self.logger.error(f"解析tag：{tag.tagpath}发生错误[{e}]，请检查变量配置是否正确！")
                    elif tag.data_type == 'dint':
                        try:
                            value = get_dint(tag_data, 0)
                        except Exception as e:
                            value = None
                            self.logger.error(f"解析tag：{tag.tagpath}发生错误[{e}]，请检查变量配置是否正确！")
                    elif tag.data_type == 'real':
                        try:
                            value = get_real(tag_data, 0)
                        except Exception as e:
                            value = None
                            self.logger.error(f"解析tag：{tag.tagpath}发生错误[{e}]，请检查变量配置是否正确！")
                    elif tag.data_type == 'lreal':
                        try:
                            value = get_lreal(tag_data, 0)
                        except Exception as e:
                            value = None
                            self.logger.error(f"解析tag：{tag.tagpath}发生错误[{e}]，请检查变量配置是否正确！")
                    elif tag.data_type == 'string':
                        # 读取字符串数据（包括2字节的头部）
                        buffer = data[relative_offset:relative_offset + tag.size +2]
                        # 获取实际字符串长度（第二个字节）
                        actual_length = buffer[1]

                        # 提取字符串数据（从第2字节开始，取实际长度）
                        string_bytes = buffer[2:2 + actual_length]

                        # 解码字符串
                        try:
                            # 尝试使用指定编码解码
                            value = string_bytes.decode("GBK")
                        except UnicodeDecodeError:
                            """
                            如果编码失败，尝试去掉末尾一个字节重新编码，解决 尾部半个中文字符的问题
                            """
                            try:
                                value = string_bytes[:-1].decode("GBK")
                            except UnicodeDecodeError as e:
                                value = string_bytes
                                self.logger.error(f"批量读取时无法解码字符串{tag.tagpath}: {e}！")


                    else:
                            self.logger.warning(f"未知的数据类型: {tag.data_type}!")
                            value = tag_data

                    # 更新标签值
                    tag.value = value
                    results[tag.tagpath] = value

            except Exception as e:
                self.logger.error(f"批量读取时，发生严重错误：[{e}]")
                # 标记这些标签读取失败
                for tag in tags:
                    results[tag.tagpath] = None

        return results

    def read_db_tags(self, db_number: int) -> Dict[str, Any]:
        """批量读取指定DB块的所有标签值"""
        if self._plc_client_async is None:
            raise RuntimeError("未设置PLC客户端")

        # 获取指定DB块的所有标签
        db_tags = self.get_tags_by_db(db_number)
        if not db_tags:
            return {}

        # 计算读取范围
        tags_list = list(db_tags.values())
        start_offset, end_offset = self._calculate_read_range(tags_list)
        read_size = end_offset - start_offset + 1

        results = {}

        try:
            # 读取数据
            result, data = self._plc_client_async.readDB_Byte(db_number, start_offset, read_size)

            # 解析每个标签的值
            for tag in tags_list:
                relative_offset = tag.start_offset - start_offset
                tag_data = data[relative_offset:relative_offset + tag.size]

                if tag.data_type == 'bool' and tag.bit_index is not None:
                    value = get_bool(tag_data, 0, tag.bit_index)
                elif tag.data_type == 'int':
                    value = get_int(tag_data, 0)
                elif tag.data_type == 'dint':
                    value = get_dint(tag_data, 0)
                elif tag.data_type == 'real':
                    value = get_real(tag_data, 0)
                elif tag.data_type == 'lreal':
                    value = get_lreal(tag_data, 0)
                elif tag.data_type == 'string':
                    # 读取字符串数据（包括2字节的头部）
                    buffer = data[relative_offset:relative_offset + tag.size + 2]
                    # 获取实际字符串长度（第二个字节）
                    actual_length = buffer[1]

                    # 提取字符串数据（从第2字节开始，取实际长度）
                    string_bytes = buffer[2:2 + actual_length]

                    # 解码字符串
                    try:
                        # 尝试使用指定编码解码
                        value = string_bytes.decode("GBK")
                    except UnicodeDecodeError:
                        """
                        如果编码失败，尝试去掉末尾一个字节重新编码，解决 尾部半个中文字符的问题
                        """
                        try:
                            value = string_bytes[:-1].decode("GBK")
                        except UnicodeDecodeError as e:
                            value = string_bytes
                            self.logger.error(f"批量读取时无法解码字符串{tag.tagpath}: {e}！")


                else:
                    self.logger.warning(f"未知的数据类型: {tag.data_type}!")
                    value = tag_data

                # 更新标签值
                tag.value = value
                results[tag.tagpath] = value

        except Exception as e:
            self.logger.error(f"读取DB{db_number}失败: {e}")
            # 标记这些标签读取失败
            for tag in tags_list:
                results[tag.tagpath] = None

        return results

    def write_pending_tags(self) -> Dict[str, bool]:
        """批量写入所有待写入的标签值"""
        if self._plc_client_async is None:
            raise RuntimeError("未设置PLC客户端")

        # 获取所有有待写入值的标签
        pending_tags = [tag for tag in self.tags.values() if tag.has_pending_write()]
        if not pending_tags:
            return {}

        # 按DB块分组标签
        grouped_tags = self._group_tags_by_db(pending_tags)

        results = {}

        # 处理每个分组
        for db_number, tags in grouped_tags.items():
            # 计算写入范围
            start_offset, end_offset = self._calculate_write_range(tags)
            write_size = end_offset - start_offset + 1

            try:
                # 先读取原始数据
                result, original_data = self._plc_client_async.readDB_Byte(db_number, start_offset, write_size)

                # 修改数据
                modified_data = bytearray(original_data)

                for tag in tags:
                    value = tag.get_pending_write_value()
                    relative_offset = tag.start_offset - start_offset

                    # 准备要写入的数据
                    if tag.data_type == 'bool' and tag.bit_index is not None:
                        # 布尔类型需要特殊处理位操作
                        self._set_bool_in_bytearray(
                            modified_data, relative_offset,
                            tag.bit_index, value
                        )
                    elif tag.data_type == 'int':
                        set_int(modified_data, relative_offset, value)
                    elif tag.data_type == 'dint':
                        set_dint(modified_data, relative_offset, value)
                    elif tag.data_type == 'real':
                        set_real(modified_data, relative_offset, value)
                    elif tag.data_type == 'lreal':
                        set_lreal(modified_data, relative_offset, value)
                    elif tag.data_type == 'string':
                        encoding = 'gbk'
                        # 将字符串编码为字节
                        try:
                            string_bytes = value.encode(encoding)
                        except UnicodeEncodeError as e:
                            self.logger.error(f"写入字符串{tag.tagpath}时编码出错: {e}")
                        # 检查长度是否超出限制
                        max_content_length = tag.size
                        if len(string_bytes) > max_content_length:
                            # 截断字符串
                            truncated_bytes = string_bytes[:max_content_length]
                            try:
                                # 尝试解码截断后的字节，确保不会在字符中间截断
                                truncated_str = truncated_bytes.decode(encoding)
                                string_bytes = truncated_str.encode(encoding)
                                self.logger.warning(f"{tag.tagpath}字符串写入时长度超出限制，已截断为: {truncated_str}")
                            except:
                                # 如果解码失败，可能出现窃取半个中文字符的问题，尝试去掉末尾字符重试
                                truncated_str = truncated_bytes[:-1].decode(encoding)
                                string_bytes = truncated_str.encode(encoding)
                                self.logger.warning(f"{tag.tagpath}字符串写入时长度超出限制，已截断为: {truncated_str}")

                        # 创建PLC字符串格式
                        # 西门子字符串格式:
                        # 第一个字节: 最大长度 (max_length)
                        # 第二个字节: 实际长度 (actual_length)
                        # 接着是字符串数据，剩余部分填充0
                        buffer = bytearray(tag.size + 2)
                        buffer[0] = tag.size  # 最大长度
                        buffer[1] = len(string_bytes)  # 实际长度

                        # 复制字符串数据
                        buffer[2:2 + len(string_bytes)] = string_bytes

                        # 剩余部分填充0（可选，但建议填充以确保一致性）
                        for i in range(2 + len(string_bytes), tag.size + 2):
                            buffer[i] = 0


                        modified_data[relative_offset : relative_offset+tag.size+2] = buffer



                    else:
                        self.logger.warning(f"{tag.tagpath}是未知的数据类型: {tag.data_type}")

                    # 更新标签值并清除待写入值
                    #tag.value = value
                    tag.clear_pending_write_value()
                    results[tag.tagpath] = True

                # 写回数据
                self._plc_client_async.writeDB_Byte(db_number, start_offset, modified_data)

            except Exception as e:
                self.logger.error(f"批量pending写入DB{db_number}失败: {e}")
                # 标记这些标签写入失败
                for tag in tags:
                    results[tag.tagpath] = False

        return results

    def _group_tags_by_db(self, tags: Optional[List[DBPLCTag]] = None) -> Dict[int, List[DBPLCTag]]:
        """按DB块分组标签"""
        if tags is None:
            tags = list(self.tags.values())

        groups = {}
        for tag in tags:
            if tag.db_number not in groups:
                groups[tag.db_number] = []
            groups[tag.db_number].append(tag)

        return groups

    def _calculate_read_range(self, tags: List[DBPLCTag]) -> tuple:
        """计算读取的起始和结束偏移量"""
        start_offset = min([tag.start_offset for tag in tags])
        end_offset = max([tag.start_offset + tag.size - 1 if tag.data_type != "string"
                          else tag.start_offset + tag.size + 1
                          for tag in tags])
        return start_offset, end_offset

    def _calculate_write_range(self, tags: List[DBPLCTag]) -> tuple:
        """计算写入的起始和结束偏移量"""
        return self._calculate_read_range(tags)

    def _set_bool_in_bytearray(self, data: bytearray, byte_offset: int,
                               bit_index: int, value: bool):
        """在字节数组中设置布尔值"""
        if value:
            data[byte_offset] |= (1 << bit_index)
        else:
            data[byte_offset] &= ~(1 << bit_index)

    def background_async_read(self):
        print("====开始执行后台任务读取=====")
        self.logger.info(f"开始后台定时批量读取tag任务background_async_read，周期设定：{self.interval}s..")
        while self._read_running:
            self.read_all_tags()
            print("后台任务读取while循环中...")
            time.sleep(self.interval)
        self.logger.warning(f"后台定时批量读取tag任务，已停止！")

    def background_async_write(self):
        self.logger.info(f"开始后台定时批量异步写入tag任务background_async_write，周期设定：{self.interval}s..")
        while self._write_running:
            self.write_pending_tags()
            time.sleep(self.interval)
        self.logger.warning(f"后台定时批量异步写入tag任务，已停止！")

    def start_background_async_read(self):
        """启动批量读取tag线程"""
        with self._lock:
            if self._background_async_read_thread is None or not self._background_async_read_thread.is_alive():
                self._read_running = True
                self._background_async_read_thread = threading.Thread(
                    target=self.background_async_read,
                    name=f"class._background_async_read_thread",
                    daemon=True
                )
                self._background_async_read_thread.start()
                self.logger.info(f"已成功启动周期异步读取 'class._background_async_read_thread' 的线程...")

    def stop_background_async_read(self):
        """停止批量读取tag线程"""
        with self._lock:
            self._read_running = False

        # 等待线程结束
        if self._background_async_read_thread and self._background_async_read_thread.is_alive():
            self._background_async_read_thread.join(timeout=5.0)
            if self._background_async_read_thread.is_alive():
                self.logger.warning(f"程序异常：'class._background_async_read_thread' 的线程...未能正常停止")

    def start_background_async_write(self):
        """ 启动后台批量写tag线程"""
        with self._lock:
            if self._background_async_write_thread is None or not self._background_async_write_thread.is_alive():
                self._write_running = True
                self._background_async_write_thread = threading.Thread(
                    target=self.background_async_write,
                    name=f"class._background_async_write_thread",
                    daemon=True
                )
                self._background_async_write_thread.start()
                self.logger.info(f"已成功启动周期异步写 'class._background_async_write_thread' 的线程...")

    def stop_background_async_write(self):
        """停止后台批量写tag线程"""
        with self._lock:
            self._write_running = False

        # 等待线程结束
        if self._background_async_write_thread and self._background_async_write_thread.is_alive():
            self._background_async_write_thread.join(timeout=5.0)
            if self._background_async_write_thread.is_alive():
                self.logger.warning(f"程序异常：'class._background_async_write_thread' 的线程...未能正常停止")



    def __del__(self):
        """析构函数，确保资源被正确释放"""
        self.stop_background_async_read()
        self.stop_background_async_write()


# 使用示例
if __name__ == "__main__":

    # 创建一个log日志
    logger = AppLogger("VariableMonitor17Var", level=logging.INFO)
    # 创建一个plc客户端
    plc_client = PLCClient("../config\PLC1_CONF.ini", logger, True)


    # 定义标签配置
    tag_definitions = [
        {
            "tagpath" : "Motor1_Status",
            "name": "Motor1_Status",
            "db_number": 101,
            "start_offset": 0,
            "size": 1,
            "data_type": "bool",
            "bit_index": 0,
            "description": "电机1状态"
        },
        {
            "tagpath": "Motor1_Speed",
            "name": "Motor1_Speed",
            "db_number": 101,
            "start_offset": 2,
            "size": 2,
            "data_type": "int",
            "description": "电机1速度"
        },
        {
            "tagpath": "path-Temperature",
            "name": "Temperature",
            "db_number": 101,
            "config_monitor": 1,
            "start_offset": 4,
            "size": 4,
            "data_type": "real",
            "description": "温度"
        },
        {
            "tagpath": "Machine_Name",
            "name": "Machine_Name",
            "db_number": 102,
            "start_offset": 0,
            "size": 20,
            "data_type": "string",
            "description": "机器名称"
        }
    ]

    # 初始化标签管理器

    tag_manager = DBPLCTagManager.initialize(logger, plc_client, tag_definitions)
    time.sleep(5.0)
    try:


        #tag_manager.start_background_async_read()
        tag_manager.start_background_async_write()

        tag_manager.write_tag("Motor1_Speed",111,False)
        print("异步写入值111")

        asyncVlue = tag_manager.tags["Motor1_Speed"].value
        print("异步读取的Motor1_Speed:", asyncVlue)

        realValues = tag_manager.read_tag("Motor1_Speed")
        print("实时读取的Motor1_Speed:", realValues)

        print("休眠10s..")
        time.sleep(5.0)

        #print("<刷新pending>")
        #tag_manager.write_pending_tags()

        asyncVlue = tag_manager.tags["Motor1_Speed"].value
        print("异步读取的Motor1_Speed:", asyncVlue)
        realValues = tag_manager.read_tag("Motor1_Speed")
        print("实时读取的Motor1_Speed:", realValues)
        asyncVlue = tag_manager.tags["Motor1_Speed"].value
        print("异步读取的Motor1_Speed:", asyncVlue)


        print()

        tag_manager.__del__()

    except Exception as e:
        logger.error(f"操作失败: {e}")