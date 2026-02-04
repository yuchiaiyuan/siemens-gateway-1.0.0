# setup.py
import os
import sys
from PyInstaller.__main__ import run

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# PyInstaller配置
if __name__ == '__main__':
    opts = [
        'send_feishu_messages_v2.py',  # 入口文件
        '--onefile',  # 打包为单个exe
        '--name=feishu_urge_v2.0',  # 可执行文件名称
        '--paths=.',  # 添加当前目录到Python路径
    ]

    run(opts)