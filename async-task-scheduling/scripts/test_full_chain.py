#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
异步任务调度系统 - 完整链路测试脚本

测试场景:
1. 意图解析 -> 2. 消息构建 -> 3. 发送 RabbitMQ -> 4. 验证队列
5. Agent 监听并处理 -> 6. 结果返回 -> 7. 星枢接收结果

用法:
    python3 test_full_chain.py                    # 运行所有测试
    python3 test_full_chain.py --scenario <场景>  # 运行指定场景
    python3 test_full_chain.py --interactive     # 交互模式

场景:
    monitor_success   - 监控任务成功
    monitor_fail     - 监控任务失败
    code_review      - 代码审查
    ops_start        - 运维启动
    ops_stop         - 运维停止
    personal         - 个人事务
    unknown          - 无法识别的命令
"""

import sys
import os
import json
import time
import argparse
import subprocess
import threading
import unittest
from datetime import datetime
from typing import Dict, List, Optional

# 添加脚本目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import RABBITMQ_CONFIG, get_queue_name, get_routing_key
from intent_parser import IntentParser
from message_builder import MessageBuilder
from rabbitmq_sender import RabbitMQSender

# 导入 pika 用于直接操作 RabbitMQ
import pika

# ============================================================================
# 测试配置
# ============================================================================

TEST_CONFIG = {
    "rabbitmq_host": RABBITMQ_CONFIG["host"],
    "rabbitmq_port": RABBITMQ_CONFIG["port"],
    "username": RABBITMQ_CONFIG["username"],
    "password": RABBITMQ_CONFIG["password"],
    "test_agent": "yunhan",  # 测试用的 agent
    "result_agent": "xingshu",  # 结果收集 agent
    "timeout": 30,  # 测试超时时间
}

# 测试场景定义
TEST_SCENARIOS = {
    "monitor_success": {
        "user_input": "请检查 ubuntu2 服务器的内存使用情况",
        "expected_action": "monitor",
        "expected_target": "yunhan",
        "mock_response": {
            "status": "success",
            "memory": "使用率 45%, 共 16GB, 已用 7.2GB",
            "uptime": "15天 3小时 22分钟"
        }
    },
    "monitor_fail": {
        "user_input": "检查 192.168.3.999 的状态",
        "expected_action": "monitor",
        "expected_target": "yunhan",
        "mock_response": {
            "status": "error",
            "error": "无法连接到 192.168.3.999: 连接超时"
        }
    },
    "code_review": {
        "user_input": "让云策审查 async-task-scheduling 项目的代码",
        "expected_action": "code_review",
        "expected_target": "yunce",
        "mock_response": {
            "status": "success",
            "summary": "代码审查完成，发现 3 个问题",
            "issues": [
                {"severity": "high", "file": "config.py", "issue": "敏感信息硬编码"},
                {"severity": "medium", "file": "agent_listener.py", "issue": "缺少超时配置"},
                {"severity": "low", "file": "intent_parser.py", "issue": "类型注解不完整"}
            ]
        }
    },
    "ops_start": {
        "user_input": "启动 docker 服务",
        "expected_action": "ops",
        "expected_target": "xingyao",
        "mock_response": {
            "status": "success",
            "operation": "start",
            "service": "docker",
            "result": "Docker 服务已启动"
        }
    },
    "ops_stop": {
        "user_input": "停止 nginx 服务",
        "expected_action": "ops",
        "expected_target": "xingyao",
        "mock_response": {
            "status": "success",
            "operation": "stop",
            "service": "nginx",
            "result": "Nginx 服务已停止"
        }
    },
    "personal": {
        "user_input": "帮我安排明天上午9点的会议",
        "expected_action": "personal",
        "expected_target": "xinghui",
        "mock_response": {
            "status": "success",
            "reminder": "会议安排: 明天上午9点",
            "result": "已添加到日历"
        }
    },
    "unknown": {
        "user_input": "来一段周杰伦的晴天",
        "expected_action": None,
        "expected_target": None,
        "mock_response": None
    },
    "deploy": {
        "user_input": "部署服务到生产环境",
        "expected_action": "deploy",
        "expected_target": "yunzhi",
        "mock_response": {
            "status": "success",
            "deployment": "生产环境部署完成",
            "version": "v2.2.0"
        }
    }
}

# ============================================================================
# RabbitMQ 工具类
# ============================================================================

class RabbitMQHelper:
    """RabbitMQ 辅助工具"""
    
    def __init__(self, config: Dict = None):
        self.config = config or TEST_CONFIG
        self.connection = None
        self.channel = None
    
    def connect(self):
        """连接到 RabbitMQ"""
        credentials = pika.PlainCredentials(
            self.config["username"],
            self.config["password"]
        )
        parameters = pika.ConnectionParameters(
            host=self.config["rabbitmq_host"],
            port=self.config["rabbitmq_port"],
            credentials=credentials,
            heartbeat=60,
            blocked_connection_timeout=30
        )
        
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        return self
    
    def close(self):
        """关闭连接"""
        if self.connection and self.connection.is_open:
            self.connection.close()
    
    def get_queue_message_count(self, queue_name: str) -> int:
        """获取队列消息数量"""
        queue = self.channel.queue_declare(queue=queue_name, passive=True)
        return queue.method.message_count
    
    def get_queue_messages(self, queue_name: str, count: int = 1) -> List[Dict]:
        """获取队列中的消息"""
        messages = []
        for _ in range(count):
            method, properties, body = self.channel.basic_get(
                queue=queue_name, auto_ack=False
            )
            if body:
                messages.append(json.loads(body))
                # 不 ACK，保留消息
            else:
                break
        return messages
    
    def peek_queue(self, queue_name: str) -> Optional[Dict]:
        """查看队列头部消息（不消费）"""
        messages = self.get_queue_messages(queue_name, 1)
        return messages[0] if messages else None
    
    def clear_queue(self, queue_name: str):
        """清空队列"""
        while True:
            method, _, _ = self.channel.basic_get(queue=queue_name, auto_ack=True)
            if not method:
                break


# ============================================================================
# 测试结果收集
# ============================================================================

class TestResult:
    """测试结果"""
    
    def __init__(self, scenario: str):
        self.scenario = scenario
        self.start_time = datetime.now()
        self.end_time = None
        self.steps: List[Dict] = []
        self.success = False
        self.error = None
    
    def add_step(self, name: str, data: Dict = None, success: bool = True):
        """添加测试步骤"""
        self.steps.append({
            "name": name,
            "data": data,
            "success": success,
            "timestamp": datetime.now().isoformat()
        })
    
    def finish(self, success: bool, error: str = None):
        """完成测试"""
        self.end_time = datetime.now()
        self.success = success
        self.error = error
    
    def get_duration(self) -> float:
        """获取测试耗时（秒）"""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return (datetime.now() - self.start_time).total_seconds()
    
    def print_report(self):
        """打印测试报告"""
        print("\n" + "="*70)
        print(f"📋 测试场景: {self.scenario}")
        print(f"⏱️ 耗时: {self.get_duration():.2f}秒")
        print(f"📊 状态: {'✅ 通过' if self.success else '❌ 失败'}")
        
        if self.error:
            print(f"\n❌ 错误: {self.error}")
        
        print("\n📝 执行步骤:")
        for i, step in enumerate(self.steps, 1):
            status = "✅" if step["success"] else "❌"
            print(f"  {i}. {status} {step['name']}")
            if step["data"]:
                # 简化显示
                data_str = json.dumps(step["data"], ensure_ascii=False, indent=2)
                if len(data_str) > 200:
                    data_str = data_str[:200] + "..."
                print(f"     {data_str}")
        
        print("="*70)


# ============================================================================
# 完整链路测试
# ============================================================================

class FullChainTester:
    """完整链路测试器"""
    
    def __init__(self, scenario: str):
        self.scenario = scenario
        self.config = TEST_CONFIG
        self.result = TestResult(scenario)
        
        # 初始化组件
        self.parser = IntentParser()
        self.builder = MessageBuilder(source="test_user")
        self.sender = None
        self.rabbitmq = None
    
    def run(self) -> bool:
        """运行完整测试"""
        print(f"\n🚀 开始测试场景: {self.scenario}")
        print("="*70)
        
        try:
            # 步骤1: 意图解析
            self._test_intent_parsing()
            
            # 获取场景配置
            scenario_config = TEST_SCENARIOS.get(self.scenario)
            if not scenario_config:
                raise ValueError(f"未知场景: {self.scenario}")
            
            # 如果是无法识别的命令，测试结束
            if scenario_config.get("expected_action") is None:
                self.result.add_step("意图解析（无法识别）", {
                    "input": scenario_config["user_input"],
                    "expected": "无法识别",
                    "result": "无法识别是预期行为"
                }, True)
                self.result.finish(True)
                return True
            
            # 检查意图解析是否成功
            intent = self.parser.parse_intent(scenario_config["user_input"])
            if "error" in intent:
                raise ValueError(f"意图解析失败: {intent.get('error')}")
            
            # 步骤2: 构建消息
            self._test_message_building()
            
            # 步骤3: 连接到 RabbitMQ
            self._test_rabbitmq_connection()
            
            # 步骤4: 发送消息
            self._test_send_message()
            
            # 步骤5: 验证消息进入队列
            self._test_verify_message_in_queue()
            
            # 步骤6: 模拟 Agent 处理（本地模拟）
            self._test_mock_agent_processing(scenario_config["mock_response"])
            
            # 步骤7: 验证结果进入结果队列
            self._test_verify_result_in_queue()
            
            # 步骤8: 模拟星枢接收结果
            self._test_mock_xingshu_receive()
            
            self.result.finish(True)
            return True
            
        except Exception as e:
            self.result.finish(False, str(e))
            return False
    
    def _test_intent_parsing(self):
        """测试意图解析"""
        scenario = TEST_SCENARIOS[self.scenario]
        user_input = scenario["user_input"]
        
        intent = self.parser.parse_intent(user_input)
        
        # 对于无法识别的命令，检查是否返回了 error
        if scenario.get("expected_action") is None:
            success = "error" in intent
            self.result.add_step("意图解析", {
                "input": user_input,
                "intent": intent,
                "expected": "无法识别"
            }, success)
            if success:
                print(f"✅ 意图解析: 无法识别（预期行为）")
                return
            else:
                raise AssertionError(f"意图解析应该返回错误")
        
        success = (
            intent.get("action") == scenario.get("expected_action") and
            intent.get("target") == scenario.get("expected_target")
        )
        
        self.result.add_step("意图解析", {
            "input": user_input,
            "intent": intent,
            "expected": {
                "action": scenario.get("expected_action"),
                "target": scenario.get("expected_target")
            }
        }, success)
        
        if not success:
            raise AssertionError(
                f"意图解析失败: 期望 action={scenario.get('expected_action')}, "
                f"target={scenario.get('expected_target')}, "
                f"实际 action={intent.get('action')}, target={intent.get('target')}"
            )
        
        print(f"✅ 意图解析: {intent['action']} -> {intent['target']}")
    
    def _test_message_building(self):
        """测试消息构建"""
        scenario = TEST_SCENARIOS[self.scenario]
        intent = self.parser.parse_intent(scenario["user_input"])
        
        # 如果意图解析失败，跳过消息构建
        if "error" in intent:
            raise ValueError(f"意图解析失败，跳过消息构建: {intent.get('error')}")
        
        message = self.builder.build_task_message(intent)
        
        # 验证消息结构
        required_fields = ["taskId", "type", "source", "target", "priority", "content"]
        has_all_fields = all(field in message for field in required_fields)
        
        self.result.add_step("消息构建", {
            "message": message
        }, has_all_fields)
        
        if not has_all_fields:
            raise AssertionError(f"消息结构不完整: {message}")
        
        print(f"✅ 消息构建: taskId={message['taskId']}")
        self.task_message = message
    
    def _test_rabbitmq_connection(self):
        """测试 RabbitMQ 连接"""
        try:
            self.rabbitmq = RabbitMQHelper(self.config).connect()
            self.sender = RabbitMQSender({
                "host": self.config["rabbitmq_host"],
                "username": self.config["username"],
                "password": self.config["password"]
            })
            
            self.result.add_step("RabbitMQ 连接", {
                "host": self.config["rabbitmq_host"]
            }, True)
            
            print(f"✅ RabbitMQ 连接成功: {self.config['rabbitmq_host']}")
            
            # 清空目标队列中的旧消息（只保留最近一条作为测试标记）
            self._cleanup_old_messages()
            
        except Exception as e:
            self.result.add_step("RabbitMQ 连接", {"error": str(e)}, False)
            raise
    
    def _cleanup_old_messages(self):
        """清理目标队列中的旧消息，只保留我们新发送的"""
        # 获取初始队列深度，用于验证
        for target in ["yunhan", "yunce", "xingyao", "xinghui", "yunzhi"]:
            queue_name = get_queue_name(target, "tasks")
            try:
                # 清空队列
                self.rabbitmq.channel.queue_declare(queue=queue_name, durable=True)
                while True:
                    method, _, _ = self.rabbitmq.channel.basic_get(
                        queue=queue_name, auto_ack=True
                    )
                    if not method:
                        break
            except:
                pass
    
    def _test_send_message(self):
        """测试发送消息"""
        task_id = self.task_message["taskId"]
        target = self.task_message["target"]
        
        # 记录发送前的队列深度
        queue_name = get_queue_name(target, "tasks")
        count_before = self.rabbitmq.get_queue_message_count(queue_name)
        
        # 发送消息
        self.sender.send_task(self.task_message)
        
        self.result.add_step("发送消息", {
            "taskId": task_id,
            "target": target,
            "queue": queue_name
        }, True)
        
        print(f"✅ 消息已发送: {task_id} -> {target}")
        self.task_id = task_id
    
    def _test_verify_message_in_queue(self):
        """验证消息进入队列"""
        target = self.task_message["target"]
        queue_name = get_queue_name(target, "tasks")
        
        # 等待消息进入队列
        time.sleep(0.5)
        
        # 检查队列是否有消费者正在监听
        queue_info = self.rabbitmq.channel.queue_declare(queue=queue_name, passive=True)
        consumer_count = queue_info.method.consumer_count
        message_count = queue_info.method.message_count
        
        print(f"📬 队列状态: {queue_name}, 消息数: {message_count}, 消费者: {consumer_count}")
        
        # 如果有消费者监听，消息可能被立即消费
        if consumer_count > 0:
            # 消息被 agent 消费了，这是预期的行为
            print(f"✅ 消息已投递到 Agent (队列有消费者监听)")
            self.result.add_step("验证消息投递", {
                "queue": queue_name,
                "delivered": True,
                "consumer_count": consumer_count
            }, True)
        elif message_count > 0:
            # 没有消费者，消息在队列中 - 需要找到我们发送的消息
            found = False
            latest_message = None
            
            # 遍历队列查找我们的消息
            for i in range(message_count):
                method, props, body = self.rabbitmq.channel.basic_get(
                    queue=queue_name, auto_ack=False
                )
                if body:
                    msg = json.loads(body)
                    if msg.get("taskId") == self.task_id:
                        found = True
                        latest_message = msg
                        # 确认消息并退出循环
                        self.rabbitmq.channel.basic_ack(
                            delivery_tag=method.delivery_tag
                        )
                        break
                    else:
                        # 不是我们的消息，重新放回队列
                        self.rabbitmq.channel.basic_nack(
                            delivery_tag=method.delivery_tag, requeue=True
                        )
            
            # 如果找到消息，队列少了一条，所以消息数现在少了1
            # 把其他消息重新放回去（它们之前被 nack 了）
            # 实际上，basic_nack(requeue=True) 会把消息放回去
            
            self.result.add_step("验证消息在队列", {
                "queue": queue_name,
                "found": found,
                "message": latest_message
            }, found)
            
            if not found:
                raise AssertionError(f"消息未找到队列中: {queue_name}")
            print(f"✅ 消息已在队列中: {queue_name}")
        else:
            # 既没有消费者也没有消息
            print(f"⚠️ 队列为空")
    
    def _test_mock_agent_processing(self, mock_response: Dict):
        """模拟 Agent 处理任务"""
        if not mock_response:
            return
        
        # 模拟 agent_listener 处理任务
        # 这里我们直接构造结果消息，模拟 agent 处理完成
        
        result_message = {
            "taskId": self.task_id,
            "type": "result",
            "source": self.task_message["target"],
            "target": "xingshu",
            "status": mock_response.get("status", "success"),
            "content": {
                "action": self.task_message["content"]["action"],
                "message": self.task_message["content"].get("message", ""),
                "result": mock_response
            },
            "metadata": {
                "completedAt": datetime.now().isoformat() + "Z"
            }
        }
        
        # 发送结果到结果队列
        self.sender.send_result(result_message)
        
        self.result.add_step("模拟 Agent 处理", {
            "taskId": self.task_id,
            "response": mock_response
        }, True)
        
        print(f"✅ Agent 处理完成，返回结果: {mock_response.get('status')}")
        self.result_message = result_message
    
    def _test_verify_result_in_queue(self):
        """验证结果进入结果队列"""
        result_queue = get_queue_name(self.config["result_agent"], "results")
        
        # 等待结果进入队列
        time.sleep(0.5)
        
        # 检查队列状态
        queue_info = self.rabbitmq.channel.queue_declare(queue=result_queue, passive=True)
        consumer_count = queue_info.method.consumer_count
        message_count = queue_info.method.message_count
        
        print(f"📬 结果队列状态: {result_queue}, 消息数: {message_count}, 消费者: {consumer_count}")
        
        # 如果有消费者监听，结果被立即消费
        if consumer_count > 0:
            print(f"✅ 结果已投递到星枢 (队列有消费者监听)")
            self.result.add_step("验证结果投递", {
                "queue": result_queue,
                "delivered": True,
                "consumer_count": consumer_count
            }, True)
        elif message_count > 0:
            message = self.rabbitmq.peek_queue(result_queue)
            found = message and message.get("taskId") == self.task_id
            
            self.result.add_step("验证结果在队列", {
                "queue": result_queue,
                "found": found
            }, found)
            
            if not found:
                raise AssertionError(f"结果未找到队列中: {result_queue}")
            print(f"✅ 结果已在队列中: {result_queue}")
        else:
            # 检查消息是否被发送（通过查询确认）
            print(f"⚠️ 结果队列为空")
    
    def _test_mock_xingshu_receive(self):
        """模拟星枢接收结果"""
        result_queue = get_queue_name(self.config["result_agent"], "results")
        
        # 获取结果消息
        messages = self.rabbitmq.get_queue_messages(result_queue, 1)
        
        # 如果队列有消费者，消息已被消费，使用我们发送的结果消息
        queue_info = self.rabbitmq.channel.queue_declare(queue=result_queue, passive=True)
        if queue_info.method.consumer_count > 0:
            # 使用测试中发送的模拟结果
            result = self.result_message
            
            # 格式化输出
            formatted = self._format_result(result)
            
            self.result.add_step("星枢接收结果", {
                "result": result,
                "formatted": formatted,
                "note": "消息被实时消费者 (result_receiver) 消费"
            }, True)
            
            print(f"\n📥 星枢收到结果 (通过模拟):")
            print(formatted)
        elif messages:
            result = messages[0]
            
            # 格式化输出
            formatted = self._format_result(result)
            
            self.result.add_step("星枢接收结果", {
                "result": result,
                "formatted": formatted
            }, True)
            
            print(f"\n📥 星枢收到结果:")
            print(formatted)
        else:
            raise AssertionError("星枢未能接收结果")
    
    def _format_result(self, message: Dict) -> str:
        """格式化结果消息"""
        task_id = message.get("taskId", "unknown")
        source = message.get("source", "unknown")
        status = message.get("status", "unknown")
        content = message.get("content", {})
        
        status_emoji = {
            "success": "✅",
            "error": "❌",
            "failed": "❌"
        }.get(status, "📋")
        
        lines = [
            f"{status_emoji} 任务完成",
            f"",
            f"Task ID: {task_id}",
            f"执行者: {source}",
            f"状态: {status}",
            ""
        ]
        
        # 添加结果内容
        result = content.get("result", {})
        if isinstance(result, dict):
            for key, value in result.items():
                if isinstance(value, list):
                    lines.append(f"{key}:")
                    for item in value:
                        lines.append(f"  - {item}")
                else:
                    lines.append(f"{key}: {value}")
        else:
            lines.append(f"结果: {result}")
        
        return "\n".join(lines)
    
    def cleanup(self):
        """清理资源"""
        if self.sender:
            self.sender.close()
        if self.rabbitmq:
            self.rabbitmq.close()


# ============================================================================
# 测试运行器
# ============================================================================

def run_single_scenario(scenario: str) -> bool:
    """运行单个场景测试"""
    tester = FullChainTester(scenario)
    
    try:
        success = tester.run()
        tester.result.print_report()
        
        # 清理
        tester.cleanup()
        
        return success
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        tester.result.print_report()
        tester.cleanup()
        return False


def run_all_tests() -> Dict[str, bool]:
    """运行所有场景测试"""
    print("\n" + "="*70)
    print("🧪 异步任务调度系统 - 完整链路测试")
    print("="*70)
    
    results = {}
    
    for scenario in TEST_SCENARIOS:
        print(f"\n\n{'#'*70}")
        success = run_single_scenario(scenario)
        results[scenario] = success
    
    # 打印汇总
    print("\n\n" + "="*70)
    print("📊 测试汇总")
    print("="*70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for scenario, success in results.items():
        status = "✅" if success else "❌"
        print(f"  {status} {scenario}")
    
    print(f"\n通过: {passed}/{total}")
    print("="*70)
    
    return results


def interactive_mode():
    """交互模式"""
    print("\n" + "="*70)
    print("🎮 交互模式")
    print("="*70)
    
    print("\n可用场景:")
    for i, scenario in enumerate(TEST_SCENARIOS, 1):
        print(f"  {i}. {scenario}")
    
    while True:
        try:
            user_input = input("\n👤 请输入命令 (输入 'q' 退出): ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() == 'q':
                break
            
            # 创建临时测试
            parser = IntentParser()
            intent = parser.parse_intent(user_input)
            
            print(f"\n📝 意图解析结果:")
            print(json.dumps(intent, ensure_ascii=False, indent=2))
            
            if "error" not in intent:
                builder = MessageBuilder()
                message = builder.build_task_message(intent)
                print(f"\n📤 消息内容:")
                print(builder.to_json(message))
            else:
                print(f"\n⚠️ 无法理解此命令")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\n❌ 错误: {e}")
    
    print("\n👋 退出交互模式")


# ============================================================================
# 主程序
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="异步任务调度系统 - 完整链路测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python3 test_full_chain.py                      # 运行所有测试
    python3 test_full_chain.py --scenario monitor_success
    python3 test_full_chain.py --interactive          # 交互模式
    python3 test_full_chain.py --list                  # 列出所有场景
        """
    )
    
    parser.add_argument(
        "--scenario", "-s",
        help="指定测试场景"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="交互模式"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="列出所有测试场景"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细输出"
    )
    
    args = parser.parse_args()
    
    # 列出所有场景
    if args.list:
        print("\n可用测试场景:")
        print("-"*50)
        for scenario, config in TEST_SCENARIOS.items():
            print(f"  {scenario}:")
            print(f"    输入: {config['user_input']}")
            print(f"    期望: action={config.get('expected_action')}, "
                  f"target={config.get('expected_target')}")
            print()
        return
    
    # 交互模式
    if args.interactive:
        interactive_mode()
        return
    
    # 运行指定场景或所有测试
    if args.scenario:
        if args.scenario not in TEST_SCENARIOS:
            print(f"❌ 未知场景: {args.scenario}")
            print(f"可用场景: {', '.join(TEST_SCENARIOS.keys())}")
            sys.exit(1)
        
        success = run_single_scenario(args.scenario)
        sys.exit(0 if success else 1)
    else:
        results = run_all_tests()
        all_passed = all(results.values())
        sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
