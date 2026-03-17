# -*- coding: utf-8 -*-
"""
星枢结果监听器 - Result Receiver
监听 results.xingshu 队列，接收并处理子 Agent 返回的结果
"""

import pika
import json
import logging
import signal
import sys
import os
import subprocess
from datetime import datetime
from config import RABBITMQ_CONFIG, get_queue_name

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ResultReceiver:
    """星枢结果接收器"""
    
    def __init__(self, agent_name: str = "xingshu"):
        self.agent_name = agent_name
        self.queue_name = get_queue_name(agent_name, "results")
        self.connection = None
        self.channel = None
        self.should_stop = False
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        logger.info(f"收到退出信号，正在关闭...")
        self.should_stop = True
        if self.connection and self.connection.is_open:
            self.connection.close()
    
    def connect(self):
        """连接到 RabbitMQ"""
        credentials = pika.PlainCredentials(
            RABBITMQ_CONFIG["username"],
            RABBITMQ_CONFIG["password"]
        )
        parameters = pika.ConnectionParameters(
            host=RABBITMQ_CONFIG["host"],
            port=RABBITMQ_CONFIG["port"],
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300
        )
        
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        
        # 声明队列
        self.channel.queue_declare(queue=self.queue_name, durable=True)
        
        # 每次只处理一条消息
        self.channel.basic_qos(prefetch_count=1)
        
        logger.info(f"✅ 已连接到 RabbitMQ: {RABBITMQ_CONFIG['host']}")
        logger.info(f"📬 监听队列: {self.queue_name}")
    
    def on_message(self, channel, method, properties, body):
        """消息处理回调"""
        try:
            result_message = json.loads(body)
            self.process_result(result_message)
            
            # ACK 确认
            channel.basic_ack(delivery_tag=method.delivery_tag)
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 解析失败: {e}")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            logger.error(f"❌ 处理失败: {e}")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def process_result(self, message: dict):
        """处理结果消息"""
        task_id = message.get("taskId", "unknown")
        source = message.get("source", "unknown")
        status = message.get("status", "unknown")
        content = message.get("content", {})
        completed_at = message.get("metadata", {}).get("completedAt", "")
        
        logger.info(f"📥 收到结果: {task_id} from {source}")
        
        # 格式化输出到控制台
        print("\n" + "="*60)
        print(f"📋 任务 ID: {task_id}")
        print(f"👤 执行 Agent: {source}")
        print(f"📊 状态: {status}")
        print(f"⏰ 完成时间: {completed_at}")
        print("-"*60)
        
        # 根据不同 action 格式化输出
        action = content.get("action", "unknown")
        if action == "monitor":
            self._format_monitor_result(content)
        else:
            # 默认输出
            summary = content.get("message", "")
            print(f"📝 结果: {summary}")
            
            # 如果有详细结果
            if "result" in content:
                print("\n📊 详细结果:")
                result = content["result"]
                if isinstance(result, dict):
                    for key, value in result.items():
                        print(f"   {key}: {value}")
                else:
                    print(f"   {result}")
        
        print("="*60 + "\n")
        
        # 推送结果到当前 OpenClaw 会话
        push_message = self.format_result_for_push(message)
        self.push_to_session(push_message)
    
    def _format_monitor_result(self, content: dict):
        """格式化监控结果"""
        result = content.get("result", {})
        
        # 内存信息
        if "memory" in result:
            print("\n💾 内存使用情况:")
            print(result["memory"])
        
        # 磁盘信息
        if "disk" in result:
            print("\n💿 磁盘使用情况:")
            print(result["disk"])
        
        # CPU 信息
        if "cpu" in result:
            print("\n🖥️ CPU 使用情况:")
            print(result["cpu"])
        
        # 运行时间
        if "uptime" in result:
            print(f"\n⏱️ 运行时间: {result['uptime']}")
    
    def get_active_session(self) -> str:
        """获取当前活动的 OpenClaw 会话 ID"""
        try:
            # 优先使用环境变量中的会话 ID
            if os.environ.get("OPENCLAW_SESSION"):
                return os.environ.get("OPENCLAW_SESSION")
            
            # 使用 openclaw sessions 获取活动会话 (5分钟内活跃)
            result = subprocess.run(
                ["openclaw", "sessions", "--json", "--active", "5"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout:
                sessions = json.loads(result.stdout)
                if sessions and len(sessions) > 0:
                    # 返回第一个活动会话
                    return sessions[0].get("sessionKey", sessions[0].get("session_id", ""))
            
            logger.warning("⚠️ 未找到活动会话")
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ 获取活动会话失败: {e}")
            return None
    
    def push_to_session(self, message: str):
        """推送消息到当前 OpenClaw 会话"""
        # 优先使用环境变量中配置的推送方式
        push_url = os.environ.get("ASYNC_TASK_PUSH_URL")
        auth_token = os.environ.get("ASYNC_TASK_AUTH_TOKEN")
        
        # 方式1: 使用自定义 HTTP endpoint
        if push_url:
            return self._push_to_http_endpoint(message, push_url, auth_token)
        
        # 方式2: 使用 Telegram bot 发送到用户
        return self._push_to_telegram(message)
    
    def _push_to_http_endpoint(self, message: str, url: str, token: str = None) -> bool:
        """推送到自定义 HTTP endpoint"""
        import urllib.request
        import urllib.parse
        
        try:
            data = {
                "content": message,
                "role": "assistant"
            }
            
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode('utf-8'),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}" if token else ""
                }
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    logger.info(f"✅ 已推送到 HTTP endpoint")
                    return True
                else:
                    logger.error(f"❌ HTTP push failed: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ HTTP push error: {e}")
            return False
    
    def _push_to_telegram(self, message: str) -> bool:
        """通过 Telegram 机器人推送消息到用户"""
        # 从环境变量获取 Telegram 配置
        telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        telegram_target = os.environ.get("TELEGRAM_TARGET", "5038825565")  # 默认发送到比利哥
        
        if not telegram_token:
            # 尝试从配置文件读取
            try:
                import yaml
                config_path = os.path.expanduser("~/.openclaw/config.yaml")
                if os.path.exists(config_path):
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                        telegram_token = config.get('channels', {}).get('telegram', {}).get('bot_token')
            except:
                pass
        
        if not telegram_token:
            logger.warning("⚠️ 无法推送：未配置 Telegram bot token")
            return False
        
        try:
            import urllib.request
            import urllib.parse
            
            # 发送消息到 Telegram
            url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            data = {
                "chat_id": telegram_target,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode('utf-8'),
                headers={"Content-Type": "application/json"}
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                if result.get("ok"):
                    logger.info(f"✅ 已推送到 Telegram: {telegram_target}")
                    return True
                else:
                    logger.error(f"❌ Telegram push failed: {result}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Telegram push error: {e}")
            return False
    
    def format_result_for_push(self, message: dict) -> str:
        """格式化结果为推送到会话的消息"""
        task_id = message.get("taskId", "unknown")
        source = message.get("source", "unknown")
        status = message.get("status", "unknown")
        content = message.get("content", {})
        
        # 根据状态选择 emoji
        status_emoji = {
            "success": "✅",
            "failed": "❌",
            "error": "❌",
            "pending": "⏳"
        }.get(status, "📋")
        
        # 构建消息
        lines = [
            f"📥 **任务结果** {status_emoji}",
            f"",
            f"**Task ID**: `{task_id}`",
            f"**执行者**: {source}",
            f"**状态**: {status}",
            ""
        ]
        
        # 根据 action 添加内容
        action = content.get("action", "unknown")
        
        if action == "personal":
            # 日程/提醒结果
            reminder_content = content.get("params", {}).get("content", "")
            reminder_time = content.get("params", {}).get("time", "")
            result_msg = content.get("message", "")
            lines.append(f"**提醒内容**: {reminder_content}")
            lines.append(f"**提醒时间**: {reminder_time}")
            if result_msg:
                lines.append(f"**结果**: {result_msg}")
        
        elif action == "monitor":
            # 监控结果
            result = content.get("result", {})
            if "memory" in result:
                lines.append(f"**内存**: {result['memory']}")
            if "uptime" in result:
                lines.append(f"**运行时间**: {result['uptime']}")
        
        elif action == "ops":
            # 运维操作结果
            operation = content.get("params", {}).get("operation", "")
            service = content.get("params", {}).get("service", "")
            result_msg = content.get("message", "")
            lines.append(f"**操作**: {operation}")
            lines.append(f"**服务**: {service}")
            if result_msg:
                lines.append(f"**结果**: {result_msg}")
        
        else:
            # 默认处理
            result_msg = content.get("message", "") or content.get("summary", "")
            if result_msg:
                lines.append(f"**结果**: {result_msg}")
        
        return "\n".join(lines)
    
    def start_listening(self):
        """开始监听"""
        logger.info(f"🚀 星枢开始监听结果队列...")
        
        self.channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=self.on_message
        )
        
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("收到中断信号，停止监听")
            self.channel.stop_consuming()
        finally:
            if self.connection and self.connection.is_open:
                self.connection.close()
            logger.info("👋 结果监听器已关闭")


def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="星枢结果监听器")
    parser.add_argument("--agent", default="xingshu", help="Agent 名称")
    parser.add_argument("--host", default=None, help="RabbitMQ 地址")
    
    args = parser.parse_args()
    
    receiver = ResultReceiver(agent_name=args.agent)
    receiver.connect()
    receiver.start_listening()


if __name__ == "__main__":
    main()
