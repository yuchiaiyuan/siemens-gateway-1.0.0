from flask import Blueprint, request, current_app

from gateway.config.globals import PLC
from gateway.plc_api.app.utils.response import success_response, error_response
from gateway.plc_api.app.utils.validation import validate_tag_paths, validate_write_data


# 创建蓝图
bp = Blueprint('plc', __name__, url_prefix='/api/plc')
logger = PLC.LOG_PLC_API


# 假设这是您已经实现的PLC读写函数
def internal_read_tags(tag_paths):
    """内部PLC读取函数 - 由您实现"""
    # 这里应该调用您已经实现的PLC读取功能
    results = {}
    for tag_path in tag_paths:
        value = PLC.DB.get_tag(tag_path).value
        results[tag_path] = value
    return results


def internal_write_tags(tag_values):
    """内部PLC写入函数 - 由您实现"""
    # 这里应该调用您已经实现的PLC写入功能
    results = {}
    for tag_path, value in tag_values.items():
        # 伪代码: success = your_plc_write_function(tag_path, value)
        PLC.DB.write_tag(tag_path, value, False)
    results = PLC.DB.write_pending_tags()
    return results



@bp.route('/read', methods=['GET'])
def read_tags():
    """批量读取PLC标签值"""
    try:

        logger.info(f"API：读取tag请求，入参: {request.args.to_dict()}")
        # 获取标签路径参数
        tags_param = request.args.get('tags')
        if not tags_param:
            return error_response("缺少tags参数")

        # 解析标签路径
        tag_paths = [tag.strip() for tag in tags_param.split(',')]
        if not tag_paths:
            return error_response("标签列表为空")

        # 验证标签路径格式
        is_valid, invalid_paths = validate_tag_paths(tag_paths)
        if not is_valid:
            return error_response(f"无效的标签路径: {invalid_paths}")

        # 检查批量大小限制
        max_batch_size = current_app.config['MAX_BATCH_SIZE']
        if len(tag_paths) > max_batch_size:
            return error_response(
                f"批量读取标签数量超过限制: {len(tag_paths)} > {max_batch_size}",
                code=413
            )

        # 调用内部PLC读取函数
        results = internal_read_tags(tag_paths)

        return success_response(results, "读取成功")

    except Exception as e:
        logger.error(f"读取PLC标签错误: {e}")
        return error_response("读取PLC标签失败")


@bp.route('/write', methods=['POST'])
def write_tags():
    """批量写入PLC标签值"""
    try:
        # 获取JSON数据
        data = request.get_json()

        logger.info(f"API：写入tag请求，入参: {data}")
        if not data:
            return error_response("请求体必须是JSON格式")

        # 验证数据格式
        is_valid, invalid_keys = validate_write_data(data)
        if not is_valid:
            return error_response(f"无效的标签路径: {invalid_keys}")

        # 检查批量大小限制
        max_batch_size = current_app.config['MAX_BATCH_SIZE']
        if len(data) > max_batch_size:
            return error_response(
                f"批量写入标签数量超过限制: {len(data)} > {max_batch_size}",
                code=413
            )

        # 调用内部PLC写入函数
        results = internal_write_tags(data)

        # 检查写入结果
        failed_writes = {tag: success for tag, success in results.items() if not success}
        if failed_writes:
            return error_response(
                "部分标签写入失败",
                errors=failed_writes
            )

        return success_response(results, "写入成功")

    except Exception as e:
        logger.error(f"写入PLC标签错误: {e}")
        return error_response("写入PLC标签失败")


@bp.route('/batch', methods=['POST'])
def batch_operations():
    """批量读写操作（读写混合）"""
    try:

        data = request.get_json()
        logger.info(f"API：混合操作tag请求，入参: {request.data}")

        if not data:
            return error_response("请求体必须是JSON格式")

        # 分离读取和写入操作
        read_tags = data.get('read', [])
        write_data = data.get('write', {})

        # 验证读取标签
        is_valid, invalid_reads = validate_tag_paths(read_tags)
        if not is_valid:
            return error_response(f"无效的读取标签路径: {invalid_reads}")

        # 验证写入数据
        is_valid, invalid_writes = validate_write_data(write_data)
        if not is_valid:
            return error_response(f"无效的写入标签路径: {invalid_writes}")

        # 检查总操作数量限制
        max_batch_size = current_app.config['MAX_BATCH_SIZE']
        total_operations = len(read_tags) + len(write_data)
        if total_operations > max_batch_size:
            return error_response(
                f"批量操作数量超过限制: {total_operations} > {max_batch_size}",
                code=413
            )

        # 执行读取操作
        read_results = {}
        if read_tags:
            read_results = internal_read_tags(read_tags)

        # 执行写入操作
        write_results = {}
        if write_data:
            write_results = internal_write_tags(write_data)

        # 组合响应
        response_data = {
            'read': read_results,
            'write': write_results
        }

        return success_response(response_data, "批量操作成功")

    except Exception as e:
        logger.error(f"批量操作PLC标签错误: {e}")
        return error_response("批量操作PLC标签失败")