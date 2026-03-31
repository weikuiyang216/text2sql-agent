# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Text-to-SQL Agent 是基于 MCP (Model Context Protocol) 架构的智能助手，核心特性：
- **统一入口**: `/unified/chat` 使用 Function Calling 自动路由 SQL/RAG/计算器/文件操作
- **Text-to-SQL**: 自然语言转 SQL 查询，支持多数据库切换和 SQL 错误自动修复
- **Agentic RAG**: PDF 文档智能问答，支持向量检索和引用溯源
- **Agent 循环模式**: LLM 自动判断是否需要调用工具，复杂任务自动分解

## 常用命令

```bash
# 安装
pip install -e .

# 启动 Milvus（RAG 功能需要）
docker-compose up -d

# 启动 API 服务
python -m src.api.server
# 或
uvicorn src.api.server:app --host 0.0.0.0 --port 8765

# 启动 MCP Server
python -m src.mcp_server.server
```

### CLI 命令

```bash
text2sql chat --db bakery_1    # 交互式对话
text2sql list-db               # 列出数据库
text2sql schema --db bakery_1  # 显示 Schema
text2sql exec "SELECT * FROM goods LIMIT 5" --db bakery_1  # 执行 SQL
```

### 文档摄入（RAG）

```bash
python scripts/ingest_documents.py           # 摄入所有 PDF
python scripts/ingest_documents.py --reset   # 重置集合并重新摄入
python scripts/ingest_documents.py --file data/合同.pdf  # 单个文件
```

## 架构

### 核心模块

```
src/
├── config.py           # 配置管理（环境变量加载）
├── logging_config.py   # 日志配置（Rich 控制台输出）
├── mcp_server/         # MCP Server - 提供 SQL 执行工具
│   ├── server.py       # MCP Server 主程序
│   ├── tools.py        # SQL 执行工具
│   ├── sql_security.py # SQL 安全验证（防注入）
│   ├── calculator_tools.py  # 计算器工具
│   └── document_tools.py    # 文件操作工具
├── mcp_client/         # MCP Client - 与 MCP Server 通信
├── agent/              # Agent 核心
│   ├── core.py         # Text2SQLAgent - SQL 生成与执行
│   ├── unified_core.py # UnifiedAgent - 统一入口（Function Calling）
│   ├── tools.py        # 工具定义注册表（OpenAI Function Calling 格式）
│   ├── prompts.py      # Prompt 模板
│   └── history.py      # 对话历史
├── rag/                # RAG 模块
│   ├── pipeline.py     # RAGPipeline - 主流程编排
│   ├── ingestion/      # 数据摄入
│   ├── retrieval/      # 检索模块
│   ├── storage/        # 向量存储（Milvus）
│   └── embeddings/     # Embedding 客户端
├── api/server.py       # FastAPI Web 服务
└── cli/main.py         # Click CLI 接口
```

### Agent 循环流程（UnifiedAgent）

```
用户问题 → LLM 判断是否需要工具
         → 需要工具：执行工具 → 结果加入上下文 → 返回 LLM（循环）
         → 不需要工具：返回最终回答
```

关键实现细节：
- `_parse_tool_calls_from_text()` 解析文本中的 JSON 工具调用（支持 ``json 块和裸 JSON）
- 工具定义在 `agent/tools.py` 的 `TOOLS` 列表中集中管理
- 工具执行在 `unified_core.py` 的 `_execute_tool()` 方法中分发

### 可用工具

| 类别 | 工具 | 说明 |
|------|------|------|
| SQL | `execute_sql` / `get_schema` / `switch_database` / `list_databases` | 数据库操作 |
| RAG | `rag_query` | 文档问答 |
| 计算 | `calculate` | 数学计算（四则运算、百分比） |
| 文件 | `read_file` / `write_file` / `edit_file` | 文件操作 |

### 测试数据库

`test_database/` 包含 200+ 个 SQLite 测试数据库：
```
test_database/{db_name}/
├── {db_name}.sqlite   # SQLite 数据库文件
└── schema.sql         # Schema 定义
```

## 扩展开发

### 添加新工具

1. 在 `src/agent/tools.py` 的 `TOOLS` 列表中添加工具定义（OpenAI Function Calling 格式）
2. 在 `src/agent/unified_core.py` 的 `_execute_tool()` 方法中添加 case 分发
3. 实际执行逻辑可在 `src/mcp_server/` 下新建或使用现有工具类

### 添加新的 RAG 组件

RAG Pipeline 采用模块化设计，各组件在 `rag/` 子目录中独立扩展，需在 `pipeline.py` 中集成。

## 配置

`.env` 文件关键配置：
- `OPENAI_API_BASE` / `OPENAI_API_KEY` / `DEFAULT_MODEL` - LLM 配置
- `DATABASE_DIR` / `DEFAULT_DATABASE` - 数据库配置
- `MILVUS_HOST` / `MILVUS_PORT` - Milvus 向量数据库
- `EMBEDDING_PROVIDER` / `EMBEDDING_API_KEY` / `EMBEDDING_MODEL` - Embedding 配置
- `LOG_LEVEL` / `LOG_FILE` - 日志配置
- `SQL_ALLOW_WRITE` / `SQL_MAX_ROWS` / `SQL_TIMEOUT_SECONDS` - SQL 安全配置

## SQL 安全机制

`src/mcp_server/sql_security.py` 实现 SQL 安全验证：

**默认只读模式**（`SQL_ALLOW_WRITE=false`）：
- 只允许 SELECT 语句
- 禁止 INSERT/UPDATE/DELETE/DROP/ALTER 等写操作

**防注入保护**：
- 禁止多条语句执行（`SELECT * FROM t; DROP TABLE t;`）
- 禁止 SQL 注释（`--` 和 `/* */`）
- 禁止访问系统表（`sqlite_master`）
- 结果行数限制（默认 1000 行）
- 执行超时限制（默认 30 秒）

## 依赖

- `mcp` - Model Context Protocol SDK
- `openai` - OpenAI 兼容 API 客户端
- `pymilvus` - Milvus 向量数据库
- `pymupdf` - PDF 解析
- `aiosqlite` - 异步 SQLite