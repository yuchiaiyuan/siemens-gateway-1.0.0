import requests
import json
import os
import sys
import logging
from logging.handlers import RotatingFileHandler  # 📌 新增：导入轮转文件处理器
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Any

# ======================== 【配置专区】 ========================
FEISHU_APP_ID = "cli_a6aa5ab0b3309013"
FEISHU_APP_SECRET = "L91MyAi8ep4CCLJsdW34pTSJA7IrDdDf"
FEISHU_CHAT_ID = "oc_5e64b13f2a57b78cba6f2c8ae6159b77"
DEFAULT_DETECTION_IMAGE_PATH = r"C:\deeplearning\ultralytics-8.3.163\dist\Image\TB2\2026-01-28\HLX12B173T1515508_OK_20260128 104026.jpg"


# =================================================================================

def setup_rotating_logger():
    """
    配置回转日志：单文件最大10M，保留最近10个日志文件，同时控制台输出日志
    日志文件：当前目录下 yolo_detection.log（自动生成，轮转后为yolo_detection.log.1、.2...）
    """
    # 1. 获取日志器，设置全局日志级别（INFO：记录关键信息，DEBUG/ERROR按需调整）
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers.clear()  # 清除默认处理器，避免重复打印

    # 2. 配置轮转文件处理器：10M/个，保留最近10个
    log_file = "feishu.log"  # 日志主文件名
    max_bytes = 10 * 1024 * 1024    # 单文件最大大小：10M（字节转换）
    backup_count = 10               # 保留最近10个日志文件
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"  # 支持中文日志，避免乱码
    )

    # 3. 配置控制台处理器（同时在控制台打印日志，方便调试）
    console_handler = logging.StreamHandler()

    # 4. 配置日志格式：[时间] [日志级别] [模块:行号] 日志内容（便于问题排查）
    log_format = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"  # 时间格式，清晰易读
    )
    file_handler.setFormatter(log_format)
    console_handler.setFormatter(log_format)

    # 5. 将处理器添加到日志器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

# 初始化日志器（全局可用）
logger = setup_rotating_logger()


def get_tenant_access_token() -> Optional[str]:
    """获取租户访问令牌"""
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        logger.error("飞书APP_ID/APP_SECRET未配置")
        return None

    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json"}
    payload = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        response.raise_for_status()
        token_data = response.json()
        if token_data.get("code") != 0:
            logger.error(f"获取令牌失败：{token_data.get('msg')}")
            return None
        return token_data.get("tenant_access_token")
    except Exception as e:
        logger.error(f"获取令牌异常：{str(e)}", exc_info=True)
        return None


def upload_image(image_path: str, token: str) -> Optional[str]:
    """上传图片到飞书，返回img_key"""
    image_path = os.path.abspath(image_path)
    if not os.path.exists(image_path) or not image_path.lower().endswith((".jpg", ".jpeg", ".png")):
        logger.error(f"图片路径无效：{image_path}")
        return None

    url = "https://open.feishu.cn/open-apis/im/v1/images"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with open(image_path, 'rb') as file:
            files = {'image': (os.path.basename(image_path), file, 'image/jpeg')}
            data = {"image_type": "message"}
            response = requests.post(url, headers=headers, files=files, data=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            if result.get("code") != 0:
                logger.error(f"图片上传失败：{result.get('msg')}")
                return None
            return result.get("data", {}).get("image_key")
    except Exception as e:
        logger.error(f"图片上传异常：{str(e)}", exc_info=True)
        return None


def create_card_content(image_key,title,content,note) -> Dict[str, Any]:
    """构建飞书卡片 - 新增防重复回调配置"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 生成唯一请求ID（用于云端去重）
    request_uuid = str(uuid.uuid4())

    # 基础卡片结构 - 新增callback_id（飞书防重复回调核心）
    card = {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
            "update_multi": True
        },
        "callback_id": f"defect_alert_{request_uuid}",  # 唯一回调ID，云端可去重
        "header": {
            "title": {"tag": "plain_text", "content": f"{title}"},
            "template":"green"
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"{content}"},
                "margin": "md"
            },
            {
                "tag": "img",
                "img_key": image_key,
                "alt": {"tag": "plain_text", "content": "检测图片"},
                "mode": "fit_horizontal",
                "preview": True,
                "margin": "md"
            }
        ]
    }
    return card


def send_message(chat_id: str, card_content: Dict[str, Any], token: str) -> Optional[str]:
    """发送卡片到飞书群 - 确保只发送一次"""
    if not chat_id or not card_content:
        logger.error("群ID或卡片内容为空")
        return None

    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}"
    }

    payload = {
        "receive_id": chat_id,
        "msg_type": "interactive",
        "content": json.dumps(card_content, ensure_ascii=False)
    }

    params = {"receive_id_type": "chat_id"}

    try:
        # 新增超时和重试控制，避免重复发送
        response = requests.post(
            url,
            headers=headers,
            params=params,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            timeout=15,
            allow_redirects=False  # 禁止重定向，避免重复请求
        )
        response.raise_for_status()
        result = response.json()
        if result.get("code") != 0:
            logger.error(f"发送失败：{result.get('msg')}")
            return None
        message_id = result.get("data", {}).get("message_id")
        logger.info(f"消息发送成功，ID: {message_id}")
        return message_id
    except requests.exceptions.RetryError:
        logger.error("请求重试次数超限，避免重复发送")
        return None
    except Exception as e:
        logger.error(f"发送异常：{str(e)}", exc_info=True)
        return None


def send_message_reply(root_id) -> Optional[str]:
    """
    发送卡片到飞书群
    :param root_id: (可选) 要回复的消息ID。如果传入此参数，消息将以回复形式发送。
    """

    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{root_id}/reply"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {get_tenant_access_token()}"
    }

    # 创建卡片内容（修正：直接返回卡片对象，不包装成列表）
    card_content = {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
            "update_multi": True
        },
        "header": {
            "title": {"tag": "plain_text", "content": "正在查询中..."},
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": f"预计10秒内完成，请等待！"},
                "margin": "md"
            },

        ]
    }

    # 修正payload结构
    payload = {
        #"receive_id": chat_id,
        "msg_type": "interactive",
        "content": json.dumps(card_content, ensure_ascii=False)  # 修正：直接dump卡片对象
    }

    # 如果需要回复消息
    if root_id:
        # 飞书回复消息的正确格式：使用"reply"参数
        payload["root_id"] = root_id
        logger.info(f"正在回复消息 ID: {root_id}")


    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,  # 使用json参数自动编码，而不是手动data
            timeout=15
        )

        # 检查响应状态
        if response.status_code != 200:
            logger.error(f"HTTP错误: {response.status_code}")
            logger.error(f"响应内容: {response.text}")
            return None

        result = response.json()
        if result.get("code") != 0:
            logger.error(f"飞书API错误：{result.get('msg')}")
            return None

        message_id = result.get("data", {}).get("message_id")
        logger.info(f"消息发送成功，ID: {message_id}")
        return message_id

    except requests.exceptions.RequestException as e:
        logger.error(f"请求异常：{str(e)}")
        return None
    except Exception as e:
        logger.error(f"发送异常：{str(e)}", exc_info=True)
        return None


def update_message_reply(root_id,img_path,task_type_name) -> Optional[str]:
    token = get_tenant_access_token()
    image_key = upload_image(img_path, token)
    if not image_key:
        logger.error("图片上传失败")
        return
    card_content = create_card_content(image_key, task_type_name, f'** 时间: **{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', "")

    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{root_id}"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}"
    }
    # 修正payload结构
    payload = {
        #"receive_id": chat_id,
        "msg_type": "interactive",
        "content": json.dumps(card_content, ensure_ascii=False)  # 修正：直接dump卡片对象
    }


    try:
        response = requests.patch(
            url,
            headers=headers,
            json=payload,  # 使用json参数自动编码，而不是手动data
            timeout=15
        )

        # 检查响应状态
        if response.status_code != 200:
            logger.error(f"HTTP错误: {response.status_code}")
            logger.error(f"响应内容: {response.text}")
            return None

        result = response.json()
        if result.get("code") != 0:
            logger.error(f"飞书API错误：{result.get('msg')}")
            return None

        message_id = result.get("data", {}).get("message_id")
        logger.info(f"更新发送成功，ID: {message_id}")
        return message_id

    except requests.exceptions.RequestException as e:
        logger.error(f"请求异常：{str(e)}")
        return None
    except Exception as e:
        logger.error(f"发送异常：{str(e)}", exc_info=True)
        return None


def main(chat_id,image_path,title,content,note):
    """主函数 - 确保只执行一次"""
    # 新增：检查是否已有运行实例，避免重复执行
    lock_file = "feishu_alert.lock"
    if os.path.exists(lock_file):
        logger.error("检测到已有运行实例，避免重复发送")
        return
    try:
        # 创建锁文件，防止重复执行
        with open(lock_file, 'w', encoding='utf-8') as f:
            f.write(f"running_{datetime.now().strftime('%Y%m%d%H%M%S')}")

        target_image_path = image_path if image_path else DEFAULT_DETECTION_IMAGE_PATH
        token = get_tenant_access_token()
        if not token:
            logger.error("获取访问令牌失败")
            return
        image_key = upload_image(target_image_path, token)
        if not image_key:
            logger.error("图片上传失败")
            return
        card_content = create_card_content(image_key,title,content,note)
        message_id = send_message(chat_id, card_content, token)
        if message_id:
            logger.info(f"卡片发送成功，消息ID：{message_id}")
        else:
            logger.error("卡片发送失败")
    finally:
        # 删除锁文件
        if os.path.exists(lock_file):
            os.remove(lock_file)


if __name__ == "__main__":
    # 新增：避免命令行参数重复传递导致多次执行
    cli_image_path = sys.argv[1] if len(sys.argv) > 1 else None
    title = "标题"
    content = "content"
    note=""
    main(FEISHU_CHAT_ID,cli_image_path,title,content,note)