import os
import logging
import inspect
import uuid
from logging.handlers import RotatingFileHandler
from datetime import datetime


class AppLogger:
    """
    作者：尉
    创建日期：2025/12/13
    应用程序日志类，提供统一的日志记录功能，支持多个独立实例
    """

    def __init__(self, name: str = None, log_dir: str = 'logs', level: object = logging.INFO, max_bytes: int = 10 * 1024 * 1024,
                 backup_count: int = 10) -> None:
        """
        初始化日志记录器

        参数:
            name (str): 日志记录器名称，如果为None则自动生成唯一名称
            log_dir (str): 日志文件存储目录
            max_bytes (int): 单个日志文件最大字节数
            backup_count (int): 保留的备份文件数量
        """
        # 生成唯一名称（如果未提供）
        self.name = name or f"app_logger_{uuid.uuid4().hex[:8]}"
        self.log_dir = log_dir
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.level = level
        # 创建日志记录器
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(self.level)

        self.set_level(self.level)

        # 避免重复配置
        if not self.logger.handlers:
            self.setup_logging()
        else:
            # 如果已有处理器，只需更新格式化器以包含调用者信息
            self._update_formatters()

    def setup_logging(self):
        """配置日志记录器"""
        # 创建日志目录
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        # 生成日志文件名（包含日期）
        current_date = datetime.now().strftime('%Y-%m-%d')
        log_filename = f"{self.log_dir}/{self.name}_{current_date}.log"

        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(filename)s:%(lineno)d'
        )

        # 创建文件处理器（带日志回滚）
        file_handler = RotatingFileHandler(
            filename=log_filename,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(self.level)
        file_handler.setFormatter(formatter)

        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.level)
        console_handler.setFormatter(formatter)

        # 添加处理器到记录器
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

        self.info('===== 日志初始化完成 =====')

    def _update_formatters(self):
        """更新所有处理器的格式化器以包含调用者信息"""
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(filename)s:%(lineno)d'
        )
        for handler in self.logger.handlers:
            handler.setFormatter(formatter)

    def _get_caller_info(self):
        """获取调用者信息（文件名和行号）"""
        # 获取调用堆栈
        stack = inspect.stack()
        # 跳过当前方法（_get_caller_info）和日志方法（debug, info等）
        # 查找第一个不在当前类中的调用帧
        for frame in stack[2:]:
            if not frame.filename.endswith(__file__):
                # 只返回文件名，不包含路径
                filename = os.path.basename(frame.filename)
                return filename, frame.lineno
        # 如果找不到外部调用者，返回未知
        return "unknown", 0

    def _log_with_caller_info(self, level, msg, *args, **kwargs):
        """记录带有调用者信息的日志"""
        # 创建LogRecord并手动设置文件名和行号
        filename, lineno = self._get_caller_info()

        # 创建一个新的记录
        record = self.logger.makeRecord(
            self.name, level, filename, lineno, msg, args, None, None, None
        )

        # 处理异常信息
        if 'exc_info' in kwargs and kwargs['exc_info']:
            record.exc_info = kwargs['exc_info']

        self.logger.handle(record)

    def debug(self, msg, *args, **kwargs):
        """记录调试信息"""
        self._log_with_caller_info(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        """记录普通信息"""
        self._log_with_caller_info(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        """记录警告信息"""
        self._log_with_caller_info(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        """记录错误信息"""
        self._log_with_caller_info(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        """记录严重错误信息"""
        self._log_with_caller_info(logging.CRITICAL, msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        """记录异常信息（包括堆栈跟踪）"""
        kwargs['exc_info'] = True
        self._log_with_caller_info(logging.ERROR, msg, *args, **kwargs)

    def add_handler(self, handler):
        """添加自定义处理器"""
        self.logger.addHandler(handler)

    def remove_handler(self, handler):
        """移除处理器"""
        self.logger.removeHandler(handler)

    def set_level(self, level):
        """设置日志级别"""
        self.logger.setLevel(level)
        for handler in self.logger.handlers:
            handler.setLevel(level)

####  预定义一个通用的日志实列作为通用存  ####
#logger = AppLogger(name="logger", log_dir="logs")


# 示例使用
if __name__ == '__main__':
    # 创建多个日志实例
    logger1 = AppLogger(name="module1", log_dir="logs/module1")
    logger2 = AppLogger(name="module2", log_dir="logs/module2")
    logger3 = AppLogger()  # 使用自动生成的名称

    # 使用不同的日志实例
    logger1.info('这是模块1的日志')
    logger2.warning('这是模块2的警告')
    logger3.debug('这是匿名日志器的调试信息')

    # 验证它们是不同的实例
    print(f"Logger1名称: {logger1.name}")
    print(f"Logger2名称: {logger2.name}")
    print(f"Logger3名称: {logger3.name}")

    # 验证它们使用不同的日志文件
    logger1.info('这条消息会写入module1的日志文件')
    logger2.info('这条消息会写入module2的日志文件')
    logger3.info('这条消息会写入匿名日志器的文件')