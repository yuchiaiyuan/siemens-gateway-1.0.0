"""
作者：尉
创建日期：2025/12/20
===  这里定义的是前面监听monitor文件里VariableMonitor监听对象值变换触发的事件已经存储在了queue里，我们需要定义相干的业务逻辑去处理设备信号请求后的相关业务操作 ====
下面是一段使用使用方法示例：
-----------------------------------------------------------------------
-----------------------------------------------------------------------
# 创建紧急停止状态监控
emergency_stop = VariableMonitor("emergency_stop", False)

def handle_emergency_stop_activated(event):
    #处理紧急停止激活事件
    logger.critical("紧急停止被激活！")
    # 停止所有运动
    stop_all_motors()
    # 激活安全装置
    activate_safety_devices()
    # 发送报警通知
    send_alert_notification("紧急停止激活")

def handle_emergency_stop_deactivated(event):
    #处理紧急停止解除事件
    logger.info("紧急停止已解除")
    # 重置系统状态
    reset_system()
    # 需要手动确认后才能继续操作
    require_operator_confirmation()

# 注册处理函数
emergency_stop.register_handler(EdgeType.RISING, handle_emergency_stop_activated)
emergency_stop.register_handler(EdgeType.FALLING, handle_emergency_stop_deactivated)

# 在PLC数据读取线程中更新值
def plc_data_read_thread():
    while True:
        # 读取PLC中的紧急停止状态
        stop_state = read_plc_bit("E_STOP")
        emergency_stop.value = stop_state
        time.sleep(0.1)  # 100ms读取一次
-------------------------------------------------------------------------------------------
------------------------------------------------------------------------------------------
"""
#############################################
##  以下是实际需要自定义的业务处理逻辑  ##
#############################################


from gateway.plc.log import AppLogger
from gateway.plc.monitor import VariableEvent, EdgeType
from gateway.config.globals import PLC


logger:AppLogger

# 定义事件处理函数
def handle_rising_edge(event: VariableEvent):
    logger.info(f"处理上升沿事件: {event}")
    print(f"处理上升沿事件: {event}")



def handle_falling_edge(event: VariableEvent):
    logger.info(f"处理下降沿事件: {event}")
    print(f"处理下降沿事件: {event}")


def handle_change(event: VariableEvent):
    logger.info(f"处理普通变化事件: {event}")
    print(f"处理普通变化事件: {event}")


def handle_registe():
    tags = PLC.DB.tags
    for tag in tags:
        if PLC.DB.tags.get(tag).config_monitor:
            print(f"注册标签监听：{tag}")
            logger.info(f"注册标签监听：{tag}")
            PLC.DB.tags[tag].monitor.register_handler(EdgeType.RISING, handle_rising_edge)
            #PLC.DB.tags[tag].monitor.register_handler(EdgeType.FALLING,handle_falling_edge)
            #PLC.DB.tags[tag].monitor.register_change_handler(handle_change)
