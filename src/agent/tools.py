"""Tool definitions for Function Calling."""

from typing import Any

# 工具定义 - OpenAI Function Calling 格式
TOOLS: list[dict[str, Any]] = [
    # SQL 工具
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": "执行 SQL 查询并返回结果。用于数据库查询操作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "要执行的 SQL 查询语句"
                    }
                },
                "required": ["sql"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_schema",
            "description": "获取当前数据库的表结构信息，包括表名、字段、类型。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "switch_database",
            "description": "切换当前使用的数据库",
            "parameters": {
                "type": "object",
                "properties": {
                    "db_name": {
                        "type": "string",
                        "description": "数据库名称"
                    }
                },
                "required": ["db_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_databases",
            "description": "列出所有可用的数据库",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    # RAG 工具
    {
        "type": "function",
        "function": {
            "name": "rag_query",
            "description": "从文档库中检索信息回答问题。用于查询合同条款、规定说明等文档内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "要查询的问题"
                    }
                },
                "required": ["question"]
            }
        }
    },
    # 计算器工具
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "执行数学计算，支持四则运算和百分比。例如：'100 + 50 * 2' 或 '100 * 20%'",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    # 文档工具
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入或追加文件内容。会自动创建不存在的目录。",
            "parameters": {
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
                        "enum": ["write", "append"],
                        "description": "写入模式：write（覆盖）或 append（追加）",
                        "default": "write"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "编辑文件，替换指定的文本内容",
            "parameters": {
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
                        "default": False
                    }
                },
                "required": ["path", "old_text", "new_text"]
            }
        }
    },
]


def get_tools() -> list[dict[str, Any]]:
    """获取工具定义列表"""
    return TOOLS


def get_tool_names() -> list[str]:
    """获取所有工具名称"""
    return [tool["function"]["name"] for tool in TOOLS]