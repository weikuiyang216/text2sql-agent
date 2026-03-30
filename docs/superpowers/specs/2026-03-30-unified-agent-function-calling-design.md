# 统一 Agent Function Calling 设计文档

## 概述

重构 `UnifiedAgent`，移除意图分类，使用 Function Calling 自动路由所有请求。LLM 自动判断是否需要调用工具（SQL、RAG、计算器、文件操作等），支持多轮工具调用直到任务完成。

## 需求

- **统一入口**：用户只需调用 `/unified/chat`，LLM 自动决定调用哪些工具
- **Function Calling**：使用 OpenAI 兼容 API 的原生 Function Calling 能力
- **多轮调用**：支持 Agent 循环模式，LLM 可多次调用工具
- **可配置上限**：最大工具调用次数可配置，防止无限循环

## 架构

### 改动概览

```
src/agent/
├── unified_core.py     # 重构 - 移除意图分类，添加 Function Calling 循环
└── tools.py            # 新建 - 工具定义注册

src/api/server.py       # 简化 - 只保留 /unified/chat 入口
```

### 工具注册表

| 工具名 | 类型 | 说明 |
|--------|------|------|
| `execute_sql` | 同步 | 执行 SQL 查询 |
| `get_schema` | 同步 | 获取数据库结构 |
| `switch_database` | 同步 | 切换数据库 |
| `rag_query` | 异步 | RAG 文档问答 |
| `calculate` | 同步 | 数学计算 |
| `read_file` | 异步 | 读取文件 |
| `write_file` | 异步 | 写入文件 |
| `edit_file` | 异步 | 编辑文件 |

### Agent 循环流程

```
┌─────────────────────────────────────────────────────┐
│                   用户问题                           │
└─────────────────────┬───────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────┐
│              LLM (带工具定义)                        │
│  - 判断是否需要调用工具                              │
│  - 生成工具调用请求或最终回答                        │
└─────────────────────┬───────────────────────────────┘
                      ▼
              ┌───────────────┐
              │ 需要调用工具？ │
              └───────┬───────┘
           是 │             │ 否
              ▼             ▼
    ┌─────────────────┐   ┌─────────────────┐
    │   执行工具调用   │   │   返回最终回答   │
    └────────┬────────┘   └─────────────────┘
             │
             ▼
    ┌─────────────────┐
    │ 结果加入消息历史 │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────────┐
    │ 调用次数 < max ?    │
    └────────┬────────────┘
         是 │      │ 否
             ▼      ▼
    返回 LLM 循环   强制返回当前回答
```

## 实现细节

### 工具定义格式

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "执行数学计算，支持四则运算和百分比",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 '100 + 50 * 2'"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    # ... 其他工具
]
```

### Agent 核心循环

```python
async def chat(self, question: str, max_tool_calls: int = 10) -> UnifiedResponse:
    messages = [{"role": "user", "content": question}]

    for i in range(max_tool_calls):
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
                answer=message.content,
                tool_calls=self._tool_call_history,
                success=True
            )

        # 将助手消息加入历史
        messages.append(message)

        # 执行每个工具调用
        for tool_call in message.tool_calls:
            result = await self._execute_tool(
                tool_call.function.name,
                json.loads(tool_call.function.arguments)
            )

            # 工具结果加入历史
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False)
            })

            self._tool_call_history.append({
                "tool": tool_call.function.name,
                "arguments": json.loads(tool_call.function.arguments),
                "result": result
            })

    # 达到最大调用次数，强制生成回答
    final_response = await self.llm.chat.completions.create(
        model=self.model,
        messages=messages + [{"role": "user", "content": "请基于以上信息给出最终回答。"}]
    )

    return UnifiedResponse(
        query=question,
        answer=final_response.choices[0].message.content,
        tool_calls=self._tool_call_history,
        success=True
    )
```

### 响应模型

```python
@dataclass
class UnifiedResponse:
    """统一响应"""
    query: str
    answer: str
    tool_calls: list[dict]  # 工具调用历史
    success: bool
```

### 工具执行分发

```python
async def _execute_tool(self, name: str, arguments: dict) -> dict:
    """执行工具调用"""
    match name:
        case "execute_sql":
            return await self.sql_agent.execute_sql(arguments["sql"])
        case "get_schema":
            return {"schema": await self.sql_agent.get_schema_text()}
        case "switch_database":
            return await self.sql_agent.switch_database(arguments["db_name"])
        case "rag_query":
            result = await self.rag_query(arguments["question"])
            return {"answer": result.answer, "sources": [...]}
        case "calculate":
            return self.calculator_tools.calculate(arguments["expression"])
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
```

## API 变更

### 简化端点

移除独立的 `/tools/*` 端点，只保留统一入口：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/unified/chat` | POST | 统一问答入口 |
| `/rag/ingest` | POST | 文档摄入（保留） |
| `/rag/stats` | GET | RAG 统计（保留） |

### 请求/响应模型

```python
class UnifiedChatRequest(BaseModel):
    question: str
    max_tool_calls: int = 10  # 可选，默认 10

class UnifiedChatResponse(BaseModel):
    query: str
    answer: str
    tool_calls: list[dict]  # 工具调用记录
    success: bool
```

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `src/agent/unified_core.py` | 重构 - 移除意图分类，添加 Function Calling 循环 |
| `src/agent/tools.py` | 新建 - 工具定义注册表 |
| `src/api/server.py` | 简化 - 移除 `/tools/*` 端点，更新响应模型 |

## 测试场景

```python
# 场景 1：SQL 查询
question = "找出所有价格低于5元的商品"
# → LLM 调用 get_schema → execute_sql → 返回结果

# 场景 2：计算
question = "帮我计算 100 * 20% + 50"
# → LLM 调用 calculate → 返回 70.0

# 场景 3：文件操作
question = "读取 /tmp/test.txt 文件内容"
# → LLM 调用 read_file → 返回内容

# 场景 4：混合操作
question = "查询商品总数并写入文件 /tmp/count.txt"
# → LLM 调用 execute_sql → write_file → 返回完成

# 场景 5：RAG 问答
question = "合同中关于提前还款的规定是什么？"
# → LLM 调用 rag_query → 返回答案
```