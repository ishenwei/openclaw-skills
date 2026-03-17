# -*- coding: utf-8 -*-
"""
意图解析模块 - Intent Parser
将自然语言指令转换为结构化任务
"""

import re
from typing import Dict, Optional


class IntentParser:
    """意图解析器"""
    
    # Agent 名称映射 (中文名 -> agent_id)
    AGENT_MAP = {
        # 云系
        "云瀚": "yunhan",
        "云策": "yunce",
        "云匠": "yunjiang",
        "云织": "yunzhi",
        # 风系
        "风衡": "fengheng",
        "风驰": "fengchi",
        "风纪": "fengji",
        # 星系
        "星曜": "xingyao",
        "星辉": "xinghui",
    }
    
    # 动作关键词映射 - 优先级从高到低
    ACTION_KEYWORDS = {
        # 优先级1: 日程/提醒类 (最高优先)
        "日程": "personal",
        "提醒": "personal",
        "安排": "personal",
        "会议": "personal",
        "日历": "personal",
        "写日报": "personal",
        "发邮件": "personal",
        
        # 优先级2: 运维操作类
        "停止": "ops",
        "停掉": "ops",
        "启动": "ops",
        "重启": "ops",
        "安装": "ops",
        "卸载": "ops",
        "网络测试": "ops",
        "ping": "ops",
        "连通性": "ops",
        
        # 优先级3: 监控/检查类
        "检查": "monitor",
        "监控": "monitor",
        "查看": "monitor",
        "状态": "monitor",
        "内存": "monitor",
        "磁盘": "monitor",
        "CPU": "monitor",
        
        # 优先级4: 开发类
        "审查": "code_review",
        "代码审查": "code_review",
        "部署": "deploy",
        "发布": "deploy",
        "开发": "coding",
        "写代码": "coding",
        
        # 优先级5: 自动化/测试类
        "自动化": "automation",
        "CI/CD": "automation",
        "测试": "qa_test",
        "QA": "qa_test",
        
        # 优先级6: 执行/审计类
        "执行": "execute",
        "审计": "audit",
        "分析": "data_analysis",
    }
    
    # 动作到 agent 的默认映射
    DEFAULT_TARGET = {
        "monitor": "yunhan",      # 默认给云瀚
        "code_review": "yunce",   # 默认给云策
        "deploy": "yunzhi",       # 默认给云织
        "coding": "yunjiang",     # 默认给云匠
        "automation": "yunzhi",   # 默认给云织
        "qa_test": "fengheng",    # 默认给风衡
        "execute": "fengchi",     # 默认给风驰
        "audit": "fengji",        # 默认给风纪
        "personal": "xinghui",    # 默认给星辉
        "ops": "xingyao",         # 默认给星曜
    }
    
    # 高优先级动作关键词 (优先匹配)
    HIGH_PRIORITY_KEYWORDS = ["日程", "提醒", "安排", "会议", "日历", "写日报", "发邮件", "停止", "停掉", "启动", "重启"]
    
    def parse_intent(self, user_input: str) -> Dict:
        """
        解析用户输入，返回结构化意图
        """
        user_input = user_input.strip()
        
        # 1. 先尝试识别 Agent 名称
        target_agent = None
        for chinese_name, agent_id in self.AGENT_MAP.items():
            if chinese_name in user_input:
                target_agent = agent_id
                break
        
        # 2. 优先识别高优先级动作关键词
        action = None
        for keyword in self.HIGH_PRIORITY_KEYWORDS:
            if keyword in user_input:
                action = self.ACTION_KEYWORDS[keyword]
                break
        
        # 3. 如果没有高优先级动作，再识别其他动作
        if not action:
            for keyword, act in self.ACTION_KEYWORDS.items():
                if keyword in user_input:
                    action = act
                    break
        
        # 4. 如果识别到动作但没有指定 agent，使用默认
        if action and not target_agent:
            target_agent = self.DEFAULT_TARGET.get(action, None)
        
        # 5. 如果识别到 agent 但没有动作，使用默认
        if target_agent and not action:
            action = "monitor"  # 默认动作为监控
        
        # 6. 如果能确定 agent 和动作，返回结果
        if target_agent and action:
            return {
                "action": action,
                "target": target_agent,
                "message": user_input
            }
        
        # 无法识别
        return {
            "error": "无法理解指令",
            "message": user_input
        }


# 测试
if __name__ == "__main__":
    parser = IntentParser()
    
    test_cases = [
        "请让云瀚检查ubuntu2上的内存使用情况",
        "让云策审查代码",
        "部署服务到生产",
        "让星辉帮我安排明天的会议",
        "检查服务器状态",
    ]
    
    for test in test_cases:
        result = parser.parse_intent(test)
        print(f"输入: {test}")
        print(f"输出: {result}")
        print("-" * 40)
