"""
作者：尉
创建日期：2025/12/17
这是一段程序执行前的初始化程序：
        # 1.PLC链接属性配置文件加载
        2.tag变量配置sqlite文件内容加载
        3.logger日志初始化
        4.client PLC链接管理初始化
        5.PLCTagManger单实例类初始化
        6.monitor_handle监听回调函数注册
        7.利用apscheduler里的 BackgroundScheduler管理 后台tag的批量异步读写 进程调用
        8.为外部程序提供标签读写的服务，restful接口
        ...
"""
import logging
import time

from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from gateway.plc.client import PLCClient
from gateway.plc.log import AppLogger
from gateway.plc.tags_manager import DBPLCTagManager

from gateway.config.globals import PLC
import monitor_handler_register as PlcMonitorHandler

def load_tags_conf(config_db_path):
    import sqlite3
    # 连接到数据库（如果不存在会自动创建）
    conn = sqlite3.connect(config_db_path)

    # 创建游标对象
    cursor = conn.cursor()

    # 执行SQL查询
    cursor.execute("SELECT * FROM config_plc_tags")

    # 获取所有数据
    rows = cursor.fetchall()

    tags = []
    # 遍历结果
    for row in rows:
        tag = {}
        plc = row[1]
        group = row[2]
        tagpath = row[3]
        name = row[4]
        desc = row[5]
        default_value = row[6]
        config_monitor = row[7]
        data_type = row[8]
        db_number = row[9]
        byte_offset = row[10]
        bit_index = row[11]
        size = row[12]

        tag['plc'] = plc
        tag['group'] = group
        tag['tagpath'] = tagpath
        tag['name'] = name
        tag['description'] = desc
        tag['default_value'] = default_value
        tag['config_monitor'] = config_monitor
        tag['data_type'] = data_type
        tag['db_number'] = db_number
        tag['start_offset'] = byte_offset
        tag['bit_index'] = bit_index
        tag['size'] = size
        tags.append(tag)
    # 关闭连接
    conn.close()
    return tags

def creat_log(log_file_name, log_file_path = "logs", log_level = logging.INFO):
    # 创建一个log日志
    logger = AppLogger(log_file_name, log_file_path, log_level)
    return logger


def creat_plc_client(plc_conf_path, logger, heartbeat = False):
    # 创建一个plc客户端
    plc_client = PLCClient(plc_conf_path, logger, heartbeat)
    return plc_client



def init():
    """
    ################################################# 1. #######################################################
    日志文件初始化
    """
    # 针对PLC链接管理的日志 记录链接的健康检测和底层读写相关记录
    logger_plc_client_sync = creat_log('plc_client_sync.log', "logs/client")
    logger_plc_client_async = creat_log('plc_client_async.log', "logs/client")
    # 记录tag的创建 tags批量异步读写结果 tag值变换的监听处理
    logger_tag_manager = creat_log('tags_manager.log', "logs/tags_manager")
    # 记录消费者线程 处理监听任务的业务逻辑过程日志
    logger_monitor_handler = creat_log('monitor_handler.log', "logs/monitor_handler")
    # 记录外部程序调用的记录
    logger_external_api = creat_log('external_api.log', "logs/external_api")
    PLC.LOG_PLC_API = logger_external_api
    # 创建一个通用的应用级日志
    PLC.LOG = creat_log('app.log', "logs/app")

    PLC.LOG.info("=============== 初始化程序执行开始 ================")
    """
    ################################################# 2. #######################################################
    PLC1进行初始化,建立两个链接 分别用于后台周期异步读写  和业务逻辑相应时的同步实时读写
    并向全局传出一个Client同步读写链接
    """
    client_plc1_sync = creat_plc_client("config/PLC1_CONF.ini", logger_plc_client_sync, heartbeat = True)
    client_plc1_async = creat_plc_client("config/PLC1_CONF.ini", logger_plc_client_async)
    # 给应用程序一个全局的读写链接
    PLC.S7 = client_plc1_sync

    PLC.LOG.info("... S7异步/同步读写链接已建立 ...")

    """
    ################################################# 3. #######################################################
    PLC1的TAG导入；
    PLCTagManger 单实例初始化 并传出TAGS管理器
    """
    # 等待客户端链接建立稳定
    time.sleep(1.0)
    config_db_path = "config/Database.db"
    tag_definitions = load_tags_conf(config_db_path)
    PLC.DB = DBPLCTagManager.initialize(logger_tag_manager, client_plc1_async, client_plc1_sync, tag_definitions)

    PLC.LOG.info("... tag标签配置数据已初始化完成 ...")
    """
    ################################################# 4. #######################################################
    monitor_handle监听回调函数注册
    """
    PlcMonitorHandler.logger = logger_monitor_handler
    PlcMonitorHandler.handle_registe()

    PLC.LOG.info("... 标签监听handler方法已注册完毕 ...")

    """
    ################################################# 5. #######################################################
    后台任务管理
    BackgroundScheduler管理
    例如：后台tag的批量异步读写
    """
    def job_listener(event):
        if event.exception:
            PLC.LOG.error(f"任务执行失败: {event.exception}")
        else:
            PLC.LOG.debug("任务执行成功")
    try:
        # 创建调度器配置
        scheduler = BackgroundScheduler({
            'apscheduler.job_defaults.max_instances': 1,  # 允许的最大并发实例数
            'apscheduler.timezone': 'Asia/Shanghai',  # 设置时区
        })
        # 添加任务监听器
        scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        # 添加定时任务
        scheduler.add_job(
            PLC.DB.read_all_tags,
            trigger=IntervalTrigger(seconds = PLC.ASYNC_RW_INTERVAL),
            id='plc1_background_read_all_tags',
            name='PLC1的后台周期读取任务',
            misfire_grace_time=1,  # 允许的延迟执行时间
            coalesce=True,  # 合并多次未执行的任务
            max_instances=1  # 最大并发实例数
        )
        # 启动调度器
        scheduler.start()
        print(f"plc1_background_read_all_tags定时任务调度器已启动,周期设定{PLC.ASYNC_RW_INTERVAL}s ...")
        PLC.LOG.info(f"... plc1_background_read_all_tags定时任务调度器已启动,周期设定{PLC.ASYNC_RW_INTERVAL}s...")
    except Exception as e:
        print(f"scheduler后台异步读写任务启动失败！！！原因：{e}")
        PLC.LOG.error(f"错误：scheduler后台异步读写任务启动失败！！！原因：{e}")

    """
    ################################################# 6. #######################################################
    外部API Server初始化
    """
    from gateway.plc_api.run import run_api
    run_api()
    PLC.LOG.info("... API Service 接口服务已启动 ...")

    PLC.LOG.info("=============== 初始化程序执行结束 ================")

if __name__ == '__main__':
    init()