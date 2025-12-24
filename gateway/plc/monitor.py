"""
作者：尉
创建日期：2025/12/22

我们要设计一个类，用于监控一个变量的值变化，特别是对于布尔量，要检测上升沿（false->true）和下降沿（true->false）。
同时，我们希望将事件触发和事件处理解耦，事件触发后交由其他线程（消费者线程）去执行相关的业务逻辑。

设计思路：

使用一个线程安全的变量存储当前值，并允许设置新值。
当设置新值时，检查值是否发生变化，以及如果是布尔量，检查边沿变化。
使用线程安全的事件队列（可以使用queue.Queue）来存放事件，由单独的消费者线程处理。
提供注册事件处理回调函数的方法，允许用户为上升沿和下降沿注册不同的回调。
我们将设计一个类，支持监控任意类型的变量，但特别对布尔量提供边沿检测。

考虑到通用性，我们也可以支持其他类型的变量变化事件，但重点在布尔量的边沿。

类设计：
类名：VariableMonitor
属性：
- current_value: 当前值
- _lock: 用于线程安全
- event_queue: 事件队列（使用queue.Queue）
- consumer_thread: 消费者线程
- running: 消费者线程运行标志
- rise_handlers: 上升沿回调列表（如果是布尔值，false->true）
- fall_handlers: 下降沿回调列表（如果是布尔值，true->false）
- change_handlers: 任意变化回调列表（适用于任何类型）

方法：
    - __init__(self, initial_value=None): 初始化，设置初始值
    - set_value(self, new_value): 设置新值，并触发相应事件
    - register_rise_handler(self, handler): 注册上升沿处理函数（布尔量）
    - register_fall_handler(self, handler): 注册下降沿处理函数（布尔量）
    - register_change_handler(self, handler): 注册任意变化处理函数
    - _start_consumer(self): 启动消费者线程
    - _stop_consumer(self): 停止消费者线程
    - _consume_events(self): 消费者线程函数，从队列中取出事件并处理

事件表示：我们可以用一个元组或字典来表示事件，包含事件类型和值。例如：
('rise', True) 表示上升沿事件，当前值为True
('fall', False) 表示下降沿事件，当前值为False
('change', new_value) 表示变化事件，值为新值

注意：由于布尔量也是变化的一种，所以当布尔量变化时，除了触发边沿事件，也会触发变化事件。
另外，我们希望这个监控类是线程安全的，所以设置值和处理事件队列都需要加锁。
但是注意：事件处理是在单独的消费者线程中，所以注册的回调函数需要是线程安全的，并且如果回调函数执行时间很长，可能会阻塞事件处理。
我们可以选择使用一个单独的线程来处理事件，这样即使回调函数执行时间较长，也不会阻塞主线程设置值。

 类设计说明
1. 核心类
VariableMonitor：主监控类

管理变量值和变化检测
提供事件队列和消费者线程
支持注册不同类型的事件处理函数
VariableEvent：事件类

封装变量变化信息
包含变量名、旧值、新值、时间戳和边沿类型
EdgeType：枚举类

定义边沿类型（上升沿、下降沿、双边沿）
2. 关键特性
线程安全：使用 RLock 确保多线程环境下的安全性
生产者-消费者模式：使用队列分离事件产生和消费
精确边沿检测：专门针对布尔值检测上升沿和下降沿
灵活的事件处理：支持注册多种类型的事件处理函数
资源管理：提供正确的启动和停止机制

    扩展建议
添加去抖动功能：对于机械开关等可能产生抖动的信号，可以添加去抖动逻辑
支持超时检测：检测信号保持时间，例如短按和长按的区别
添加历史记录：记录变量的历史变化，便于调试和分析
支持批量操作：一次性更新多个变量，减少事件触发次数
添加统计功能：统计边沿触发次数、变化频率等
这个设计提供了一个灵活且健壮的变量监控框架，可以根据具体需求进行扩展和定制。
"""
from gateway.plc import log
import threading
import time
import queue
from typing import Any, Callable, Optional
from enum import Enum

class EdgeType(Enum):
    """边沿类型枚举"""
    RISING = "rising"  # 上升沿
    FALLING = "falling"  # 下降沿
    BOTH = "both"  # 双边沿


class VariableEvent:
    """变量事件类"""

    def __init__(self, variable_name: str, old_value: Any, new_value: Any, edge_type: Optional[EdgeType] = None):
        self.variable_name = variable_name
        self.old_value = old_value
        self.new_value = new_value
        self.edge_type = edge_type
        self.timestamp = time.time()

    def __str__(self):
        if self.edge_type:
            return f"{self.variable_name} {self.edge_type.value} edge: {self.old_value} -> {self.new_value}"
        else:
            return f"{self.variable_name} changed: {self.old_value} -> {self.new_value}"


class VariableMonitor:
    """
    变量监控类，支持值变化检测和边沿事件触发
    """

    def __init__(self, name: str, logger: log.AppLogger, initial_value: Any = None):
        """
        初始化变量监控器

        参数:
            name (str): 变量名称
            initial_value (Any): 初始值
        """
        self.name = name
        self.logger = logger
        self._value = initial_value
        self._old_value = initial_value
        self._lock = threading.RLock()
        self._event_queue = queue.Queue()
        self._event_handlers = {
            EdgeType.RISING: [],
            EdgeType.FALLING: [],
            EdgeType.BOTH: [],
            "change": []  # 普通变化事件
        }
        self._consumer_thread = None
        self._running = False

        # 启动事件消费者线程
        # self.start_consumer()

    @property
    def value(self) -> Any:
        """获取当前值"""
        with self._lock:
            return self._value

    @value.setter
    def value(self, new_value: Any):
        """设置新值并检测变化"""
        with self._lock:
            old_value = self._value
            self._value = new_value

            # 检测值变化
            if old_value != new_value:
                self._detect_change(old_value, new_value)

    def _detect_change(self, old_value: Any, new_value: Any):
        """检测值变化并生成相应事件"""
        # 创建普通变化事件
        change_event = VariableEvent(self.name, old_value, new_value)
        self._event_queue.put(("change", change_event))

        # 检测布尔值的边沿变化
        if isinstance(old_value, bool) and isinstance(new_value, bool):
            if old_value is False and new_value is True:
                # 上升沿事件
                edge_event = VariableEvent(self.name, old_value, new_value, EdgeType.RISING)
                self._event_queue.put((EdgeType.RISING, edge_event))
                self._event_queue.put((EdgeType.BOTH, edge_event))

            elif old_value is True and new_value is False:
                # 下降沿事件
                edge_event = VariableEvent(self.name, old_value, new_value, EdgeType.FALLING)
                self._event_queue.put((EdgeType.FALLING, edge_event))
                self._event_queue.put((EdgeType.BOTH, edge_event))

    def register_handler(self, event_type: EdgeType, handler: Callable[[VariableEvent], None]):
        """
        注册事件处理函数

        参数:
            event_type (EdgeType): 事件类型
            handler (Callable): 处理函数，接受一个VariableEvent参数
        """
        with self._lock:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = []
            self._event_handlers[event_type].append(handler)

    def register_change_handler(self, handler: Callable[[VariableEvent], None]):
        """
        注册普通变化事件处理函数

        参数:
            handler (Callable): 处理函数，接受一个VariableEvent参数
        """
        with self._lock:
            self._event_handlers["change"].append(handler)

    def _event_consumer(self):
        """事件消费者线程函数"""
        self.logger.info(f"变量 '{self.name}' 事件消费者线程工作中...")

        while self._running or not self._event_queue.empty():
            try:
                # 从队列获取事件，设置超时以便定期检查运行状态
                event_type, event = self._event_queue.get(timeout=1.0)

                # 处理事件
                if event_type in self._event_handlers:
                    for handler in self._event_handlers[event_type]:
                        try:
                            handler(event)
                        except Exception as e:
                            self.logger.error(f"事件处理函数执行失败: {e}")

                # 标记任务完成
                self._event_queue.task_done()

            except queue.Empty:
                # 队列为空，继续循环
                continue
            except Exception as e:
                self.logger.error(f"事件消费过程中发生异常: {e}")

        self.logger.warning(f"变量 '{self.name}' 事件消费者线程停止")

    def start_consumer(self):
        """启动事件消费者线程"""
        with self._lock:
            if self._consumer_thread is None or not self._consumer_thread.is_alive():
                self._running = True
                self._consumer_thread = threading.Thread(
                    target=self._event_consumer,
                    name=f"{self.name}_EventConsumer",
                    daemon=True
                )
                self._consumer_thread.start()
                self.logger.info(f"启动变量 '{self.name}' 的事件消费者线程")

    def stop_consumer(self):
        """停止事件消费者线程"""
        with self._lock:
            self._running = False

        # 等待线程结束
        if self._consumer_thread and self._consumer_thread.is_alive():
            self._consumer_thread.join(timeout=5.0)
            if self._consumer_thread.is_alive():
                self.logger.warning(f"变量 '{self.name}' 的事件消费者线程未能正常停止")

    def wait_until_processed(self, timeout: Optional[float] = None):
        """
        等待所有事件处理完成

        参数:
            timeout (float): 超时时间，None表示无限等待

        返回:
            bool: 是否所有事件都已处理完成
        """
        return self._event_queue.join()

    def __del__(self):
        """析构函数，确保资源被正确释放"""
        self.stop_consumer()


# 使用示例
if __name__ == "__main__":
    # 创建布尔变量监控器
    logger = log.AppLogger("VariableMonitor")

    bool_monitor = VariableMonitor("emergency_stop",logger, False)


    # 定义事件处理函数
    def handle_rising_edge(event: VariableEvent):
        print(f"处理上升沿事件: {event}")
        # 这里可以执行紧急停止触发的业务逻辑
        print("紧急停止被触发，执行安全操作...")


    def handle_falling_edge(event: VariableEvent):
        print(f"处理下降沿事件: {event}")
        # 这里可以执行紧急停止解除的业务逻辑
        print("紧急停止解除，恢复正常操作...")


    def handle_change(event: VariableEvent):
        print(f"处理普通变化事件: {event}")


    # 注册事件处理函数
    bool_monitor.register_handler(EdgeType.RISING, handle_rising_edge)
    bool_monitor.register_handler(EdgeType.FALLING, handle_falling_edge)
    bool_monitor.register_change_handler(handle_change)

    # 模拟变量变化
    print("=== 模拟变量变化 ===")

    # 初始值: False
    print(f"当前值: {bool_monitor.value}")

    # 设置为 True (触发上升沿)
    print("设置值为 True")
    bool_monitor.value = True

    # 等待事件处理
    time.sleep(0.1)

    # 再次设置为 True (不会触发事件，因为值没有变化)
    print("再次设置值为 True")
    bool_monitor.value = True

    # 等待事件处理
    time.sleep(0.1)

    # 设置为 False (触发下降沿)
    print("设置值为 False")
    bool_monitor.value = False

    # 等待事件处理完成
    bool_monitor.wait_until_processed()

    # 停止消费者线程
    bool_monitor.stop_consumer()