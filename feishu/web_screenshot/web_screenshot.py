#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网页定时截图程序
功能：定时保存指定网页为图片到本地，后台运行无需打开浏览器
"""

import asyncio
import os
import sys
import time
import json
from asyncio import subprocess
from datetime import datetime
from playwright.async_api import async_playwright
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import feishu_send_img
from feishu.web_screenshot.feishu_send_img import update_message_reply




class WebScreenshot:
    def __init__(self):
        self.config = self.load_config()
        self.url = self.config.get('url', 'https://www.baidu.com')
        self.save_dir = self.config.get('save_dir', './screenshots')
        self.cron_expression = self.config.get('cron_expression', "0 0/1 * * *",)  # 默认每小时执行一次
        self.width = self.config.get('width', 1920)
        self.height = self.config.get('height', 1080)
        self.wait_time = self.config.get('wait_time', 5)  # 等待网页加载时间
        self.chat_id = self.config.get('chat_id')
        self.title = self.config.get('title')
        self.executable_path = self.config.get('executable_path',r"C:\Program Files\Google\Chrome\Application\chrome.exe")

        self.temp_job = False
        self.messsage_id = None
        self.task_type = None
        self.task_url = None
        # 创建保存目录
        os.makedirs(self.save_dir, exist_ok=True)

        print(f"网页定时截图程序初始化成功")
        print(f"目标网址: {self.url}")
        print(f"保存目录: {self.save_dir}")
        print(f"Cron表达式: {self.cron_expression}")
        print(f"截图尺寸: {self.width}x{self.height}")
        print(f"等待时间: {self.wait_time}秒")

    def load_config(self,config_file = "config.json"):
        """从JSON文件加载配置"""
        # 默认配置
        default_config = {
            'url': 'https://www.baidu.com',
            'save_dir': './screenshots',
            'cron_expression': '* * */1 * *',
            'width': 1920,
            'height': 1080,
            'wait_time': 5,
            "chat_id": "oc_5e64b13f2a57b78cba6f2c8ae6159b77",
            "title": "【60总装】Andon产量推送"
        }
        # 如果配置文件存在，加载配置
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                print(f"从配置文件 {config_file} 加载配置成功")
                return config
            except Exception as e:
                print(f"加载配置文件失败: {str(e)}")
                print("使用默认配置")
                return default_config
        else:
            # 如果配置文件不存在，创建默认配置文件
            try:
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=4, ensure_ascii=False)
                print(f"创建默认配置文件 {config_file} 成功")
            except Exception as e:
                print(f"创建默认配置文件失败: {str(e)}")
            return default_config

    async def take_screenshot(self):
        """执行网页截图"""
        playwright = None
        browser = None
        self.url = self.task_url if self.temp_job  else self.config.get('url', 'https://www.baidu.com')
        try:
            # 启动playwright
            playwright = await async_playwright().start()

            # 启动headless浏览器
            # 让Playwright自动处理浏览器路径
            browser = await playwright.chromium.launch(
                headless=True,  # 无头模式
                executable_path=self.executable_path,  # 替换为实际路径
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage'
                ]
            )

            # 打开新页面
            page = await browser.new_page()
            # 设置页面视口
            await page.set_viewport_size({"width": self.width, "height": self.height})

            # 访问网页
            print(f"[{datetime.now()}] 正在访问网页: {self.url}")
            await page.goto(self.url, wait_until='networkidle')

            # 等待指定时间确保页面完全加载
            if self.wait_time > 0:
                print(f"[{datetime.now()}] 等待 {self.wait_time} 秒确保页面加载完成")
                await asyncio.sleep(self.wait_time)

            # 生成文件名（包含时间戳）
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"screenshot_{timestamp}.png"
            save_path = os.path.join(self.save_dir, filename)

            # 执行截图
            print(f"[{datetime.now()}] 正在截图...")
            await page.screenshot(
                path=save_path,
                full_page=True,  # 截取整个页面
                type='png'
            )

            print(f"[{datetime.now()}] 截图成功！保存至: {save_path}")


            return True, save_path

        except Exception as e:
            print(f"[{datetime.now()}] 截图失败: {str(e)}")
            return False, str(e)
        finally:
            # 关闭浏览器和playwright
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()

    def job(self):
        """定时任务执行函数"""
        success, result = asyncio.run(self.take_screenshot())
        if success:
            print(f"[{datetime.now()}] Job完成，保存路径: {result}")
            feishu_send_img.main(self.chat_id, result, self.title,f'** 时间: **{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', "")
            return result
        else:
            print(f"[{datetime.now()}] Job失败: {result}")
            return None

    def start(self):
        """启动定时任务"""
        # 立即执行一次截图
        print("\n开始执行首次截图...")
        first_result = self.job()
        print(f"首次截图结果: {'成功' if first_result else '失败'}")

        # 创建后台调度器
        scheduler = BackgroundScheduler()

        # 设置cron表达式定时任务
        print(f"\n设置定时任务，Cron表达式: {self.cron_expression}")
        scheduler.add_job(
            self.job,
            CronTrigger.from_crontab(self.cron_expression),
            id='web_screenshot_job',
            name='网页定时截图任务',
            replace_existing=True
        )

        # 启动调度器
        scheduler.start()
        print("定时任务已启动，按 Ctrl+C 停止\n")

        try:
            # 保持程序运行
            while True:
                time.sleep(0.1)
                if self.temp_job:
                    reply_id = feishu_send_img.send_message_reply(self.messsage_id)
                    success, img_path = asyncio.run(self.take_screenshot())
                    if success:
                        print(f"[{datetime.now()}] 【监听】Job完成，保存路径: {img_path}")
                        feishu_send_img.update_message_reply(reply_id,img_path,self.task_type)

                    else:
                        print(f"[{datetime.now()}] 【监听】Job失败: {img_path}")

                    self.temp_job = False
                    self.messsage_id = None
                    self.task_type = None
                    self.task_url = None
        except KeyboardInterrupt:
            # 停止调度器
            scheduler.shutdown()
            print("\n定时任务已停止")
        except Exception as e:
            scheduler.shutdown()
            print(f"\n程序异常: {str(e)}")


if __name__ == '__main__':
    # 创建截图实例并启动
    screenshot = WebScreenshot()
    screenshot.start()
