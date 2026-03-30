# 统一 Agent Function Calling 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 UnifiedAgent，使用 Function Calling 自动路由所有请求，移除意图分类。

**Architecture:** 创建工具定义注册表，实现 Agent 循环模式，LLM 自动判断并调用工具（SQL、RAG、计算器、文件操作）直到任务完成。

**Tech Stack:** Python 3.10+, OpenAI Function Calling API, AsyncOpenAI

---

## 文件结构

```
src/agent/
├── unified_core.py     # 重构 - 移除意图分类，添加 Function Calling 循环
└── tools.py            # 新建 - 工具定义注册表

src/api/server.py       # 简化 - 移除 /tools/* 端点，更新响应模型
```

---

### Task 1: 创建工具定义注册表

**Files:**
- Create: `src/agent/tools.py`

- [ ] **Step 1: 创建工具定义文件**

```python
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
```

- [ ] **Step 2: 验证语法正确**

Run: `python -c "from src.agent.tools import TOOLS, get_tools; print(len(TOOLS), 'tools')"`
Expected: `9 tools`

- [ ] **Step 3: 提交**

```bash
git add src/agent/tools.py
git commit -m "feat: 添加 Function Calling 工具定义注册表"
```

---

### Task 2: 重构 UnifiedAgent（移除意图分类，添加 Function Calling）

**Files:**
- Modify: `src/agent/unified_core.py`

- [ ] **Step 1: 重写 unified_core.py**

完整替换文件内容：

```python
"""Unified Agent with Function Calling support."""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from ..config import config
from ..mcp_client.client import MCPClient
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
                                "content": s.content[:200] + "...",
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

        for iteration in range(max_tool_calls):
            # 调用 LLM
            response = await self.llm.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools,
                tool_choice="auto"
            )

            message = response.choices[0].message

            # 无工具调用，返回最终回答
            if not message.tool_calls:
                return UnifiedResponse(
                    query=question,
                    answer=message.content or "",
                    tool_calls=tool_call_history,
                    success=True
                )

            # 将助手消息加入历史
            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]
            })

            # 执行每个工具调用
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                logger.info(f"Tool call: {tool_name}({tool_args})")

                # 执行工具
                result = await self._execute_tool(tool_name, tool_args)

                # 记录工具调用历史
                tool_call_history.append({
                    "tool": tool_name,
                    "arguments": tool_args,
                    "result": result
                })

                # 工具结果加入消息历史
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False)
                })

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


# Convenience function
async def create_unified_agent() -> UnifiedAgent:
    """Create and initialize a unified agent."""
    agent = UnifiedAgent()
    # Pre-connect SQL agent
    await agent.sql_agent._get_mcp()
    return agent
```

- [ ] **Step 2: 验证语法正确**

Run: `python -c "from src.agent.unified_core import UnifiedAgent; print('OK')"`
Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add src/agent/unified_core.py
git commit -m "refactor: 重构 UnifiedAgent 使用 Function Calling"
```

---

### Task 3: 简化 API Server

**Files:**
- Modify: `src/api/server.py`

- [ ] **Step 1: 移除 `/tools/*` 端点，更新响应模型**

找到并删除以下端点（约第 357-410 行）：
- `/tools/calculate`
- `/tools/read_file`
- `/tools/write_file`
- `/tools/edit_file`

以及相关的请求/响应模型类：
- `CalculateRequest`, `CalculateResponse`
- `ReadFileRequest`, `ReadFileResponse`
- `WriteFileRequest`, `WriteFileResponse`
- `EditFileRequest`, `EditFileResponse`

- [ ] **Step 2: 更新 UnifiedChatResponse 模型**

找到 `UnifiedChatResponse` 类，替换为：

```python
class UnifiedChatResponse(BaseModel):
    """统一聊天响应"""
    query: str
    answer: str
    tool_calls: list[dict] = []
    success: bool
```

- [ ] **Step 3: 更新 `/unified/chat` 端点**

找到 `unified_chat` 函数，替换为：

```python
@app.post("/unified/chat", response_model=UnifiedChatResponse)
async def unified_chat(request: UnifiedChatRequest):
    """统一问答（自动路由 SQL/RAG/工具）"""
    if not unified_agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    try:
        result = await unified_agent.chat(
            question=request.question,
            max_tool_calls=request.max_tool_calls
        )

        return UnifiedChatResponse(
            query=result.query,
            answer=result.answer,
            tool_calls=result.tool_calls,
            success=result.success
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 4: 更新 UnifiedChatRequest 模型**

找到 `UnifiedChatRequest` 类，替换为：

```python
class UnifiedChatRequest(BaseModel):
    """统一聊天请求"""
    question: str
    max_tool_calls: int = 10
```

- [ ] **Step 5: 移除不再需要的导入**

删除以下导入（如果存在）：
```python
from ..mcp_server.calculator_tools import CalculatorTools
from ..mcp_server.document_tools import DocumentTools
```

以及删除全局实例（如果存在）：
```python
calculator_tools = CalculatorTools()
document_tools = DocumentTools()
```

- [ ] **Step 6: 验证语法正确**

Run: `python -m py_compile src/api/server.py && echo "OK"`
Expected: `OK`

- [ ] **Step 7: 提交**

```bash
git add src/api/server.py
git commit -m "refactor: 简化 API，移除独立工具端点"
```

---

### Task 4: 更新 README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 Web API 端点表格**

找到 Web API 部分，将端点表格更新为：

```markdown
### Web API

#### 统一入口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/unified/chat` | POST | 统一问答入口，自动路由 |

#### 其他端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/chat` | POST | 自然语言转 SQL 查询 |
| `/databases` | GET | 列出数据库 |
| `/database/switch` | POST | 切换数据库 |
| `/schema` | GET | 获取 Schema |
| `/sql/execute` | POST | 执行 SQL |
| `/rag/ingest` | POST | 摄入文档 |
| `/rag/stats` | GET | 获取 RAG 统计 |
```

- [ ] **Step 2: 更新 API 示例**

找到 API 示例部分，替换为：

```markdown
#### API 示例

```bash
# 统一问答（自动路由 SQL/RAG/工具）
curl -X POST http://localhost:8765/unified/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "找出所有价格低于5元的商品"}'

# SQL 查询
curl -X POST http://localhost:8765/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "找出所有价格低于5元的商品", "database": "bakery_1"}'

# RAG 文档问答
curl -X POST http://localhost:8765/unified/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "住房贷款合同中关于提前还款的规定是什么？"}'

# 数学计算
curl -X POST http://localhost:8765/unified/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "帮我计算 100 * 20% + 50"}'

# 文件操作
curl -X POST http://localhost:8765/unified/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "读取 /tmp/test.txt 文件内容"}'

# 混合操作
curl -X POST http://localhost:8765/unified/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "查询商品总数并写入文件 /tmp/count.txt"}'
```
```

- [ ] **Step 3: 移除旧的 curl 示例**

删除以下示例（如果存在）：
- `/tools/calculate` 示例
- `/tools/read_file` 示例
- `/tools/write_file` 示例
- `/tools/edit_file` 示例

- [ ] **Step 4: 提交**

```bash
git add README.md
git commit -m "docs: 更新 README 统一入口说明"
```

---

### Task 5: 验证功能

- [ ] **Step 1: 创建测试脚本**

```python
# test_unified_agent.py
"""测试统一 Agent Function Calling"""

import asyncio
from src.agent.unified_core import UnifiedAgent

async def test():
    agent = UnifiedAgent()
    await agent.sql_agent._get_mcp()  # 预连接

    # 测试 1: SQL 查询
    print("=" * 50)
    print("测试 1: SQL 查询")
    result = await agent.chat("列出所有可用的数据库")
    print(f"Answer: {result.answer[:200]}...")
    print(f"Tool calls: {[tc['tool'] for tc in result.tool_calls]}")

    # 测试 2: 计算
    print("\n" + "=" * 50)
    print("测试 2: 计算")
    result = await agent.chat("帮我计算 100 * 20% + 50")
    print(f"Answer: {result.answer}")
    print(f"Tool calls: {[tc['tool'] for tc in result.tool_calls]}")

    # 测试 3: 文件操作
    print("\n" + "=" * 50)
    print("测试 3: 文件操作")
    result = await agent.chat("写入文件 /tmp/test_unified.txt，内容为 'Hello World'")
    print(f"Answer: {result.answer}")
    print(f"Tool calls: {[tc['tool'] for tc in result.tool_calls]}")

    # 测试 4: 读取文件
    print("\n" + "=" * 50)
    print("测试 4: 读取文件")
    result = await agent.chat("读取 /tmp/test_unified.txt 文件内容")
    print(f"Answer: {result.answer}")
    print(f"Tool calls: {[tc['tool'] for tc in result.tool_calls]}")

    await agent.close()
    print("\n所有测试完成！")

if __name__ == "__main__":
    asyncio.run(test())
```

Run: `python test_unified_agent.py`

Expected: 每个测试正确调用相应工具并返回结果

- [ ] **Step 2: 清理测试文件**

Run: `rm test_unified_agent.py /tmp/test_unified.txt`

- [ ] **Step 3: 最终提交检查**

```bash
git status
git log --oneline -5
```

---

## 完成清单

- [ ] Task 1: 工具定义注册表创建完成
- [ ] Task 2: UnifiedAgent 重构完成
- [ ] Task 3: API Server 简化完成
- [ ] Task 4: README 更新完成
- [ ] Task 5: 功能验证通过