from flask import Flask
from flask_cors import CORS
from gateway.plc_api.app.config import config
from gateway.plc_api.app.routes import plc, health

from gateway.plc_api.app.utils.response import error_response


def create_app(config_name='default'):
    """应用工厂函数"""
    app = Flask(__name__)

    # 加载配置
    app.config.from_object(config[config_name])

    # 确保中文正确显示的配置
    app.config['JSON_AS_ASCII'] = False
    app.config['JSONIFY_MIMETYPE'] = 'application/json; charset=utf-8'


    # 启用CORS
    CORS(app)

    # 全局响应头设置
    @app.after_request
    def after_request(response):
        """设置响应头确保中文正确显示"""
        if response.mimetype.startswith('application/json'):
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response

    # 注册蓝图
    app.register_blueprint(plc.bp)
    app.register_blueprint(health.bp)

    # 添加错误处理
    @app.errorhandler(404)
    def not_found(error):
        return error_response('资源不存在', code=404)

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"服务器错误: {error}")
        return error_response('服务器内部错误', code=500)

    return app