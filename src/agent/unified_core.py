"""Unified Agent with Function Calling support."""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from ..config import config
from .core import Text2SQLAgent
from .tools import get_tools
from ..rag.pipeline import RAGPipeline, RAGResponse
from ..mcp_server.calculator_tools import CalculatorTools
from ..mcp_server.document_tools import DocumentTools

logger = logging.getLogger(__name__)


@dataclass
class UnifiedResponse:
    """统一响应"""
    query: str
    answer: str
    tool_calls: list[dict] = field(default_factory=list)
    success: bool = True


class UnifiedAgent:
    """统一 Agent，使用 Function Calling 自动路由请求"""

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

        # 工具定义
        self.tools = get_tools()

        # SQL Agent
        self.sql_agent = Text2SQLAgent(
            api_base=self.api_base,
            api_key=self.api_key,
            model=self.model,
            max_retries=max_retries
        )

        # RAG Pipeline (lazy init)
        self._rag: RAGPipeline | None = None

        # 工具实例
        self.calculator_tools = CalculatorTools()
        self.document_tools = DocumentTools()

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

    # ==================== Tool Execution ====================

    async def _execute_tool(self, name: str, arguments: dict) -> dict:
        """执行工具调用"""
        try:
            match name:
                # SQL 工具
                case "execute_sql":
                    return await self.sql_agent.execute_sql(arguments["sql"])
                case "get_schema":
                    return {"schema": await self.sql_agent.get_schema_text()}
                case "switch_database":
                    return await self.sql_agent.switch_database(arguments["db_name"])
                case "list_databases":
                    dbs = await self.sql_agent.list_databases()
                    return {"databases": dbs, "count": len(dbs)}
                # RAG 工具
                case "rag_query":
                    result = await self.rag_query(arguments["question"])
                    return {
                        "answer": result.answer,
                        "sources": [
                            {
                                "content": s.content[:200] + "..." if len(s.content) > 200 else s.content,
                                "doc_name": s.metadata.get("doc_name", ""),
                                "score": s.combined_score
                            }
                            for s in result.sources[:5]
                        ]
                    }
                # 计算器工具
                case "calculate":
                    return self.calculator_tools.calculate(arguments["expression"])
                # 文档工具
                case "read_file":
                    return await self.document_tools.read_file(arguments["path"])
                case "write_file":
                    return await self.document_tools.write_file(
                        arguments["path"],
                        arguments["content"],
                        arguments.get("mode", "write")
                    )
                case "edit_file":
                    return await self.document_tools.edit_file(
                        arguments["path"],
                        arguments["old_text"],
                        arguments["new_text"],
                        arguments.get("replace_all", False)
                    )
                case _:
                    return {"error": f"未知工具: {name}"}
        except Exception as e:
            return {"error": str(e)}

    # ==================== Unified Interface ====================

    async def chat(
        self,
        question: str,
        max_tool_calls: int = 10
    ) -> UnifiedResponse:
        """处理用户问题，使用 Function Calling 自动路由。

        Args:
            question: 用户问题
            max_tool_calls: 最大工具调用次数，默认 10

        Returns:
            UnifiedResponse 包含答案和工具调用历史
        """
        messages: list[dict] = [{"role": "user", "content": question}]
        tool_call_history: list[dict] = []

        # 构建系统提示，引导模型使用工具
        system_prompt = """你是一个智能助手。当用户提问时：
1. 如果需要使用工具，返回 JSON 格式：{"name": "工具名", "arguments": {参数}}
2. 收到工具执行结果后，直接用自然语言回答用户问题，不要再返回 JSON

可用工具：
- list_databases: 列出所有数据库
- get_schema: 获取数据库结构
- switch_database: 切换数据库（参数: db_name）
- execute_sql: 执行 SQL 查询（参数: sql）
- rag_query: 文档问答（参数: question）
- calculate: 数学计算（参数: expression）
- read_file: 读取文件（参数: path）
- write_file: 写入文件（参数: path, content, mode可选）
- edit_file: 编辑文件（参数: path, old_text, new_text）

重要：每条消息只能返回一个工具调用。收到结果后直接回答，不要继续调用工具。"""

        messages.insert(0, {"role": "system", "content": system_prompt})

        for iteration in range(max_tool_calls):
            # 调用 LLM
            response = await self.llm.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1
            )

            message = response.choices[0].message
            content = message.content or ""

            # 尝试从文本中解析工具调用
            tool_calls = self._parse_tool_calls_from_text(content)

            # 无工具调用，返回最终回答
            if not tool_calls:
                return UnifiedResponse(
                    query=question,
                    answer=content,
                    tool_calls=tool_call_history,
                    success=True
                )

            # 将助手消息加入历史
            messages.append({"role": "assistant", "content": content})

            # 执行每个工具调用
            for tool_call in tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call.get("arguments", {})

                logger.info(f"Tool call: {tool_name}({tool_args})")

                # 执行工具
                result = await self._execute_tool(tool_name, tool_args)

                # 记录工具调用历史
                tool_call_history.append({
                    "tool": tool_name,
                    "arguments": tool_args,
                    "result": result
                })

                # 工具结果加入消息历史，明确要求模型直接回答
                messages.append({
                    "role": "user",
                    "content": f"工具执行结果：\n{json.dumps(result, ensure_ascii=False, indent=2)}\n\n请根据以上结果直接回答用户的问题，不要再调用工具。"
                })

                # 每次只执行一个工具调用，然后让模型决定是否继续
                break

        # 达到最大调用次数，强制生成回答
        logger.warning(f"达到最大工具调用次数 {max_tool_calls}，强制生成回答")
        final_response = await self.llm.chat.completions.create(
            model=self.model,
            messages=messages + [{"role": "user", "content": "请基于以上信息给出最终回答。"}]
        )

        return UnifiedResponse(
            query=question,
            answer=final_response.choices[0].message.content or "",
            tool_calls=tool_call_history,
            success=True
        )

    def _parse_tool_calls_from_text(self, text: str) -> list[dict]:
        """从文本中解析工具调用 JSON"""
        tool_calls = []

        # 匹配 ```json ... ``` 格式
        json_pattern = r'```json\s*\n(.*?)\n```'
        matches = re.findall(json_pattern, text, re.DOTALL)

        for match in matches:
            try:
                data = json.loads(match.strip())
                if isinstance(data, dict) and "name" in data:
                    tool_calls.append(data)
            except json.JSONDecodeError:
                continue

        # 如果没找到 JSON 块，尝试直接解析 JSON 对象
        if not tool_calls:
            # 匹配 {"name": "...", "arguments": {...}} 格式
            obj_pattern = r'\{[^{}]*"name"\s*:\s*"[^"]+")[^{}]*\}'
            for match in re.finditer(r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}', text):
                try:
                    data = json.loads(match.group())
                    if isinstance(data, dict) and "name" in data:
                        tool_calls.append(data)
                except json.JSONDecodeError:
                    continue

        return tool_calls


# Convenience function
async def create_unified_agent() -> UnifiedAgent:
    """Create and initialize a unified agent."""
    agent = UnifiedAgent()
    # Pre-connect SQL agent
    await agent.sql_agent._get_mcp()
    return agent