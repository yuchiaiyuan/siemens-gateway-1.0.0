from flask import Blueprint, current_app
from gateway.plc_api.app.utils.response import success_response

bp = Blueprint('health', __name__)


@bp.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    return success_response({
        'status': 'healthy',
        'service': 'PLC API',
        'version': current_app.config['API_VERSION']
    }, "服务正常")
