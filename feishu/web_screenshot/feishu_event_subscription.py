import threading
import datetime, time
import asyncio
import lark_oapi as lark
import web_screenshot

# 1. 定义一个全局变量，用于存放截图实例
global_screenshot = None


def select_url(data):
    event_type = data.header.event_type
    chat_type = data.event.message.chat_type
    message_type = data.event.message.message_type
    chat_id = data.event.message.chat_id
    content = data.event.message.content
    open_id = data.event.sender.sender_id.open_id
    messsage_id = data.event.message.message_id
    mentions = data.event.message.mentions

    keyword = global_screenshot.config.get('keyword')
    for word in keyword:
        if word in content:
            print(f"====== 检测到关键词【{word}】 ======")
            global_screenshot.temp_job = True
            global_screenshot.messsage_id = messsage_id
            global_screenshot.task_type = word
            global_screenshot.task_url = keyword[word]



## P2ImMessageReceiveV1 为接收消息 v2.0；CustomizedEvent 内的 message 为接收消息 v1.0。
def do_p2_im_message_receive_v1(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    try:
        event_type = data.header.event_type
        chat_type = data.event.message.chat_type
        message_type = data.event.message.message_type
        mentions = data.event.message.mentions

        if event_type != "im.message.receive_v1" or message_type != "text":
            return

        if chat_type == "p2p":
            select_url(data)

        elif mentions != None:
            for mention in mentions:
                if mention.name == "iDog":
                    select_url(data)


    except Exception as e:
        print(f"[{datetime.datetime.now()}]获取消息数据异常: {str(e)}")


def do_message_event(data: lark.CustomizedEvent) -> None:
    #print(f'[ do_customized_event access ], type: message, data: {lark.JSON.marshal(data, indent=4)}')
    print("------------------------------ 自定义 ---------------------------------")


def start_screenshot_service():
    """专门用于启动截图服务的线程函数"""
    global global_screenshot
    print("正在启动截图服务...")
    global_screenshot = web_screenshot.WebScreenshot()
    # 这里的 start() 会阻塞这个子线程，但不会影响主线程
    global_screenshot.start()


def main():
    # 2. 使用子线程启动截图服务
    # daemon=True 表示主程序退出时，这个线程也会自动退出
    t = threading.Thread(target=start_screenshot_service, daemon=True)
    t.start()

    # 等待几秒确保截图服务启动完成（可选）
    time.sleep(3)

    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1) \
        .register_p1_customized_event("im.message.receive_v1", do_message_event) \
        .build()

    cli = lark.ws.Client("cli_a6aa5ab0b3309013", "L91MyAi8ep4CCLJsdW34pTSJA7IrDdDf",
                         event_handler=event_handler,
                         log_level=lark.LogLevel.DEBUG)
    cli.start()

if __name__ == "__main__":
    main()




