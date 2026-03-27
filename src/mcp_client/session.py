"""Session management for MCP Client."""

from typing import Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid

from .client import MCPClient


@dataclass
class ConversationTurn:
    """对话轮次"""
    question: str
    sql: str
    result: dict[str, Any]
    explanation: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Session:
    """会话信息"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: datetime = field(default_factory=datetime.now)
    current_database: str = "bakery_1"
    history: list[ConversationTurn] = field(default_factory=list)

    def add_turn(self, turn: ConversationTurn):
        """添加对话轮次"""
        self.history.append(turn)

    def get_recent_history(self, n: int = 5) -> list[ConversationTurn]:
        """获取最近 n 轮对话"""
        return self.history[-n:]

    def clear_history(self):
        """清空对话历史"""
        self.history = []


class SessionManager:
    """会话管理器"""

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create_session(self, db_name: str = "bakery_1") -> Session:
        """创建新会话"""
        session = Session(current_database=db_name)
        self._sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        """获取会话"""
        return self._sessions.get(session_id)

    def get_or_create_session(self, session_id: str | None = None, db_name: str = "bakery_1") -> Session:
        """获取或创建会话"""
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        return self.create_session(db_name)

    def delete_session(self, session_id: str):
        """删除会话"""
        self._sessions.pop(session_id, None)

    def list_sessions(self) -> list[Session]:
        """列出所有会话"""
        return list(self._sessions.values())


# 全局会话管理器
session_manager = SessionManager()