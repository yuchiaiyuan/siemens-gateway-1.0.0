import logging
import configparser
import os
import requests
import json
import time
from datetime import datetime, timedelta

# 配置日志记录器
logger = logging.getLogger('logs/message_reminder')
logger.setLevel(logging.DEBUG)  # 设置日志级别

# 创建文件处理器
file_handler = logging.FileHandler('message_reminder.log', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# 创建日志格式器
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# 添加处理器到日志记录器
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# 飞书应用配置
APP_ID = "cli_a1d4d623dbf9500c"  # 替换为你的应用ID
APP_SECRET = "3Jqb6qL4arGWesF5ylUv2adbk7ghtpsI"  # 替换为你的应用密钥
CHAT_ID = ""
time_s = 0
time_e = 60
BOT_ID = "cli_a1d4d623dbf9500c"  # 机器人ID


def get_tenant_access_token():
    """获取租户访问令牌"""
    logger.info("开始获取租户访问令牌")
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json"}
    payload = {"app_id": APP_ID, "app_secret": APP_SECRET}

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            token = response.json().get("tenant_access_token")
            logger.debug(f"成功获取租户访问令牌: {token[:6]}...")
            return token
        logger.error(f"获取token失败 - 状态码: {response.status_code}, 响应: {response.text}")
        raise Exception(f"获取token失败: {response.text}")
    except Exception as e:
        logger.exception(f"获取租户访问令牌时发生异常: {str(e)}")
        raise


def get_history_messages(token):
    """获取10-60分钟内的历史消息"""
    logger.info("开始获取历史消息")
    # 计算时间范围
    end_time = int((datetime.now() - timedelta(minutes=int(time_s))).timestamp())
    start_time = int((datetime.now() - timedelta(minutes=int(time_e))).timestamp())

    logger.debug(f"查询时间范围: {start_time} 至 {end_time} (时间戳)")

    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    params = {
        "container_id_type": "chat",
        "container_id": CHAT_ID,
        "start_time": str(start_time),
        "end_time": str(end_time),
        "page_size": 50
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            items = response.json().get("data", {}).get("items", [])
            logger.info(f"成功获取 {len(items)} 条历史消息")
            return items
        logger.error(f"获取历史消息失败 - 状态码: {response.status_code}, 响应: {response.text}")
        raise Exception(f"获取历史消息失败: {response.text}")
    except Exception as e:
        logger.exception(f"获取历史消息时发生异常: {str(e)}")
        raise


def get_unread_users_for_message(token, message_id, mentioned_users):
    """获取指定消息的未读用户"""
    logger.info(f"开始获取消息 {message_id} 的未读用户")
    if not mentioned_users:
        logger.debug("没有提到用户，无需检查未读状态")
        return []

    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/read_users"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "user_id_type": "open_id",
        "page_size": 100
    }

    read_users = []
    page_token = ""

    try:
        # 分页获取已读用户
        while True:
            if page_token:
                params["page_token"] = page_token
                logger.debug(f"正在获取下一页数据，令牌: {page_token[:6]}...")

            response = requests.get(url, headers=headers, params=params)
            if response.status_code != 200:
                logger.error(f"获取已读用户失败 - 状态码: {response.status_code}, 响应: {response.text}")
                break

            data = response.json().get("data", {})
            users = [user["user_id"] for user in data.get("items", [])]
            read_users.extend(users)
            logger.debug(f"本页获取 {len(users)} 个已读用户")

            if not data.get("has_more"):
                break
            page_token = data.get("page_token", "")

        # 找出未读的@用户
        unread_users = [user for user in mentioned_users if user not in read_users]
        logger.info(f"消息 {message_id} 有 {len(unread_users)} 个未读用户")
        return unread_users
    except Exception as e:
        logger.exception(f"获取未读用户时发生异常: {str(e)}")
        return []


def identify_unread_mentioned_users(token):
    """识别所有消息中被@但未读的用户"""
    logger.info("开始识别所有未读的被@用户")
    messages = get_history_messages(token)

    all_unread_message = []
    logger.debug(f"共找到 {len(messages)} 条消息需要检查")

    for msg in messages:
        # 只处理机器人发送的消息
        if msg.get("sender", {}).get("id") != BOT_ID:
            logger.debug(f"跳过非机器人消息: {msg.get('message_id')}")
            continue

        # 获取被@的用户列表
        mentioned_users = [m["id"] for m in msg.get("mentions", [])]
        message_id = msg["message_id"]

        if not mentioned_users:
            logger.debug(f"消息 {message_id} 没有@任何用户")
            continue

        logger.debug(f"消息 {message_id} @了 {len(mentioned_users)} 个用户")

        # 获取这条消息的未读用户
        unread_users = get_unread_users_for_message(token, message_id, mentioned_users)

        if unread_users:
            all_unread_message.append({
                "message_id": message_id,
                "users": unread_users
            })
            logger.info(f"消息 {message_id} 有 {len(unread_users)} 个未读用户")

    logger.info(f"共找到 {len(all_unread_message)} 条未读消息需要通知")
    return all_unread_message


def urge_message(token, message_id, user_ids):
    """对消息进行加急处理（应用内加急）"""
    logger.info(f"开始对消息 {message_id} 加急，用户数量: {len(user_ids)}")
    if not message_id or not user_ids:
        logger.warning("消息ID或用户列表为空，跳过加急操作")
        return

    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/urgent_app"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "user_id_list": user_ids
    }

    params = {"user_id_type": "open_id"}

    try:
        response = requests.patch(url, headers=headers, params=params, json=payload)
        if response.status_code == 200:
            logger.info(f"消息 {message_id} 加急成功! 加急用户数: {len(user_ids)}")
        else:
            logger.error(f"加急操作失败 - 状态码: {response.status_code}, 响应: {response.text}")
    except Exception as e:
        logger.exception(f"加急操作时发生异常: {str(e)}")


def main(para_time_s, para_time_e, para_chat_id):
    global time_s, time_e, CHAT_ID
    time_s = int(para_time_s)
    time_e = int(para_time_e)

    logger.info("== 开始处理加急未读用户通知 ==")
    logger.debug(f"配置参数 - time_s: {time_s}, time_e: {time_e}, chat_id: {para_chat_id}")

    start_time = time.time()

    try:
        # 获取访问令牌
        token = get_tenant_access_token()
        logger.info("✓ 获取访问令牌成功")

        # 识别未读用户
        unread_users = []
        logger.info("⏳ 查询历史消息中的未读用户...")

        for chat_id in para_chat_id.split(","):
            CHAT_ID = chat_id
            logger.info(f"处理群组: {CHAT_ID}")
            unread_users += identify_unread_mentioned_users(token)

        if len(unread_users) > 0:
            logger.info(f"共发现 {len(unread_users)} 条有未读用户的消息")
            for user in unread_users:
                message_id = user.get("message_id")
                users = user.get("users")
                urge_message(token, message_id, users)
        else:
            logger.info("没有未读用户需要通知")

        # 计算处理时间
        elapsed = time.time() - start_time
        logger.info(f"✅ 处理完成! 耗时: {elapsed:.2f}秒,加急了消息{unread_users}")
        return unread_users

    except Exception as e:
        logger.exception(f"❌ 处理过程中出错: {str(e)}")
        return []


if __name__ == "__main__":
    try:
        config_path = "config\chat_config.ini"
        if not os.path.exists(config_path):
            logger.error(f"配置文件不存在: {config_path}")
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        config = configparser.ConfigParser()
        config.read(config_path, encoding='utf-8')

        time_s = config.getint("MONITOR", "time_s", fallback=1)
        time_e = config.getint("MONITOR", "time_e", fallback=1)
        chat_id = config.get("MONITOR", "chat_id", fallback="")
        job_time = config.getint("MONITOR", "job_time", fallback=60)

        logger.info(f"程序启动，配置: time_s={time_s}, time_e={time_e}, chat_id={chat_id}, job_time={job_time}")

        while True:
            logger.info("== 开始新一轮监控任务 ==")
            main(time_s, time_e, chat_id)
            logger.info(f"等待 {job_time} 秒后继续...")
            time.sleep(job_time)
    except Exception as e:
        logger.exception("主程序发生未捕获异常")