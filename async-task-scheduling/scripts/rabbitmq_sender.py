# -*- coding: utf-8 -*-
"""
RabbitMQ 发送模块 - RabbitMQ Sender
连接到 RabbitMQ 并发送消息
"""

import pika
import json
import logging
from datetime import datetime
from typing import Dict, Optional

# 导入配置
from config import RABBITMQ_CONFIG

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RabbitMQSender:
    """RabbitMQ 消息发送器"""
    
    # 默认配置从 config.py 读取
    DEFAULT_CONFIG = RABBITMQ_CONFIG
    
    def __init__(self, config: Dict = None):
        """
        初始化 RabbitMQ 发送器
        
        Args:
            config: RabbitMQ 配置，包含 host, port, username, password 等
        """
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        self.connection = None
        self.channel = None
        self._connect()
    
    def _connect(self):
        """建立 RabbitMQ 连接"""
        credentials = pika.PlainCredentials(
            self.config["username"],
            self.config["password"]
        )
        
        parameters = pika.ConnectionParameters(
            host=self.config["host"],
            port=self.config["port"],
            credentials=credentials,
            heartbeat=self.config["heartbeat"],
            blocked_connection_timeout=self.config["blocked_connection_timeout"]
        )
        
        try:
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # 声明交换机
            self.channel.exchange_declare(
                exchange=self.config["exchange"],
                exchange_type="topic",
                durable=True
            )
            self.channel.exchange_declare(
                exchange=self.config["result_exchange"],
                exchange_type="topic",
                durable=True
            )
            
            logger.info(f"✅ RabbitMQ 连接成功: {self.config['host']}:{self.config['port']}")
            
        except Exception as e:
            logger.error(f"❌ RabbitMQ 连接失败: {e}")
            raise
    
    def send_task(self, message: Dict, priority: str = None) -> str:
        """
        发送任务消息
        
        Args:
            message: 任务消息 (由 MessageBuilder 构建)
            priority: 优先级覆盖 (high/normal/low)
            
        Returns:
            task_id
        """
        if "error" in message:
            raise ValueError(f"无法发送错误消息: {message['error']}")
        
        target = message.get("target", "unknown")
        task_id = message.get("taskId", "unknown")
        routing_key = f"task.{target}"
        
        # 确定优先级
        priority_value = self._get_priority_value(
            priority or message.get("priority", "normal")
        )
        
        try:
            self.channel.basic_publish(
                exchange=self.config["exchange"],
                routing_key=routing_key,
                body=json.dumps(message, ensure_ascii=False),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # 消息持久化
                    content_type="application/json",
                    priority=priority_value,
                    timestamp=int(datetime.now().timestamp())
                )
            )
            
            logger.info(f"✅ 任务已发送: {task_id} -> {target} (routing: {routing_key})")
            return task_id
            
        except Exception as e:
            logger.error(f"❌ 发送任务失败: {e}")
            raise
    
    def send_result(self, message: Dict) -> str:
        """
        发送结果消息
        
        Args:
            message: 结果消息 (由 MessageBuilder 构建)
            
        Returns:
            task_id
        """
        source = message.get("source", "unknown")
        task_id = message.get("taskId", "unknown")
        routing_key = f"result.{source}"
        
        try:
            self.channel.basic_publish(
                exchange=self.config["result_exchange"],
                routing_key=routing_key,
                body=json.dumps(message, ensure_ascii=False),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json"
                )
            )
            
            logger.info(f"✅ 结果已发送: {task_id} from {source}")
            return task_id
            
        except Exception as e:
            logger.error(f"❌ 发送结果失败: {e}")
            raise
    
    def send_heartbeat(self, message: Dict) -> bool:
        """
        发送心跳消息
        
        Args:
            message: 心跳消息
            
        Returns:
            是否发送成功
        """
        agent = message.get("agent", "unknown")
        routing_key = f"heartbeat.{agent}"
        
        try:
            self.channel.basic_publish(
                exchange=self.config["exchange"],
                routing_key=routing_key,
                body=json.dumps(message, ensure_ascii=False),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json"
                )
            )
            
            logger.debug(f"💓 心跳已发送: {agent}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 发送心跳失败: {e}")
            return False
    
    def _get_priority_value(self, priority: str) -> int:
        """将优先级字符串转换为 RabbitMQ 数值"""
        priority_map = {
            "high": 10,
            "normal": 5,
            "low": 1
        }
        return priority_map.get(priority.lower(), 5)
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.connection is not None and self.connection.is_open
    
    def reconnect(self):
        """重新连接"""
        self.close()
        self._connect()
    
    def close(self):
        """关闭连接"""
        if self.connection and self.connection.is_open:
            self.connection.close()
            logger.info("🔌 RabbitMQ 连接已关闭")


# 便捷函数
def send_task_quick(message: Dict, config: Dict = None) -> str:
    """
    快速发送任务 (自动创建和关闭连接)
    
    Args:
        message: 任务消息
        config: RabbitMQ 配置
        
    Returns:
        task_id
    """
    sender = RabbitMQSender(config)
    task_id = sender.send_task(message)
    sender.close()
    return task_id


# 测试
if __name__ == "__main__":
    from message_builder import MessageBuilder
    from intent_parser import IntentParser
    
    # 解析意图
    parser = IntentParser()
    intent = parser.parse_intent("帮我审查 my-project 仓库")
    
    # 构建消息
    builder = MessageBuilder()
    message = builder.build_task_message(intent)
    
    # 发送 (需要配置实际的 RabbitMQ 地址)
    # sender = RabbitMQSender({"host": "192.168.1.100", "username": "admin", "password": "password"})
    # task_id = sender.send_task(message)
    # sender.close()
    
    print("消息构建成功:")
    print(builder.to_json(message))
