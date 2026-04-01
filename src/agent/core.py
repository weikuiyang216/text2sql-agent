"""Text-to-SQL Agent core implementation."""

import logging
from typing import Any

from openai import AsyncOpenAI

from ..config import config
from ..mcp_client.client import MCPClient, create_mcp_client
from .prompts import (
    build_system_prompt,
    build_user_prompt,
    build_fix_prompt,
    build_explain_prompt,
    extract_sql
)
from .history import ConversationHistory, ConversationTurn
from .query_rewriter import SQLQueryRewriter, parse_time_expressions

logger = logging.getLogger(__name__)


class Text2SQLAgent:
    """Text-to-SQL Agent"""

    def __init__(
        self,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        max_retries: int = 3,
        enable_query_rewrite: bool = True
    ):
        self.api_base = api_base or config.OPENAI_API_BASE
        self.api_key = api_key or config.OPENAI_API_KEY
        self.model = model or config.DEFAULT_MODEL
        self.max_retries = max_retries
        self.enable_query_rewrite = enable_query_rewrite

        # LLM Client
        self.llm = AsyncOpenAI(
            base_url=self.api_base,
            api_key=self.api_key
        )

        # MCP Client (延迟初始化)
        self._mcp: MCPClient | None = None

        # 对话历史
        self.history = ConversationHistory()

        # 当前数据库
        self.current_db = config.DEFAULT_DATABASE

        # Query Rewriter
        self._query_rewriter: SQLQueryRewriter | None = None

    async def _get_mcp(self) -> MCPClient:
        """获取 MCP Client（懒加载）"""
        if self._mcp is None:
            self._mcp = MCPClient()
            await self._mcp.connect()
        return self._mcp

    def _get_query_rewriter(self) -> SQLQueryRewriter:
        """获取 Query Rewriter（懒加载）"""
        if self._query_rewriter is None:
            self._query_rewriter = SQLQueryRewriter(
                llm_client=self.llm,
                model=self.model
            )
        return self._query_rewriter

    async def close(self):
        """关闭连接"""
        if self._mcp:
            await self._mcp.disconnect()
            self._mcp = None

    async def list_databases(self) -> list[str]:
        """列出所有数据库"""
        mcp = await self._get_mcp()
        return await mcp.list_databases()

    async def switch_database(self, db_name: str) -> dict:
        """切换数据库"""
        mcp = await self._get_mcp()
        result = await mcp.switch_database(db_name)
        if result.get("success"):
            self.current_db = db_name
        return result

    async def get_schema_text(self) -> str:
        """获取 Schema 文本"""
        mcp = await self._get_mcp()
        return await mcp.get_schema_text()

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM"""
        response = await self.llm.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,  # 低温度，更确定的输出
        )
        return response.choices[0].message.content

    async def _generate_sql(self, question: str) -> str:
        """生成 SQL"""
        schema_text = await self.get_schema_text()
        system_prompt = build_system_prompt(schema_text)
        user_prompt = build_user_prompt(question, self.history.get_recent())

        response = await self._call_llm(system_prompt, user_prompt)
        return extract_sql(response)

    async def _fix_sql(self, sql: str, error: str, question: str) -> str:
        """修复 SQL"""
        prompt = build_fix_prompt(sql, error, question)
        response = await self._call_llm("你是 SQL 专家。", prompt)
        return extract_sql(response)

    async def execute_sql(self, sql: str) -> dict:
        """执行 SQL"""
        mcp = await self._get_mcp()
        return await mcp.execute_sql(sql)

    async def chat(self, question: str, auto_fix: bool = True, explain: bool = False) -> dict[str, Any]:
        """处理用户问题

        Args:
            question: 用户问题
            auto_fix: 是否自动修复 SQL 错误
            explain: 是否解释结果

        Returns:
            {
                "sql": str,
                "result": dict,
                "explanation": str | None,
                "success": bool,
                "rewrite_info": dict | None  # 重写信息
            }
        """
        rewrite_info = None
        processed_question = question

        # 0. Query 重写（可选）
        if self.enable_query_rewrite:
            try:
                rewriter = self._get_query_rewriter()
                schema_text = await self.get_schema_text()
                rewrite_result = await rewriter.rewrite(
                    query=question,
                    schema_text=schema_text,
                    history=self.history.get_recent()
                )

                if rewrite_result.changes:
                    rewrite_info = {
                        "original": question,
                        "rewritten": rewrite_result.rewritten,
                        "changes": rewrite_result.changes,
                        "time_expressions": rewrite_result.time_expressions,
                        "entities": rewrite_result.entities
                    }
                    processed_question = rewrite_result.rewritten
                    logger.info(f"Query rewritten: {question} -> {processed_question}")
            except Exception as e:
                logger.warning(f"Query rewrite failed: {e}")

        # 1. 生成 SQL
        sql = await self._generate_sql(processed_question)

        # 2. 执行 SQL（带重试）
        result = None
        success = False
        retries = 0

        while retries < self.max_retries:
            result = await self.execute_sql(sql)

            if result.get("success"):
                success = True
                break

            if not auto_fix:
                break

            # 尝试修复
            error_msg = result.get("error", "未知错误")
            sql = await self._fix_sql(sql, error_msg, processed_question)
            retries += 1

        # 3. 可选解释
        explanation = None
        if explain and success and result:
            prompt = build_explain_prompt(sql, result)
            explanation = await self._call_llm("你是数据分析专家。", prompt)

        # 4. 记录历史
        turn = ConversationTurn(
            question=question,
            sql=sql,
            result=result or {},
            explanation=explanation or "",
            success=success
        )
        self.history.add_turn(turn)

        return {
            "sql": sql,
            "result": result,
            "explanation": explanation,
            "success": success,
            "retries": retries,
            "rewrite_info": rewrite_info
        }

    async def explain_result(self, sql: str, result: dict) -> str:
        """解释查询结果"""
        prompt = build_explain_prompt(sql, result)
        return await self._call_llm("你是数据分析专家。", prompt)


# 便捷函数
async def create_agent() -> Text2SQLAgent:
    """创建 Agent 实例"""
    agent = Text2SQLAgent()
    # 预连接 MCP
    await agent._get_mcp()
    return agent