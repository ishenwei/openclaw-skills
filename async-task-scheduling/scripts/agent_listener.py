# -*- coding: utf-8 -*-
"""
Agent 监听模块 - Agent Listener
子 Agent 持续监听 RabbitMQ 队列并执行任务
"""

import pika
import json
import logging
import subprocess
import time
import signal
import sys
from datetime import datetime

# 导入配置
from config import RABBITMQ_CONFIG, get_queue_name

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AgentListener:
    """Agent 任务监听器"""
    
    def __init__(self, agent_name: str, rabbitmq_host: str = None,
                 username: str = None, password: str = None):
        self.agent_name = agent_name
        self.queue_name = get_queue_name(agent_name, "tasks")
        
        # 使用传入的参数或默认配置
        self.rabbitmq_host = rabbitmq_host or RABBITMQ_CONFIG["host"]
        self.username = username or RABBITMQ_CONFIG["username"]
        self.password = password or RABBITMQ_CONFIG["password"]
        
        self.connection = None
        self.channel = None
        self.should_stop = False
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """处理退出信号"""
        logger.info(f"收到退出信号，正在关闭...")
        self.should_stop = True
        if self.connection and self.connection.is_open:
            self.connection.close()
    
    def connect(self):
        """连接到 RabbitMQ"""
        credentials = pika.PlainCredentials(self.username, self.password)
        parameters = pika.ConnectionParameters(
            host=self.rabbitmq_host,
            port=5672,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300
        )
        
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        
        # 声明队列 (确保存在)
        self.channel.queue_declare(queue=self.queue_name, durable=True)
        
        # 每次只处理一条消息
        self.channel.basic_qos(prefetch_count=1)
        
        logger.info(f"✅ 已连接到 RabbitMQ: {self.rabbitmq_host}")
        logger.info(f"📬 监听队列: {self.queue_name}")
    
    def execute_task(self, task_message: dict) -> dict:
        """
        执行任务的核心逻辑
        直接调用 OpenClaw Agent 执行星枢发过来的原始任务信息
        """
        content = task_message.get("content", {})
        task_id = task_message.get("taskId", "unknown")
        
        # 获取原始任务信息作为 message
        original_message = self._get_original_message(task_message)
        
        logger.info(f"🔄 执行任务: {task_id}")
        logger.info(f"📝 原始任务: {original_message[:100]}...")
        
        # 通过 OpenClaw Agent 执行
        try:
            result = self._execute_via_openclaw(original_message)
            return {
                "status": "success",
                "result": result
            }
        except Exception as e:
            logger.error(f"❌ 任务执行失败: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def _get_original_message(self, task_message: dict) -> str:
        """获取原始任务信息，构建为自然语言消息"""
        content = task_message.get("content", {})
        action = content.get("action", "")
        
        # 直接使用原始 action 构建消息
        parts = []
        
        # 添加动作
        if action:
            parts.append(f"action={action}")
        
        
        # 如果没有内容，使用默认
        if not parts:
            return "执行任务"
        
        return " ".join(parts)
    
    def _execute_via_openclaw(self, message: str) -> dict:
        """通过 OpenClaw Agent 执行任务
        
        构建命令: openclaw agent --agent {self.agent_name} --message "..." --deliver
        """
        # 构建命令
        cmd = [
            "openclaw", "agent",
            "--agent", self.agent_name,
            "--message", message,
            "--deliver"  # 添加 --deliver 让结果返回到 Telegram
        ]
        
        logger.info(f"🚀 执行命令: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120  # 2分钟超时
            )
            
            return {
                "message": message,
                "output": result.stdout,
                "error": result.stderr,
                "return_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "message": message,
                "error": "命令执行超时（2分钟）"
            }
        except Exception as e:
            return {
                "message": message,
                "error": str(e)
            }
    

    
    # === 消息处理 ===
    
    def on_message(self, channel, method, properties, body):
        """消息处理回调"""
        try:
            task_message = json.loads(body)
            task_id = task_message.get("taskId", "unknown")
            
            logger.info(f"📥 收到任务: {task_id}")
            
            # 执行任务
            result = self.execute_task(task_message)
            
            # 发送结果
            self.send_result(task_id, result)
            
            # ACK 确认
            channel.basic_ack(delivery_tag=method.delivery_tag)
            logger.info(f"✅ 任务完成: {task_id}")
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 解析失败: {e}")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            logger.error(f"❌ 处理失败: {e}")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def send_result(self, task_id: str, result: dict):
        """发送结果到 RabbitMQ"""
        result_message = {
            "taskId": task_id,
            "type": "result",
            "source": self.agent_name,
            "target": "xingshu",
            "status": result.get("status", "unknown"),
            "content": result,
            "metadata": {
                "completedAt": datetime.now().isoformat() + "Z"
            }
        }
        
        self.channel.basic_publish(
            exchange="result_exchange",
            routing_key=f"result.{self.agent_name}",
            body=json.dumps(result_message, ensure_ascii=False),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        
        logger.info(f"📤 结果已发送: {task_id} -> result.{self.agent_name}")
    
    def start_listening(self):
        """开始监听任务队列"""
        logger.info(f"🚀 {self.agent_name} 开始监听...")
        
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
            logger.info("👋 监听器已关闭")


# === 主程序 ===

def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Agent 任务监听器")
    parser.add_argument("agent_name", help="Agent 名称 (如 yunce, xingyao)")
    parser.add_argument("--host", default="192.168.3.189", help="RabbitMQ 地址")
    parser.add_argument("--username", default="guest", help="RabbitMQ 用户名")
    parser.add_argument("--password", default="guest", help="RabbitMQ 密码")
    
    args = parser.parse_args()
    
    listener = AgentListener(
        agent_name=args.agent_name,
        rabbitmq_host=args.host,
        username=args.username,
        password=args.password
    )
    
    listener.connect()
    listener.start_listening()


if __name__ == "__main__":
    main()
