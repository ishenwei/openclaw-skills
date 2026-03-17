# -*- coding: utf-8 -*-
"""
RabbitMQ 初始化脚本
用于创建 Exchanges 和 Queues

用法:
    python3 setup_rabbitmq.py
    python3 setup_rabbitmq.py --host 192.168.3.189 --username guest --password guest

配置:
    也可以通过环境变量设置:
    - RABBITMQ_HOST
    - RABBITMQ_PORT
    - RABBITMQ_USER
    - RABBITMQ_PASS
"""

import pika
import argparse
import sys

# 导入配置
from config import RABBITMQ_CONFIG, QUEUES, AGENT_ROLES


def setup_rabbitmq(host=None, username=None, password=None):
    """初始化 RabbitMQ"""
    
    # 使用传入参数或默认配置
    host = host or RABBITMQ_CONFIG["host"]
    username = username or RABBITMQ_CONFIG["username"]
    password = password or RABBITMQ_CONFIG["password"]
    
    print(f"🔌 连接到 RabbitMQ: {host}:5672")
    
    # 连接
    credentials = pika.PlainCredentials(username, password)
    parameters = pika.ConnectionParameters(
        host=host,
        port=5672,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300
    )
    
    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        print("✅ 连接成功!")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        sys.exit(1)
    
    # ========== 1. 创建 Exchange ==========
    print("\n📦 创建 Exchanges...")
    
    channel.exchange_declare(
        exchange='task_exchange',
        exchange_type='topic',
        durable=True
    )
    print("   ✅ task_exchange (topic)")
    
    channel.exchange_declare(
        exchange='result_exchange',
        exchange_type='topic',
        durable=True
    )
    print("   ✅ result_exchange (topic)")
    
    # ========== 2. 创建任务队列 ==========
    print("\n📬 创建任务队列...")
    
    for agent_id in QUEUES["tasks"]:
        agent_name = AGENT_ROLES.get(agent_id, agent_id)
        queue_name = get_queue_name(agent_id, "tasks")
        routing_key = f"task.{agent_id}"
        
        channel.queue_declare(queue=queue_name, durable=True)
        channel.queue_bind(
            exchange='task_exchange',
            queue=queue_name,
            routing_key=routing_key
        )
        print(f"   ✅ {queue_name} -> {routing_key} ({agent_name})")
    
    print("\n📥 创建结果队列...")
    
    result_queue = QUEUES["results"]
    channel.queue_declare(queue=get_queue_name(result_queue, "results"), durable=True)
    channel.queue_bind(
        exchange='result_exchange',
        queue=get_queue_name(result_queue, "results"),
        routing_key='result.#'
    )
    print(f"   ✅ results.{result_queue} -> result.# ({AGENT_ROLES.get(result_queue, result_queue)}结果收集)")
    
    # 完成
    connection.close()
    
    print("\n" + "="*50)
    print("🎉 RabbitMQ 初始化完成!")
    print("="*50)
    print("\n📋 队列列表:")
    print("   - tasks.xingyao")
    print("   - tasks.xinghui")
    print("   - tasks.yunhan")
    print("   - tasks.yunce")
    print("   - tasks.yunjiang")
    print("   - tasks.yunzhi")
    print("   - tasks.fengheng")
    print("   - tasks.fengchi")
    print("   - tasks.fengji")
    print("   - results.xingshu")
    print(f"\n🌐 管理界面: http://{host}:15672/")
    print(f"   用户名: {username}")
    print("="*50)


def main():
    parser = argparse.ArgumentParser(description='RabbitMQ 初始化脚本')
    parser.add_argument('--host', default=None, help='RabbitMQ 地址 (默认: 配置文件中)')
    parser.add_argument('--username', default=None, help='用户名 (默认: 配置文件中)')
    parser.add_argument('--password', default=None, help='密码 (默认: 配置文件中)')
    
    args = parser.parse_args()
    
    setup_rabbitmq(
        host=args.host,
        username=args.username,
        password=args.password
    )


if __name__ == '__main__':
    main()
