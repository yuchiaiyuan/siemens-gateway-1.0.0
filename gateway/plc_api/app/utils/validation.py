from typing import List, Dict, Any, Tuple
from gateway.config.globals import PLC

def validate_tag_path(tag_path: str) -> bool:
    """验证标签路径格式"""
    # 根据您的PLC系统调整验证规则
    return tag_path in PLC.DB.tags


def validate_tag_paths(tag_paths: List[str]) -> Tuple[bool, List[str]]:
    """验证多个标签路径"""
    invalid_paths = []
    for tag_path in tag_paths:
        if not validate_tag_path(tag_path):
            invalid_paths.append(tag_path)

    return len(invalid_paths) == 0, invalid_paths


def validate_write_data(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """验证写入数据格式"""
    if not isinstance(data, dict):
        return False, ["数据必须是字典格式"]

    invalid_keys = []
    for key, value in data.items():
        if not validate_tag_path(key):
            invalid_keys.append(key)

    return len(invalid_keys) == 0, invalid_keys