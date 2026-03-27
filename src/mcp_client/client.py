"""MCP Client implementation."""

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClient:
    """MCP Client，用于连接 MCP Server 并调用工具"""

    def __init__(self):
        self.session: ClientSession | None = None
        self._read_stream = None
        self._write_stream = None
        self._tools_cache: list | None = None

    async def connect(self, server_command: list[str] | None = None):
        """连接到 MCP Server

        Args:
            server_command: 启动 MCP Server 的命令，默认使用当前项目的 server
        """
        if server_command is None:
            # 默认使用当前项目的 MCP Server
            server_command = [sys.executable, "-m", "src.mcp_server.server"]

        server_params = StdioServerParameters(
            command=server_command[0],
            args=server_command[1:] if len(server_command) > 1 else [],
            env=None
        )

        self._client = stdio_client(server_params)
        self._read_stream, self._write_stream = await self._client.__aenter__()
        self.session = ClientSession(self._read_stream, self._write_stream)
        await self.session.__aenter__()

        # 初始化连接
        await self.session.initialize()

    async def disconnect(self):
        """断开与 MCP Server 的连接"""
        if self.session:
            await self.session.__aexit__(None, None, None)
            self.session = None
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None

    async def list_tools(self) -> list[dict]:
        """列出所有可用工具"""
        if self._tools_cache is not None:
            return self._tools_cache

        if not self.session:
            raise RuntimeError("未连接到 MCP Server")

        result = await self.session.list_tools()
        self._tools_cache = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema
            }
            for tool in result.tools
        ]
        return self._tools_cache

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """调用 MCP Tool

        Args:
            name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        if not self.session:
            raise RuntimeError("未连接到 MCP Server")

        result = await self.session.call_tool(name, arguments or {})

        # 解析结果
        if result.content:
            text_content = result.content[0]
            if hasattr(text_content, 'text'):
                try:
                    return json.loads(text_content.text)
                except json.JSONDecodeError:
                    return {"result": text_content.text}

        return {"result": None}

    # ===== 便捷方法 =====

    async def list_databases(self) -> list[str]:
        """列出所有可用数据库"""
        result = await self.call_tool("list_databases")
        return result.get("databases", [])

    async def switch_database(self, db_name: str) -> dict:
        """切换数据库"""
        return await self.call_tool("switch_database", {"db_name": db_name})

    async def get_schema(self) -> dict:
        """获取数据库 Schema"""
        return await self.call_tool("get_schema")

    async def get_schema_text(self) -> str:
        """获取 Schema 文本描述"""
        result = await self.call_tool("get_schema_text")
        return result.get("schema", "")

    async def execute_sql(self, sql: str) -> dict:
        """执行 SQL"""
        return await self.call_tool("execute_sql", {"sql": sql})

    async def explain_schema(self, table_name: str | None = None) -> str:
        """解释表结构"""
        args = {"table_name": table_name} if table_name else {}
        result = await self.call_tool("explain_schema", args)
        return result.get("explanation", "")


@asynccontextmanager
async def create_mcp_client(server_command: list[str] | None = None):
    """创建 MCP Client 的上下文管理器

    Usage:
        async with create_mcp_client() as client:
            databases = await client.list_databases()
    """
    client = MCPClient()
    try:
        await client.connect(server_command)
        yield client
    finally:
        await client.disconnect()