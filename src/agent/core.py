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

    async def _fix_sql(
        self,
        sql: str,
        error: str,
        question: str,
        schema_text: str | None = None,
        fix_history: list | None = None
    ) -> str:
        """修复 SQL

        Args:
            sql: 执行失败的 SQL
            error: 错误信息
            question: 原始用户问题
            schema_text: 数据库 Schema
            fix_history: 之前的修复历史

        Returns:
            修复后的 SQL
        """
        prompt = build_fix_prompt(sql, error, question, schema_text, fix_history)
        response = await self._call_llm("你是 SQL 专家，擅长分析和修复 SQL 错误。", prompt)
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
                "sql": str,              # 最终执行的 SQL
                "result": dict,          # 执行结果
                "explanation": str,      # 结果解释（可选）
                "success": bool,         # 是否成功
                "retries": int,          # 重试次数
                "rewrite_info": dict,    # 查询重写信息（可选）
                "fix_info": dict         # SQL 修复信息（可选）
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

        # 2. 执行 SQL（带重试和自动修复）
        result = None
        success = False
        retries = 0
        fix_history: list[dict] = []  # 记录修复历史
        schema_text = None  # 用于修复时提供上下文

        while retries < self.max_retries:
            result = await self.execute_sql(sql)

            if result.get("success"):
                success = True
                break

            if not auto_fix:
                break

            # 记录失败的尝试
            error_msg = result.get("error", "未知错误")
            fix_history.append({
                "attempt": retries + 1,
                "sql": sql,
                "error": error_msg
            })

            logger.warning(f"SQL execution failed (attempt {retries + 1}): {error_msg}")

            # 获取 Schema 用于修复（只获取一次）
            if schema_text is None:
                try:
                    schema_text = await self.get_schema_text()
                except Exception as e:
                    logger.warning(f"Failed to get schema for fix: {e}")

            # 尝试修复 SQL
            logger.info(f"Attempting to fix SQL (attempt {retries + 1})...")
            sql = await self._fix_sql(
                sql=sql,
                error=error_msg,
                question=processed_question,
                schema_text=schema_text,
                fix_history=fix_history
            )
            retries += 1

        # 构建修复信息
        fix_info = None
        if fix_history:
            fix_info = {
                "attempts": len(fix_history),
                "history": fix_history,
                "final_success": success
            }
            if success:
                logger.info(f"SQL fixed successfully after {retries} attempts")
            else:
                logger.error(f"SQL fix failed after {retries} attempts")

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
            "rewrite_info": rewrite_info,
            "fix_info": fix_info
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