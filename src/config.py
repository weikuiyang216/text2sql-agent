"""Configuration management for text2sql-agent."""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


class Config:
    """应用配置类"""

    # LLM API 配置
    OPENAI_API_BASE: str = os.getenv("OPENAI_API_BASE", "http://localhost:11434/v1")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "ollama")
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "qwen2.5")

    # MCP Server 配置
    MCP_SERVER_HOST: str = os.getenv("MCP_SERVER_HOST", "localhost")
    MCP_SERVER_PORT: int = int(os.getenv("MCP_SERVER_PORT", "8765"))

    # 数据库配置
    DATABASE_DIR: Path = Path(os.getenv("DATABASE_DIR", "./test_database"))
    DEFAULT_DATABASE: str = os.getenv("DEFAULT_DATABASE", "bakery_1")

    @classmethod
    def get_db_path(cls, db_name: str | None = None) -> Path:
        """获取数据库文件路径"""
        db_name = db_name or cls.DEFAULT_DATABASE
        return cls.DATABASE_DIR / db_name / f"{db_name}.sqlite"

    @classmethod
    def list_databases(cls) -> list[str]:
        """列出所有可用数据库"""
        if not cls.DATABASE_DIR.exists():
            return []
        return [
            d.name
            for d in cls.DATABASE_DIR.iterdir()
            if d.is_dir() and (d / f"{d.name}.sqlite").exists()
        ]


# 全局配置实例
config = Config()