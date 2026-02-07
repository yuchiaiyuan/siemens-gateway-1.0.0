#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网页定时截图程序
功能：定时保存指定网页为图片到本地，后台运行无需打开浏览器
"""

import asyncio
import hashlib
import os
import sys
import time
import json
from asyncio import subprocess
from datetime import datetime
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import feishu_send_img


import json
import os
from typing import Dict, List


class CookieManager:
    """Cookie管理器，支持多网站"""

    def __init__(self, cookies_dir: str = './cookies'):
        self.cookies_dir = cookies_dir
        os.makedirs(cookies_dir, exist_ok=True)
        self.cookie_index_file = os.path.join(cookies_dir, 'cookie_index.json')
        self.load_index()

    def load_index(self):
        """加载Cookie索引"""
        if os.path.exists(self.cookie_index_file):
            with open(self.cookie_index_file, 'r') as f:
                self.index = json.load(f)
        else:
            self.index = {}

    def save_index(self):
        """保存Cookie索引"""
        with open(self.cookie_index_file, 'w') as f:
            json.dump(self.index, f, indent=2)

    def get_cookie_key(self, url: str) -> str:
        """根据URL生成Cookie键"""
        parsed = urlparse(url)
        domain = parsed.netloc.split(':')[0]
        path = parsed.path.rstrip('/')
        return f"{domain}{path}"

    def get_cookie_filepath(self, url: str) -> str:
        """获取Cookie文件路径"""
        key = self.get_cookie_key(url)
        filename = f"{hashlib.md5(key.encode()).hexdigest()}.json"
        return os.path.join(self.cookies_dir, filename)

    def save_cookies(self, url: str, cookies: List[Dict]):
        """保存网站的Cookie"""
        filepath = self.get_cookie_filepath(url)
        key = self.get_cookie_key(url)

        # 保存Cookie数据
        with open(filepath, 'w') as f:
            json.dump({
                'url': url,
                'key': key,
                'timestamp': datetime.now().isoformat(),
                'cookies': cookies
            }, f, indent=2)

        # 更新索引
        self.index[key] = {
            'url': url,
            'filepath': filepath,
            'timestamp': datetime.now().isoformat(),
            'cookies_count': len(cookies)
        }
        self.save_index()

        print(f"[{datetime.now()}] 已保存 {len(cookies)} 个Cookie到 {filepath}")
        return filepath

    def load_cookies(self, url: str) -> List[Dict]:
        """加载网站的Cookie"""
        filepath = self.get_cookie_filepath(url)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                print(f"[{datetime.now()}] 从 {filepath} 加载了 {len(data['cookies'])} 个Cookie")
                return data['cookies']
            except Exception as e:
                print(f"[{datetime.now()}] 加载Cookie失败: {str(e)}")
        return []

    def list_all_cookies(self):
        """列出所有已保存的Cookie"""
        print(f"\n已保存Cookie的网站列表:")
        for key, info in self.index.items():
            print(f"  - {info['url']} ({info['cookies_count']}个Cookie, 更新于: {info['timestamp']})")

class WebScreenshot:
    def __init__(self):
        self.config = self.load_config()
        self.cookie_manager = CookieManager()
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
        self.url = self.task_url if self.temp_job else self.config.get('url', 'https://www.baidu.com')

        try:
            # 启动playwright
            playwright = await async_playwright().start()

            # 启动浏览器（可以设置为非无头模式用于调试）
            browser = await playwright.chromium.launch(
                headless=True,
                executable_path=self.executable_path,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled'  # 避免被检测为自动化
                ]
            )

            # 创建上下文并设置持久化存储
            context = await browser.new_context(
                viewport={"width": self.width, "height": self.height},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )


            # 加载已保存的Cookie（如果有）
            cookies_path = os.path.join(os.path.dirname(__file__), 'cookies.json')
            if os.path.exists(cookies_path):
                try:
                    with open(cookies_path, 'r') as f:
                        cookies = json.load(f)
                    # ----------- 使用CookieManager -----------
                    cookies = self.cookie_manager.load_cookies(self.url)
                    if cookies:
                        await context.add_cookies(cookies)
                    # await context.add_cookies(cookies)
                    print(f"[{datetime.now()}] 已加载 {len(cookies)} 个Cookie")
                except Exception as e:
                    print(f"[{datetime.now()}] 加载Cookie失败: {str(e)}")

            page = await context.new_page()

            # 访问网页
            print(f"[{datetime.now()}] 正在访问网页: {self.url}")
            await page.goto(self.url, wait_until='networkidle')

            # 检查是否需要登录（根据页面元素判断）
            need_login = await self.check_login_needed(page)

            if need_login:
                print(f"[{datetime.now()}] 检测到需要登录，执行登录流程...")
                login_success = await self.do_login(page)

                if login_success:
                    # 保存Cookie供下次使用
                    cookies = await context.cookies()
                    # ------------- 统一管理 cookies ------------
                    self.cookie_manager.save_cookies(self.url, cookies)
                    with open(cookies_path, 'w') as f:
                        json.dump(cookies, f)
                    print(f"[{datetime.now()}] 登录成功，已保存Cookie")
                else:
                    print(f"[{datetime.now()}] 登录失败")
                    return False, "登录失败"

            # 等待指定时间确保页面完全加载
            if self.wait_time > 0:
                print(f"[{datetime.now()}] 等待 {self.wait_time} 秒确保页面加载完成")
                await asyncio.sleep(self.wait_time)

            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"screenshot_{timestamp}.png"
            save_path = os.path.join(self.save_dir, filename)

            # 执行截图
            print(f"[{datetime.now()}] 正在截图...")
            await page.screenshot(
                path=save_path,
                full_page=True,
                type='png'
            )

            print(f"[{datetime.now()}] 截图成功！保存至: {save_path}")
            return True, save_path

        except Exception as e:
            print(f"[{datetime.now()}] 截图失败: {str(e)}")
            return False, str(e)
        finally:
            if browser:
                await browser.close()
            if playwright:
                await playwright.stop()

    async def check_login_needed(self, page):
        """检查页面是否需要登录"""
        try:
            if 'ignition' in self.url:
                return False
            '''# 方法1：检查登录按钮或登录表单是否存在
            login_selectors = [
                'button:has-text("登录")',
                'button:has-text("Sign in")',
                'button:has-text("Log in")',
                'a[href*="login"]',
                'a[href*="signin"]',
                'input[name="username"]',
                'input[name="email"]',
                'input[type="password"]'
            ]

            for selector in login_selectors:
                if await page.query_selector(selector):
                    return True

            # 方法2：检查特定文本（如"请登录"、"需要登录"等）
            login_texts = ["请登录", "登录", "Sign in", "Log in", "Login required"]
            for text in login_texts:
                if await page.get_by_text(text).count() > 0:
                    return True'''

            # 方法3：检查URL是否包含登录相关路径
            if "account.lixiang.com" in page.url.lower():
                return True

            return False
        except Exception:
            return False

    async def do_login(self, page):
        """执行登录操作"""
        try:
            # 从配置文件获取登录凭据
            login_config = self.config.get('login', {})
            username = login_config.get('username','yuaiyuan')
            password = login_config.get('password','Li20201009*8')
            login_url = login_config.get('login_url','https://account.lixiang.com/login')

            if not username or not password:
                print(f"[{datetime.now()}] 未配置登录凭据")
                return False

            # 如果有专门的登录页面URL，先跳转到登录页面
            if login_url:
                print(f"[{datetime.now()}] 跳转到登录页面: {login_url}")
                await page.goto(login_url, wait_until='networkidle')
                await asyncio.sleep(2)

            # 尝试不同的登录表单填充方式

            # 方式1：通过输入框名称填充
            selectors = {
                'username': [
                    'input[name="username"]',
                    'input[name="email"]',
                    'input[name="user"]',
                    'input[type="email"]',
                    'input[placeholder*="邮箱"]',
                    'input[placeholder*="账号"]',
                    'input[placeholder*="域账号"]',
                    'input[placeholder*="用户名"]',
                    'input[id*="username"]',
                    'input[id*="email"]'
                ],
                'password': [
                    'input[name="password"]',
                    'input[type="password"]',
                    'input[placeholder*="密码"]',
                    'input[id*="password"]'
                ]
            }

            # 查找并填充用户名
            username_filled = False
            for selector in selectors['username']:
                try:
                    username_field = await page.wait_for_selector(selector, timeout=3000)
                    await username_field.fill(username)
                    username_filled = True
                    print(f"[{datetime.now()}] 已填充用户名")
                    break
                except:
                    continue

            # 查找并填充密码
            password_filled = False
            for selector in selectors['password']:
                try:
                    password_field = await page.wait_for_selector(selector, timeout=3000)
                    await password_field.fill(password)
                    password_filled = True
                    print(f"[{datetime.now()}] 已填充密码")
                    break
                except:
                    continue

            if not username_filled or not password_filled:
                print(f"[{datetime.now()}] 未找到用户名或密码输入框,尝试不登录...")
                #return False

            # 查找并点击登录按钮
            login_button_selectors = [
                'button[type="submit"]',
                'button:has-text("登录")',
                'button:has-text("Sign in")',
                'button:has-text("Log in")',
                'input[type="submit"]',
                'button.btn-login'
            ]

            login_clicked = False
            for selector in login_button_selectors:
                try:
                    login_button = await page.wait_for_selector(selector, timeout=3000)
                    await login_button.click()
                    login_clicked = True
                    print(f"[{datetime.now()}] 已点击登录按钮")
                    break
                except:
                    continue

            # 等待登录完成
            await asyncio.sleep(3)

            # 检查登录是否成功
            # 方法1：检查URL变化（离开登录页面）
            if login_url and page.url != login_url:
                return True

            # 方法2：检查登录成功后的元素
            success_selectors = [
                'text="登录成功"',
                'text="Welcome"',
                'text="Dashboard"',
                'text="首页"',
                '.user-avatar',
                '.logout-btn'
            ]

            for selector in success_selectors:
                try:
                    if await page.wait_for_selector(selector, timeout=5000):
                        return True
                except:
                    continue

            # 方法3：检查是否有错误消息
            error_selectors = [
                'text="登录失败"',
                'text="Invalid"',
                'text="错误"',
                '.error-message',
                '.alert-danger'
            ]

            for selector in error_selectors:
                if await page.query_selector(selector):
                    print(f"[{datetime.now()}] 检测到登录错误")
                    return False

            # 默认返回成功（如果没检测到明显错误）
            return True

        except Exception as e:
            print(f"[{datetime.now()}] 登录过程中发生错误: {str(e)}")
            return False

    '''async def take_screenshot(self):
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
                await playwright.stop()'''

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
