"""MCP Server main program."""

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .tools import SQLExecutorTools
from .calculator_tools import CalculatorTools
from .document_tools import DocumentTools


# 创建 MCP Server 实例
server = Server("text2sql-server")

# 创建工具实例
sql_tools = SQLExecutorTools()
calculator_tools = CalculatorTools()
document_tools = DocumentTools()


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
        # 计算器工具
        Tool(
            name="calculate",
            description="执行数学计算，支持四则运算和百分比",
            inputSchema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 '100 + 50 * 2' 或 '100 * 20%'"
                    }
                },
                "required": ["expression"]
            }
        ),
        # 文档工具
        Tool(
            name="read_file",
            description="读取文件内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（绝对路径或相对路径）"
                    }
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="write_file",
            description="写入或追加文件内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "写入内容"
                    },
                    "mode": {
                        "type": "string",
                        "description": "写入模式：'write'（覆盖）或 'append'（追加）",
                        "enum": ["write", "append"],
                        "default": "write"
                    }
                },
                "required": ["path", "content"]
            }
        ),
        Tool(
            name="edit_file",
            description="编辑文件，替换指定文本",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径"
                    },
                    "old_text": {
                        "type": "string",
                        "description": "要替换的文本"
                    },
                    "new_text": {
                        "type": "string",
                        "description": "替换后的文本"
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "是否替换所有匹配项，默认 false",
                        "default": false
                    }
                },
                "required": ["path", "old_text", "new_text"]
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

        # 计算器工具
        case "calculate":
            expression = arguments.get("expression")
            if not expression:
                return {"success": False, "error": "缺少参数: expression"}
            return calculator_tools.calculate(expression)

        # 文档工具
        case "read_file":
            path = arguments.get("path")
            if not path:
                return {"success": False, "error": "缺少参数: path"}
            return await document_tools.read_file(path)

        case "write_file":
            path = arguments.get("path")
            content = arguments.get("content")
            mode = arguments.get("mode", "write")
            if not path:
                return {"success": False, "error": "缺少参数: path"}
            if content is None:
                return {"success": False, "error": "缺少参数: content"}
            return await document_tools.write_file(path, content, mode)

        case "edit_file":
            path = arguments.get("path")
            old_text = arguments.get("old_text")
            new_text = arguments.get("new_text")
            replace_all = arguments.get("replace_all", False)
            if not path:
                return {"success": False, "error": "缺少参数: path"}
            if not old_text:
                return {"success": False, "error": "缺少参数: old_text"}
            if not new_text:
                return {"success": False, "error": "缺少参数: new_text"}
            return await document_tools.edit_file(path, old_text, new_text, replace_all)

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