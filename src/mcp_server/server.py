"""MCP Server main program."""

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .tools import SQLExecutorTools


# 创建 MCP Server 实例
server = Server("text2sql-server")

# 创建工具实例
sql_tools = SQLExecutorTools()


@server.list_tools()
async def list_tools() -> list[Tool]:
    """列出所有可用的 MCP Tools"""
    return [
        Tool(
            name="list_databases",
            description="列出所有可用的 SQLite 数据库",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="switch_database",
            description="切换当前使用的数据库",
            inputSchema={
                "type": "object",
                "properties": {
                    "db_name": {
                        "type": "string",
                        "description": "数据库名称，如 bakery_1"
                    }
                },
                "required": ["db_name"]
            }
        ),
        Tool(
            name="get_schema",
            description="获取当前数据库的表结构信息，包括表名、字段、类型、外键关系",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="get_schema_text",
            description="获取当前数据库 Schema 的文本描述，适合 LLM 理解",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="execute_sql",
            description="执行 SQL 查询并返回结果",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "要执行的 SQL 语句"
                    }
                },
                "required": ["sql"]
            }
        ),
        Tool(
            name="explain_schema",
            description="用自然语言解释指定表的结构和用途",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "表名，可选，不传则解释所有表"
                    }
                }
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """处理工具调用"""
    try:
        result = await dispatch_tool(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


async def dispatch_tool(name: str, arguments: dict[str, Any]) -> Any:
    """分发工具调用到对应的处理函数"""
    match name:
        case "list_databases":
            dbs = await sql_tools.list_databases()
            return {"databases": dbs, "count": len(dbs)}

        case "switch_database":
            db_name = arguments.get("db_name")
            if not db_name:
                return {"error": "缺少参数: db_name"}
            return await sql_tools.switch_database(db_name)

        case "get_schema":
            return await sql_tools.get_schema()

        case "get_schema_text":
            return {"schema": await sql_tools.get_schema_text()}

        case "execute_sql":
            sql = arguments.get("sql")
            if not sql:
                return {"error": "缺少参数: sql"}
            return await sql_tools.execute_sql(sql)

        case "explain_schema":
            table_name = arguments.get("table_name")
            return {"explanation": await sql_tools.explain_schema(table_name)}

        case _:
            return {"error": f"未知工具: {name}"}


async def run_server():
    """启动 MCP Server"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main():
    """CLI 入口"""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()