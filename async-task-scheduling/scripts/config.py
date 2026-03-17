# -*- coding: utf-8 -*-
"""
RabbitMQ 配置文件
集中管理 RabbitMQ 连接配置
"""

import os

# RabbitMQ 连接配置
RABBITMQ_CONFIG = {
    "host": os.environ.get("RABBITMQ_HOST", "192.168.3.189"),
    "port": int(os.environ.get("RABBITMQ_PORT", "5672")),
    "username": os.environ.get("RABBITMQ_USER", "guest"),
    "password": os.environ.get("RABBITMQ_PASS", "guest"),
    "exchange": "task_exchange",
    "result_exchange": "result_exchange",
    "heartbeat": 600,
    "blocked_connection_timeout": 300
}

# Queue 配置
QUEUES = {
    "tasks": [
        "xingyao",    # 星曜 - IT管家
        "xinghui",    # 星辉 - 个人助理
        "yunhan",     # 云瀚 - 监控官
        "yunce",      # 云策 - 架构师
        "yunjiang",   # 云匠 - 工匠
        "yunzhi",     # 云织 - 自动化师
        "fengheng",   # 风衡 - 质检官
        "fengchi",    # 风驰 - 执行者
        "fengji",     # 风纪 - 审计官
    ],
    "results": "xingshu"  # 星枢结果收集
}

# Agent 角色映射
AGENT_ROLES = {
    "xingyao": "星曜 - IT管家",
    "xinghui": "星辉 - 个人助理",
    "yunhan": "云瀚 - 监控官",
    "yunce": "云策 - 架构师",
    "yunjiang": "云匠 - 工匠",
    "yunzhi": "云织 - 自动化师",
    "fengheng": "风衡 - 质检官",
    "fengchi": "风驰 - 执行者",
    "fengji": "风纪 - 审计官",
    "xingshu": "星枢 - 总调度"
}

# Action 到 Agent 的映射
ACTION_TO_AGENT = {
    # 快捷指令
    "code_review": "yunce",
    "deploy": "yunzhi",
    "status_check": "yunhan",
    
    # 标准指令
    "ops": "xingyao",
    "personal": "xinghui",
    "monitor": "yunhan",
    "architecture": "yunce",
    "coding": "yunjiang",
    "automation": "yunzhi",
    "qa_test": "fengheng",
    "execute": "fengchi",
    "audit": "fengji"
}


def get_rabbitmq_url():
    """获取 RabbitMQ 连接 URL"""
    return f"amqp://{RABBITMQ_CONFIG['username']}:{RABBITMQ_CONFIG['password']}@{RABBITMQ_CONFIG['host']}:{RABBITMQ_CONFIG['port']}/"


def get_queue_name(agent_id, queue_type="tasks"):
    """获取队列名称"""
    if queue_type == "tasks":
        return f"tasks.{agent_id}"
    elif queue_type == "results":
        return f"results.{agent_id}"
    return queue_type


def get_routing_key(agent_id, key_type="task"):
    """获取 routing key"""
    return f"{key_type}.{agent_id}"
