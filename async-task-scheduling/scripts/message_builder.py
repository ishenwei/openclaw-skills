# -*- coding: utf-8 -*-
"""
消息构建模块 - Message Builder
将意图解析结果转换为标准的 RabbitMQ 消息格式
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Optional


class MessageBuilder:
    """消息构建器"""
    
    # 高优先级动作
    HIGH_PRIORITY_ACTIONS = ["code_review", "deploy", "security_check", "data_analysis"]
    
    # 默认超时时间 (毫秒)
    DEFAULT_TIMEOUT = 3600000  # 1小时
    
    def __init__(self, source: str = "xingyao", default_timeout: int = None):
        """
        初始化消息构建器
        
        Args:
            source: 消息来源 Agent 名称
            default_timeout: 默认超时时间 (毫秒)
        """
        self.source = source
        self.default_timeout = default_timeout or self.DEFAULT_TIMEOUT
    
    def build_task_message(self, intent: Dict, priority: str = None) -> Dict:
        """
        构建任务消息
        
        Args:
            intent: 意图解析结果
            priority: 优先级 (high/normal/low)，如果为 None 则自动判断
            
        Returns:
            标准任务消息 JSON
        """
        if "error" in intent:
            return {"error": intent["error"]}
        
        # 自动判断优先级
        if priority is None:
            priority = self._detect_priority(intent.get("action", ""))
        
        # 生成任务ID
        task_id = self._generate_task_id()
        
        message = {
            "taskId": task_id,
            "type": "task",
            "source": self.source,
            "target": intent["target"],
            "priority": priority,
            "content": {
                "action": intent["action"],
                "message": intent.get("message")
            },
            "metadata": {
                "createdAt": datetime.now().isoformat() + "Z",
                "expireAt": None,
                "retryCount": 0,
                "maxRetries": 3,
                "timeout": self.default_timeout
            }
        }
        
        return message
    
    def build_result_message(self, task_id: str, target: str, 
                           status: str, content: Dict) -> Dict:
        """
        构建结果消息 (由子 Agent 使用)
        
        Args:
            task_id: 原始任务ID
            target: 目标 Agent (通常是星枢)
            status: 执行状态 (success/error/partial)
            content: 结果内容
            
        Returns:
            标准结果消息 JSON
        """
        message = {
            "taskId": task_id,
            "type": "result",
            "source": self.source,
            "target": target,
            "status": status,
            "content": content,
            "metadata": {
                "completedAt": datetime.now().isoformat() + "Z"
            }
        }
        
        return message
    
    def build_heartbeat_message(self, agent_name: str, 
                                status: str = "idle",
                                current_task: str = None) -> Dict:
        """
        构建心跳消息
        
        Args:
            agent_name: Agent 名称
            status: 当前状态 (idle/busy/error)
            current_task: 当前执行的任务ID
            
        Returns:
            心跳消息 JSON
        """
        message = {
            "type": "heartbeat",
            "agent": agent_name,
            "status": status,
            "currentTask": current_task,
            "timestamp": datetime.now().isoformat() + "Z"
        }
        
        return message
    
    def build_error_message(self, task_id: str, target: str,
                           error: str, details: Dict = None) -> Dict:
        """
        构建错误消息
        
        Args:
            task_id: 任务ID
            target: 目标 Agent
            error: 错误描述
            details: 错误详情
            
        Returns:
            错误消息 JSON
        """
        message = {
            "taskId": task_id,
            "type": "error",
            "source": self.source,
            "target": target,
            "error": error,
            "content": details or {},
            "metadata": {
                "occurredAt": datetime.now().isoformat() + "Z"
            }
        }
        
        return message
    
    def _detect_priority(self, action: str) -> str:
        """根据动作自动判断优先级"""
        return "high" if action in self.HIGH_PRIORITY_ACTIONS else "normal"
    
    def _generate_task_id(self) -> str:
        """生成唯一任务ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:6]
        return f"task_{timestamp}_{unique_id}"
    
    def to_json(self, message: Dict) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(message, ensure_ascii=False, indent=2)
    
    def from_json(self, json_str: str) -> Dict:
        """从 JSON 字符串解析"""
        return json.loads(json_str)


# 测试
if __name__ == "__main__":
    builder = MessageBuilder()
    
    # 测试任务消息
    intent = {
        "action": "personal",
        "target": "xinghui",
        "message": "请安排明天早上9点的会议"
    }
    
    task_msg = builder.build_task_message(intent)
    print("任务消息:")
    print(builder.to_json(task_msg))
    print("-" * 40)
    
    # 测试心跳消息
    heartbeat = builder.build_heartbeat_message("xinghui", "idle")
    print("心跳消息:")
    print(builder.to_json(heartbeat))
    print("-" * 40)
    
    # 测试结果消息
    result_msg = builder.build_result_message(
        task_id=task_msg["taskId"],
        target="xingshu",
        status="success",
        content={"summary": "日程安排成功", "findings": []}
    )
    print("结果消息:")
    print(builder.to_json(result_msg))
