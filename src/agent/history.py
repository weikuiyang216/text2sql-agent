"""Conversation history management."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ConversationTurn:
    """对话轮次"""
    question: str
    sql: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    success: bool = True
    timestamp: datetime = field(default_factory=datetime.now)


class ConversationHistory:
    """对话历史管理"""

    def __init__(self, max_turns: int = 10):
        self.max_turns = max_turns
        self.turns: list[ConversationTurn] = []

    def add_turn(self, turn: ConversationTurn):
        """添加对话轮次"""
        self.turns.append(turn)
        # 保持历史在限制内
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

    def get_recent(self, n: int = 3) -> list[ConversationTurn]:
        """获取最近 n 轮对话"""
        return self.turns[-n:]

    def clear(self):
        """清空历史"""
        self.turns = []

    def __len__(self) -> int:
        return len(self.turns)

    def __iter__(self):
        return iter(self.turns)

    def to_dict(self) -> list[dict]:
        """转换为字典列表"""
        return [
            {
                "question": t.question,
                "sql": t.sql,
                "success": t.success,
                "timestamp": t.timestamp.isoformat()
            }
            for t in self.turns
        ]