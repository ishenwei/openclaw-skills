# -*- coding: utf-8 -*-
"""
快速查看结果 - Quick Result Viewer
不持续监听，直接查看队列中的消息
"""

import pika
import json
from config import RABBITMQ_CONFIG, get_queue_name


def view_results(agent_name: str = "xingshu", count: int = 10):
    """查看结果队列中的消息"""
    
    queue_name = get_queue_name(agent_name, "results")
    
    credentials = pika.PlainCredentials(
        RABBITMQ_CONFIG["username"],
        RABBITMQ_CONFIG["password"]
    )
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_CONFIG["host"],
        port=RABBITMQ_CONFIG["port"],
        credentials=credentials
    )
    
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    
    # 获取队列信息
    queue = channel.queue_declare(queue=queue_name, passive=True)
    message_count = queue.method.message_count
    
    print(f"\n📬 队列: {queue_name}")
    print(f"📊 待处理消息: {message_count}")
    print("="*60)
    
    if message_count == 0:
        print("✅ 没有待处理的消息")
        connection.close()
        return
    
    # 读取消息 (不 ACK)
    for i in range(min(message_count, count)):
        method, properties, body = channel.basic_get(queue=queue_name, auto_ack=False)
        
        if body:
            try:
                message = json.loads(body)
                _print_message(message, i+1)
                # 不 ACK，消息会保留在队列中
            except json.JSONDecodeError:
                print(f"❌ 消息 {i+1}: JSON 解析失败")
    
    connection.close()
    print("\n💡 提示: 以上消息未 ACK，如需处理请运行 result_receiver.py")


def _print_message(message: dict, index: int):
    """格式化打印消息"""
    task_id = message.get("taskId", "unknown")
    source = message.get("source", "unknown")
    status = message.get("status", "unknown")
    content = message.get("content", {})
    
    print(f"\n📋 [{index}] Task ID: {task_id}")
    print(f"   👤 来源: {source}")
    print(f"   📊 状态: {status}")
    
    # 根据类型打印内容
    if content.get("action") == "monitor":
        result = content.get("result", {})
        if "memory" in result:
            print(f"   💾 内存: {result['memory'].split(chr(10))[0]}")
        if "uptime" in result:
            print(f"   ⏱️ 运行: {result['uptime'].strip()}")
    else:
        summary = content.get("message", "")
        if summary:
            print(f"   📝 {summary}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="快速查看结果")
    parser.add_argument("--count", type=int, default=10, help="查看消息数量")
    parser.add_argument("--agent", default="xingshu", help="Agent 名称")
    
    args = parser.parse_args()
    
    view_results(agent_name=args.agent, count=args.count)
