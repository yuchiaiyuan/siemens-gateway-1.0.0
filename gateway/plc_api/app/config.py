import os


class Config:
    # 基础配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'plc-api-secret-key'
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

    # API配置
    API_TITLE = 'PLC读写API'
    API_VERSION = '1.0'

    # 性能配置
    JSONIFY_PRETTYPRINT_REGULAR = False  # 生产环境禁用美化输出
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 最大请求大小16MB

    # 批量操作配置
    MAX_BATCH_SIZE = int(os.environ.get('MAX_BATCH_SIZE', 100))  # 批量操作最大标签数


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}