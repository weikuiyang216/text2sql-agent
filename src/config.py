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

    # Milvus 配置
    MILVUS_HOST: str = os.getenv("MILVUS_HOST", "localhost")
    MILVUS_PORT: int = int(os.getenv("MILVUS_PORT", "19530"))
    MILVUS_COLLECTION_PREFIX: str = os.getenv("MILVUS_COLLECTION_PREFIX", "boc_contracts")

    # Embedding 配置
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "dashscope")
    EMBEDDING_API_BASE: str = os.getenv("EMBEDDING_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", "")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024"))

    # RAG 配置
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "10"))
    RAG_RERANK_TOP_K: int = int(os.getenv("RAG_RERANK_TOP_K", "5"))
    RAG_CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE", "800"))
    RAG_CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP", "150"))

    # 文档配置
    DOCUMENT_DIR: Path = Path(os.getenv("DOCUMENT_DIR", "./data"))

    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: Path | None = Path(os.getenv("LOG_FILE", "")) if os.getenv("LOG_FILE") else None
    LOG_RICH_OUTPUT: bool = os.getenv("LOG_RICH_OUTPUT", "true").lower() == "true"

    # SQL 安全配置
    SQL_ALLOW_WRITE: bool = os.getenv("SQL_ALLOW_WRITE", "false").lower() == "true"
    SQL_MAX_ROWS: int = int(os.getenv("SQL_MAX_ROWS", "1000"))
    SQL_TIMEOUT_SECONDS: float = float(os.getenv("SQL_TIMEOUT_SECONDS", "30.0"))

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