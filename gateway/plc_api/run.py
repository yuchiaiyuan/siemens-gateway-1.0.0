import os
from threading import Thread

from gateway.config.globals import PLC
from gateway.plc_api.app import create_app

# 创建应用实例
app = create_app(os.environ.get('FLASK_CONFIG', 'default'))
logger = PLC.LOG_PLC_API

def run_flask():
    # 启动开发服务器
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5000))
    app.run(host=host, port=port, debug=False)
    logger.info(f'API Server已启动:{host}:{port}')

def run_api():
    # 在新线程中运行Flask
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True  # 设置为守护线程
    flask_thread.start()

if __name__ == '__main__':
    # 启动开发服务器
    run_api()