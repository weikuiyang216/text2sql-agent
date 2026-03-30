"""Unified Agent that combines Text2SQL and RAG capabilities."""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from openai import AsyncOpenAI

from ..config import config
from ..mcp_client.client import MCPClient
from .core import Text2SQLAgent
from .prompts import build_system_prompt, build_user_prompt, extract_sql
from ..rag.pipeline import RAGPipeline, RAGResponse

logger = logging.getLogger(__name__)


class QueryIntent(str, Enum):
    """Query intent classification."""
    SQL = "sql"           # Database query
    RAG = "rag"           # Document query
    HYBRID = "hybrid"     # Both SQL and RAG
    GENERAL = "general"   # General chat


@dataclass
class UnifiedResponse:
    """Unified response from the agent."""
    query: str
    intent: QueryIntent
    answer: str
    # SQL results (if applicable)
    sql: str | None = None
    sql_result: dict | None = None
    # RAG results (if applicable)
    rag_sources: list | None = None
    citations: list | None = None
    # Metadata
    success: bool = True
    retries: int = 0


class QueryRouter:
    """Route queries to appropriate handlers."""

    def __init__(self, llm: AsyncOpenAI, model: str):
        self.llm = llm
        self.model = model

    async def classify_intent(self, question: str) -> QueryIntent:
        """Classify the intent of a user query."""
        prompt = f"""分析用户问题的意图，判断应该使用哪种查询方式。

问题：{question}

选项：
A. SQL - 问题涉及数据库查询（如统计、筛选数据记录）
B. RAG - 问题涉及文档内容查询（如合同条款、规定说明）
C. HYBRID - 问题同时涉及数据库和文档
D. GENERAL - 一般性问题，不需要查询

只输出选项字母（A/B/C/D）："""

        response = await self._call_llm(prompt)
        response = response.strip().upper()

        mapping = {
            'A': QueryIntent.SQL,
            'B': QueryIntent.RAG,
            'C': QueryIntent.HYBRID,
            'D': QueryIntent.GENERAL
        }
        return mapping.get(response, QueryIntent.GENERAL)

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with prompt."""
        response = await self.llm.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=50
        )
        return response.choices[0].message.content or ""


class UnifiedAgent:
    """Unified agent supporting both SQL queries and document RAG."""

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        max_retries: int = 3
    ):
        self.api_base = api_base or config.OPENAI_API_BASE
        self.api_key = api_key or config.OPENAI_API_KEY
        self.model = model or config.DEFAULT_MODEL
        self.max_retries = max_retries

        # LLM Client
        self.llm = AsyncOpenAI(
            base_url=self.api_base,
            api_key=self.api_key
        )

        # SQL Agent
        self.sql_agent = Text2SQLAgent(
            api_base=self.api_base,
            api_key=self.api_key,
            model=self.model,
            max_retries=max_retries
        )

        # RAG Pipeline (lazy init)
        self._rag: RAGPipeline | None = None

        # Query Router
        self.router = QueryRouter(self.llm, self.model)

        # Current database
        self.current_db = config.DEFAULT_DATABASE

    async def _get_rag(self) -> RAGPipeline:
        """Get RAG pipeline (lazy init)."""
        if self._rag is None:
            self._rag = RAGPipeline(
                llm_client=self.llm,
                model=self.model
            )
            await self._rag.initialize()
        return self._rag

    async def close(self):
        """Close all connections."""
        await self.sql_agent.close()
        if self._rag:
            await self._rag.close()

    # ==================== SQL Operations ====================

    async def list_databases(self) -> list[str]:
        """List all SQL databases."""
        return await self.sql_agent.list_databases()

    async def switch_database(self, db_name: str) -> dict:
        """Switch SQL database."""
        result = await self.sql_agent.switch_database(db_name)
        if result.get("success"):
            self.current_db = db_name
        return result

    async def get_schema_text(self) -> str:
        """Get SQL schema."""
        return await self.sql_agent.get_schema_text()

    async def execute_sql(self, sql: str) -> dict:
        """Execute SQL directly."""
        return await self.sql_agent.execute_sql(sql)

    # ==================== RAG Operations ====================

    async def ingest_documents(self, reset: bool = False) -> int:
        """Ingest documents into RAG."""
        rag = await self._get_rag()
        if reset:
            rag.milvus.drop_collection()
            rag.milvus.create_collection()
        return await rag.ingest_all_pdfs()

    async def rag_query(
        self,
        question: str,
        top_k: int = 10,
        filters: dict | None = None
    ) -> RAGResponse:
        """Query RAG directly."""
        rag = await self._get_rag()
        return await rag.query(question, top_k=top_k, filters=filters)

    # ==================== Unified Interface ====================

    async def chat(
        self,
        question: str,
        intent: QueryIntent | None = None,
        auto_route: bool = True
    ) -> UnifiedResponse:
        """Process user question with automatic routing.

        Args:
            question: User question
            intent: Override intent (skip routing if provided)
            auto_route: Whether to auto-route (default True)

        Returns:
            UnifiedResponse with results
        """
        # Classify intent if not provided
        if intent is None and auto_route:
            intent = await self.router.classify_intent(question)
        elif intent is None:
            intent = QueryIntent.GENERAL

        logger.info(f"Query intent: {intent.value}")

        # Route to appropriate handler
        if intent == QueryIntent.SQL:
            return await self._handle_sql(question)
        elif intent == QueryIntent.RAG:
            return await self._handle_rag(question)
        elif intent == QueryIntent.HYBRID:
            return await self._handle_hybrid(question)
        else:
            return await self._handle_general(question)

    async def _handle_sql(self, question: str) -> UnifiedResponse:
        """Handle SQL query."""
        result = await self.sql_agent.chat(question)

        return UnifiedResponse(
            query=question,
            intent=QueryIntent.SQL,
            answer=self._format_sql_answer(result),
            sql=result.get("sql"),
            sql_result=result.get("result"),
            success=result.get("success", False),
            retries=result.get("retries", 0)
        )

    async def _handle_rag(self, question: str) -> UnifiedResponse:
        """Handle RAG query."""
        rag = await self._get_rag()
        result = await rag.query(question)

        return UnifiedResponse(
            query=question,
            intent=QueryIntent.RAG,
            answer=result.answer,
            rag_sources=[
                {
                    "chunk_id": s.chunk_id,
                    "content": s.content[:200] + "...",
                    "score": s.combined_score,
                    "doc_name": s.metadata.get("doc_name", "")
                }
                for s in result.sources
            ],
            citations=[
                {
                    "id": c.citation_id,
                    "doc_name": c.doc_name,
                    "pages": c.pages
                }
                for c in result.citations
            ],
            success=True
        )

    async def _handle_hybrid(self, question: str) -> UnifiedResponse:
        """Handle hybrid query (both SQL and RAG)."""
        # Run both in parallel
        sql_task = self._handle_sql(question)
        rag_task = self._handle_rag(question)

        sql_result, rag_result = await asyncio.gather(
            sql_task, rag_task, return_exceptions=True
        )

        # Combine results
        combined_answer = ""

        if isinstance(sql_result, UnifiedResponse) and sql_result.success:
            combined_answer += "**数据查询结果：**\n"
            combined_answer += sql_result.answer + "\n\n"

        if isinstance(rag_result, UnifiedResponse) and rag_result.success:
            combined_answer += "**文档查询结果：**\n"
            combined_answer += rag_result.answer

        return UnifiedResponse(
            query=question,
            intent=QueryIntent.HYBRID,
            answer=combined_answer,
            sql=sql_result.sql if isinstance(sql_result, UnifiedResponse) else None,
            sql_result=sql_result.sql_result if isinstance(sql_result, UnifiedResponse) else None,
            rag_sources=rag_result.rag_sources if isinstance(rag_result, UnifiedResponse) else None,
            citations=rag_result.citations if isinstance(rag_result, UnifiedResponse) else None,
            success=True
        )

    async def _handle_general(self, question: str) -> UnifiedResponse:
        """Handle general chat."""
        response = await self.llm.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": question}],
            temperature=0.7,
            max_tokens=500
        )

        return UnifiedResponse(
            query=question,
            intent=QueryIntent.GENERAL,
            answer=response.choices[0].message.content or "",
            success=True
        )

    def _format_sql_answer(self, result: dict) -> str:
        """Format SQL result as readable answer."""
        if not result.get("success"):
            return f"查询失败: {result.get('error', '未知错误')}"

        sql_result = result.get("result", {})
        rows = sql_result.get("rows", [])
        row_count = sql_result.get("row_count", 0)

        answer = f"执行SQL:\n```sql\n{result.get('sql', '')}\n```\n\n"
        answer += f"查询到 {row_count} 条记录。\n"

        if rows:
            answer += "\n结果预览:\n"
            for i, row in enumerate(rows[:5]):
                answer += f"{i + 1}. {row}\n"

        return answer


# Convenience function
async def create_unified_agent() -> UnifiedAgent:
    """Create and initialize a unified agent."""
    agent = UnifiedAgent()
    # Pre-connect SQL agent
    await agent.sql_agent._get_mcp()
    return agent