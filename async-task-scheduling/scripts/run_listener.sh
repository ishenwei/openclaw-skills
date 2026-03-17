#!/bin/bash
# Agent Listener 启动脚本
# 用法: ./run_listener.sh <agent_name>
# 示例: ./run_listener.sh xingyao

AGENT_NAME=${1:-xingyao}
RABBITMQ_HOST=${2:-192.168.3.189}

echo "🚀 启动 Agent 监听器: $AGENT_NAME"
echo "📡 RabbitMQ: $RABBITMQ_HOST"

cd "$(dirname "$0")"

# 持续运行，失败时自动重试
while true; do
    python3 agent_listener.py "$AGENT_NAME" --host "$RABBITMQ_HOST"
    echo "⚠️ 监听器断开，5秒后重连..."
    sleep 5
done
