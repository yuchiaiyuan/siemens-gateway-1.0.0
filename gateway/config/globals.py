"""
作者：尉
创建日期：2025/12/18
这是一个全局变量文件

全局变量和配置定义
遵循统一的命名规范，便于维护和理解
规则：
前缀	    含义	        示例	                适用场景
G_	    全局变量	    G_APP_STATE	         通用的全局状态变量
C_	    常量	        C_MAX_RETRIES	    不会改变的配置值
CFG_	配置项	    CFG_DATABASE_URL	从配置文件或环境变量读取的设置
APP_	应用级变量	APP_VERSION	        与应用本身相关的信息
SYS_	系统级变量	SYS_PLATFORM	    与操作系统或运行环境相关的变量
TMP_	临时变量	    TMP_CACHE	        临时存储，可能被清理的变量
MEM_	内存缓存	    MEM_USER_CACHE	    内存中的缓存数据
THREAD_	线程相关	    THREAD_POOL	        线程或线程池相关的变量
[前缀]_[模块/领域]_[描述性名称]_[类型后缀?]

"""
from gateway.plc.client import PLCClient
from gateway.plc.log import AppLogger
from gateway.plc.tags_manager import DBPLCTagManager

class PLC:
# 后台异步批量读写周期 默认0.2s
    ASYNC_RW_INTERVAL = 0.2

    # S7同步读写链接
    S7: PLCClient
    # 标签管理 可以直接或取标签，或直接利用标签属性读写标签
    DB: DBPLCTagManager
    # 通用日志记录
    LOG: AppLogger
    # 外部API接口日志
    LOG_PLC_API: AppLogger

