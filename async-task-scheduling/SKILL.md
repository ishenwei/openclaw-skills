# async-task-scheduling - 异步任务调度技能

> 版本: 2.2
> 最后更新: 2026-03-17

---

## 概述

**技能名称**: async-task-scheduling

**适用 Agent**: xingshu (星枢)

**功能**:
- 解析用户自然语言指令
- 映射到对应的执行 Agent
- 构建标准任务消息
- 通过 RabbitMQ 异步分发

---

## 文件结构

```
async-task-scheduling/
├── SKILL.md                      # 本文件
└── scripts/
    ├── __init__.py               # 模块导出
    ├── config.py                 # RabbitMQ 配置
    ├── intent_parser.py          # 意图解析
    ├── message_builder.py        # 消息构建
    ├── rabbitmq_sender.py        # 消息发送
    ├── agent_listener.py         # 子 Agent 监听
    ├── result_receiver.py        # 结果接收 (星枢用)
    ├── view_results.py           # 快速查看结果
    ├── setup_rabbitmq.py         # RabbitMQ 初始化
    └── run_listener.sh           # 启动脚本
```

---

## RabbitMQ 配置 (config.py)

```python
# 连接配置
RABBITMQ_CONFIG = {
    "host": "192.168.3.189",       # RabbitMQ 服务器地址
    "port": 5672,                   # AMQP 端口
    "username": "guest",            # 用户名
    "password": "guest",            # 密码
    "exchange": "task_exchange",   # 任务交换机
    "result_exchange": "result_exchange",  # 结果交换机
    "heartbeat": 600,              # 心跳间隔 (秒)
    "blocked_connection_timeout": 300  # 连接超时 (秒)
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
    "code_review": "yunce",
    "deploy": "yunzhi",
    "status_check": "yunhan",
    "monitor": "yunhan",
    "architecture": "yunce",
    "coding": "yunjiang",
    "automation": "yunzhi",
    "qa_test": "fengheng",
    "execute": "fengchi",
    "audit": "fengji",
    "personal": "xinghui",
    "ops": "xingyao"
}
```

**配置说明**:
| 字段 | 说明 |
|------|------|
| host | RabbitMQ 服务器 IP (本项目运行在 Mac Mini 192.168.3.189) |
| port | AMQP 协议端口，默认 5672 |
| username/password | 认证凭据，默认 guest/guest |
| exchange | 交换机名称，用于路由消息 |
| heartbeat | 客户端心跳检测间隔 |

---

## 核心模块

### 1. intent_parser.py
- 将自然语言解析为结构化任务
- 支持中文 Agent 名称识别 (云瀚, 云策, etc.)
- action → target 映射

### 2. message_builder.py
- 构建标准 RabbitMQ 消息格式

### 3. rabbitmq_sender.py
- 发送任务到 RabbitMQ

### 4. agent_listener.py
- 子 Agent 监听任务队列
- 执行任务并返回结果

### 5. result_receiver.py
- 星枢监听结果队列

---

## 消息格式

### Task
```json
{
  "taskId": "task_20260317_xxx",
  "type": "task",
  "source": "xingshu",
  "target": "yunhan",
  "priority": "normal",
  "content": {
    "action": "monitor",
    "params": {"check_type": "memory"}
  }
}
```

### Result
```json
{
  "taskId": "task_20260317_xxx",
  "type": "result",
  "source": "yunhan",
  "target": "xingshu",
  "status": "success",
  "content": {...}
}
```

---

## RabbitMQ 队列

### Exchanges
- task_exchange (topic)
- result_exchange (topic)

### Queues
- tasks.xingyao, tasks.xinghui, tasks.yunhan, tasks.yunce
- tasks.yunjiang, tasks.yunzhi, tasks.fengheng, tasks.fengchi, tasks.fengji
- results.xingshu

---

## 服务器分布

| 服务器 | IP | 运行的 Agent |
|--------|-----|-------------|
| Mac Mini | 192.168.3.189 | xingyao, xinghui, RabbitMQ |
| Ubuntu2 | 192.168.3.45 | yunhan, yunce, yunjiang, yunzhi |
| Ubuntu1 | 192.168.3.47 | fengheng, fengchi, fengji |

---

## 命令行使用

### 1. 启动 Agent Listener (子 Agent)

```bash
# 1. 先确保 pika 已安装
pip3 install pika

# 2. 进入技能目录
cd ~/async-task-scheduling/scripts/

# 3. 启动监听 (后台运行)
nohup python3 agent_listener.py <agent_name> --host 192.168.3.189 > /tmp/agent_<agent_name>.log 2>&1 &

# 4. 查看日志
tail -f /tmp/agent_<agent_name>.log
```

### 2. 星枢处理结果

```bash
# 方式 1: 快速查看 (不处理，不 ACK)
python3 view_results.py

# 方式 2: 持续监听 (处理并 ACK)
python3 result_receiver.py
```

---

## 各 Agent 启动命令

### Mac Mini (192.168.3.189)

```bash
# 启动 xingyao (星曜)
ssh macmini "cd ~/async-task-scheduling/scripts/ && nohup python3 agent_listener.py xingyao --host 192.168.3.189 > /tmp/agent_xingyao.log 2>&1 &"

# 启动 xinghui (星辉)
ssh macmini "cd ~/async-task-scheduling/scripts/ && nohup python3 agent_listener.py xinghui --host 192.168.3.189 > /tmp/agent_xinghui.log 2>&1 &"
```

### Ubuntu2 (192.168.3.45)

```bash
# 启动 yunhan (云瀚)
ssh ubuntu2 "cd ~/async-task-scheduling/scripts/ && nohup python3 agent_listener.py yunhan --host 192.168.3.189 > /tmp/agent_yunhan.log 2>&1 &"

# 启动 yunce (云策)
ssh ubuntu2 "cd ~/async-task-scheduling/scripts/ && nohup python3 agent_listener.py yunce --host 192.168.3.189 > /tmp/agent_yunce.log 2>&1 &"

# 启动 yunjiang (云匠)
ssh ubuntu2 "cd ~/async-task-scheduling/scripts/ && nohup python3 agent_listener.py yunjiang --host 192.168.3.189 > /tmp/agent_yunjiang.log 2>&1 &"

# 启动 yunzhi (云织)
ssh ubuntu2 "cd ~/async-task-scheduling/scripts/ && nohup python3 agent_listener.py yunzhi --host 192.168.3.189 > /tmp/agent_yunzhi.log 2>&1 &"
```

### Ubuntu1 (192.168.3.47)

```bash
# 启动 fengheng (风衡)
ssh ubuntu1 "cd ~/async-task-scheduling/scripts/ && nohup python3 agent_listener.py fengheng --host 192.168.3.189 > /tmp/agent_fengheng.log 2>&1 &"

# 启动 fengchi (风驰)
ssh ubuntu1 "cd ~/async-task-scheduling/scripts/ && nohup python3 agent_listener.py fengchi --host 192.168.3.189 > /tmp/agent_fengchi.log 2>&1 &"

# 启动 fengji (风纪)
ssh ubuntu1 "cd ~/async-task-scheduling/scripts/ && nohup python3 agent_listener.py fengji --host 192.168.3.189 > /tmp/agent_fengji.log 2>&1 &"
```

---

## 依赖

- Python 3.7+
- pika

---

*版本: 2.2*
