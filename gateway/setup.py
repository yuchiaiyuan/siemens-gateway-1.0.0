# setup.py
import os
import sys
from PyInstaller.__main__ import run

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# PyInstaller配置
if __name__ == '__main__':
    opts = [
        '__main__.py',  # 入口文件
        '--onefile',  # 打包为单个exe
        '--name=siemens-gateway-1.0.0',  # 可执行文件名称
        '--add-data=plc;plc',  # 添加plc包
        '--add-data=plc_api;plc_api',  # 添加plc_api包
        '--hidden-import=plc',  # 确保plc包被包含
        '--hidden-import=plc_api',  # 确保plc_api包被包含
        '--paths=.',  # 添加当前目录到Python路径
    ]

    run(opts)