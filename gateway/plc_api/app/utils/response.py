from flask import jsonify
from typing import Any
from gateway.config.globals import PLC

logger = PLC.LOG_PLC_API

def success_response(data: Any = None, message: str = "操作成功"):
    """成功响应格式"""
    response = {
        "success": True,
        "message": message,
        "data": data
    }
    logger.info(f"API：处理tag成功，响应请求，出参: {response}")
    return jsonify(response)

def error_response(message: str = "操作失败", errors: Any = None, code: int = 400):
    """错误响应格式"""
    response = {
        "success": False,
        "message": message,
        "errors": errors
    }
    logger.info(f"API：处理tag失败，响应请求，出参: {response}")
    return jsonify(response), code