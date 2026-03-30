# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Text-to-SQL Agent 是基于 MCP (Model Context Protocol) 架构的智能助手，支持：
- **Text-to-SQL**: 自然语言转 SQL 查询，支持多数据库切换和 SQL 错误自动修复
- **Agentic RAG**: PDF 文档智能问答，支持向量检索和引用溯源
- **统一接口**: 自动路由 SQL/RAG 查询的混合查询

## 常用命令

### 安装与配置
```bash
pip install -e .
```

配置文件 `.env` 需要设置：
- `OPENAI_API_BASE` / `OPENAI_API_KEY` / `DEFAULT_MODEL` - LLM 配置
- `DATABASE_DIR` / `DEFAULT_DATABASE` - 数据库配置
- `MILVUS_HOST` / `MILVUS_PORT` - Milvus 向量数据库（RAG 功能）

### 启动服务

```bash
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
# 交互式对话
text2sql chat --db bakery_1

# 列出数据库
text2sql list-db

# 显示 Schema
text2sql schema --db bakery_1

# 执行 SQL
text2sql exec "SELECT * FROM goods LIMIT 5" --db bakery_1
```

### 文档摄入（RAG）

```bash
# 摄入所有 PDF
python scripts/ingest_documents.py

# 重置集合并重新摄入
python scripts/ingest_documents.py --reset

# 摄入单个文件
python scripts/ingest_documents.py --file data/合同.pdf
```

## 架构

### 核心模块结构

```
src/
├── config.py           # 配置管理（环境变量加载）
├── mcp_server/         # MCP Server - 提供 SQL 执行工具
│   ├── server.py       # MCP Server 主程序
│   └── tools.py        # SQL 执行工具（SQLExecutorTools）
├── mcp_client/         # MCP Client - 与 MCP Server 通信
│   ├── client.py       # MCP Client 实现
│   └── session.py      # 会话管理
├── agent/              # Agent 核心
│   ├── core.py         # Text2SQLAgent - SQL 生成与执行
│   ├── unified_core.py # UnifiedAgent - SQL + RAG 统一入口
│   ├── prompts.py      # Prompt 模板
│   └── history.py      # 对话历史
├── rag/                # RAG 模块
│   ├── pipeline.py     # RAGPipeline - 主流程编排
│   ├── ingestion/      # 数据摄入（PDF 解析、分块）
│   ├── retrieval/      # 检索模块（查询重写、多路检索、重排序、引用溯源）
│   ├── storage/        # 向量存储（Milvus）
│   └── embeddings/     # Embedding 客户端
├── api/server.py       # FastAPI Web 服务
└── cli/main.py         # Click CLI 接口
```

### 关键架构模式

1. **MCP 架构**: Agent 通过 MCP Client 调用 MCP Server 提供的工具（`list_databases`, `switch_database`, `get_schema`, `execute_sql`）

2. **SQL Agent 流程** (`agent/core.py`):
   - 获取 Schema → 构建 Prompt → LLM 生成 SQL → 执行 SQL → 错误自动修复（最多 3 次）

3. **RAG Pipeline 流程** (`rag/pipeline.py`):
   - PDF 解析 → 文档分块 → Embedding → Milvus 存储
   - 查询重写 → 多路检索 → 重排序 → 生成答案 → 引用溯源

4. **统一 Agent** (`agent/unified_core.py`):
   - `QueryRouter` 分类意图（SQL/RAG/HYBRID/GENERAL）
   - 根据意图路由到对应处理器

5. **懒加载模式**: MCP Client 和 RAG Pipeline 都采用懒加载，首次使用时初始化

### 数据流

```
用户问题 → UnifiedAgent.chat()
         → QueryRouter.classify_intent()
         → SQL: Text2SQLAgent.chat() → MCPClient → SQLExecutorTools
         → RAG: RAGPipeline.query() → Milvus
         → HYBRID: 并行执行两者
```

### 测试数据库

`test_database/` 包含 200+ 个 SQLite 测试数据库，每个数据库目录结构：
```
test_database/{db_name}/
├── {db_name}.sqlite   # SQLite 数据库文件
└── schema.sql         # Schema 定义
```

## API 端点

- `POST /chat` - Text-to-SQL 查询
- `POST /rag/chat` - RAG 文档问答
- `POST /unified/chat` - 统一问答（自动路由）
- `GET /databases` - 列出数据库
- `POST /database/switch` - 切换数据库
- `GET /schema` - 获取 Schema
- `POST /rag/ingest` - 摄入文档

## 依赖说明

- `mcp` - Model Context Protocol SDK
- `openai` - OpenAI 兼容 API 客户端（支持 Ollama/vLLM 等本地 LLM）
- `pymilvus` - Milvus 向量数据库客户端
- `pymupdf` - PDF 解析
- `aiosqlite` - 异步 SQLite 操作