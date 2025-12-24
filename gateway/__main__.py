import time
import sys
import os
import win32api
import win32event
from ctypes import windll
# 导入业务初始化函数
from gateway.__init__ import init

# 1. 互斥体名称：显式Local\前缀（本地会话级），GUID保证全局唯一
# 若需跨管理员/普通权限运行，改为Global\（需管理员身份启动）
MUTEX_NAME = "Local\\GateWay_唯一标识_8F6F0AC4-9030-11D1-9191-006008029A37"
# 2. 全局变量存储互斥体句柄：防止Python垃圾回收提前销毁句柄（核心）
g_mutex_handle = None

def is_already_running():
    """检测是否已有实例运行（修复所有问题+增强健壮性）"""
    global g_mutex_handle
    # 固定错误码：183是Windows系统中"对象已存在"的常量（替代win32con.ERROR_ALREADY_EXISTS）
    ERROR_ALREADY_EXISTS = 183

    try:
        # 创建互斥体：第二个参数False表示非初始拥有者
        g_mutex_handle = win32event.CreateMutex(None, False, MUTEX_NAME)
        # 关键：立即获取错误码，中间不插入任何代码（防止错误码被系统重置）
        last_error = win32api.GetLastError()

        # 调试信息（打包后可注释，方便排查）
        print(f"[启动前检测] 互斥体检测码：{last_error}（{ERROR_ALREADY_EXISTS}=已存在，0=新建）")

        # 核心判断：直接使用固定错误码，彻底摆脱win32con依赖
        if last_error == ERROR_ALREADY_EXISTS:
            # 已有实例：关闭句柄，返回True
            win32api.CloseHandle(g_mutex_handle)
            g_mutex_handle = None  # 重置全局变量
            return True
        # 新实例：保留句柄，返回False
        return False

    # 精细化异常捕获：区分不同异常类型，避免无脑误判
    except win32api.error as e:
        # 仅捕获Windows系统级互斥体错误（如权限不足、名称无效）
        print(f"[错误] 创建互斥体时发生系统错误：{e}")
        return True  # 系统错误时阻止多开
    except Exception as e:
        # 捕获其他非致命异常（如代码笔误、属性错误）
        print(f"[警告] 实例检测时发生非致命异常：{type(e).__name__}: {e}")
        return False  # 不阻止程序启动，避免误判

def bring_window_to_front(window_title="GateWay控制台"):
    """将已运行的控制台窗口置顶（可选，不影响核心逻辑）"""
    try:
        # 查找窗口（根据标题，需与实际窗口标题匹配）
        hwnd = windll.user32.FindWindowW(None, window_title)
        if hwnd:
            windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE：恢复最小化窗口
            windll.user32.SetForegroundWindow(hwnd)  # 置顶窗口
    except Exception as e:
        print(f"[警告] 置顶窗口失败：{e}")

def main():
    """主程序入口（优化逻辑结构，分离检测与业务）"""
    # 第一步：先执行实例检测（移出try块，避免被业务逻辑异常干扰）
    if is_already_running():
        print("程序已在运行中！即将退出...")
        bring_window_to_front()
        # 强制终止进程（os._exit比sys.exit更彻底，适用于打包后的EXE）
        input("按回车退出...")
        os._exit(0)

    # 第二步：执行业务逻辑（单独包裹异常处理）
    try:
        print("程序启动成功，唯一实例运行中...")
        init()  # 业务初始化逻辑
        # 模拟主循环（替换为你的实际业务逻辑）
        while True:
            time.sleep(2)
    except Exception as e:
        print(f"[错误] 程序异常退出：{e}")
        input("按回车退出...")
        os._exit(1)

if __name__ == "__main__":
    main()