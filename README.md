# Text-to-SQL Agent

基于 MCP 架构的智能助手，支持自然语言转 SQL 查询和文档 RAG 问答。

## 功能特性

### Text-to-SQL
- 🤖 支持本地 LLM（Ollama、vLLM 等 OpenAI 兼容 API）
- 🔧 MCP Server 提供标准化的 SQL 执行工具
- 💬 支持对话历史、多数据库切换
- 🔁 SQL 错误自动修复

### Agentic RAG
- 📄 PDF 文档智能解析（章节/条款/表格）
- 🔍 多路检索（查询重写 + 向量检索 + 重排序）
- 📝 引用溯源（答案来源可追溯）
- 🎯 自动路由（SQL/RAG 混合查询）

### 接口支持
- 📊 CLI 和 Web API 两种交互方式

### 通用工具
- 🔢 计算器工具：支持四则运算和百分比计算
- 📄 文档工具：支持文件读取、写入、追加和编辑操作

## 安装

```bash
pip install -e .
```

## 配置

编辑 `.env` 文件：

```env
# LLM API 配置 (OpenAI 兼容)
OPENAI_API_BASE=http://localhost:8000/v1
OPENAI_API_KEY=your-api-key
DEFAULT_MODEL=qwen2.5-coder-7b

# MCP Server 配置
MCP_SERVER_HOST=localhost
MCP_SERVER_PORT=8765

# 数据库配置
DATABASE_DIR=./test_database
DEFAULT_DATABASE=bakery_1

# Milvus 配置
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION_PREFIX=boc_contracts

# Embedding 配置 (支持 DashScope/OpenAI)
EMBEDDING_PROVIDER=dashscope
EMBEDDING_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=your-dashscope-api-key
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIM=1024

# RAG 配置
RAG_TOP_K=10
RAG_RERANK_TOP_K=5
DOCUMENT_DIR=./data
```

## 快速开始

### 1. 启动 Milvus（RAG 功能需要）

```bash
docker-compose up -d
```

### 2. 摄入文档

```bash
# 摄入所有 PDF 文档
python scripts/ingest_documents.py

# 重置集合并重新摄入
python scripts/ingest_documents.py --reset

# 摄入单个文件
python scripts/ingest_documents.py --file data/合同.pdf
```

### 3. 启动服务

```bash
# 启动 API 服务
python -m src.api.server

# 或使用 uvicorn
uvicorn src.api.server:app --host 0.0.0.0 --port 8765
```

## 使用方式

### CLI 命令

```bash
# 启动交互式对话
text2sql chat --db bakery_1

# 列出所有可用数据库
text2sql list-db

# 显示数据库结构
text2sql schema --db bakery_1

# 直接执行 SQL
text2sql exec "SELECT * FROM goods LIMIT 5" --db bakery_1
```

### 交互式对话命令

在 `text2sql chat` 模式下：

| 命令 | 说明 |
|------|------|
| `help` | 显示帮助信息 |
| `quit` | 退出程序 |
| `dbs` | 列出所有数据库 |
| `use <db>` | 切换数据库 |
| `schema` | 显示当前数据库结构 |
| `clear` | 清空对话历史 |

### Web API

#### Text-to-SQL 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/chat` | POST | 自然语言转 SQL 查询 |
| `/databases` | GET | 列出数据库 |
| `/database/switch` | POST | 切换数据库 |
| `/schema` | GET | 获取 Schema |
| `/sql/execute` | POST | 执行 SQL |

#### RAG 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/rag/chat` | POST | RAG 文档问答 |
| `/rag/ingest` | POST | 摄入文档 |
| `/rag/stats` | GET | 获取 RAG 统计 |
| `/unified/chat` | POST | 统一问答（自动路由） |

#### API 示例

```bash
# 自然语言 SQL 查询
curl -X POST http://localhost:8765/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "找出所有价格低于5元的商品", "database": "bakery_1"}'

# RAG 文档问答
curl -X POST http://localhost:8765/rag/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "住房贷款合同中关于提前还款的规定是什么？"}'

# 统一问答（自动路由 SQL/RAG）
curl -X POST http://localhost:8765/unified/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "个人住房贷款的利率是多少？"}'

# 摄入文档
curl -X POST http://localhost:8765/rag/ingest \
  -H "Content-Type: application/json" \
  -d '{"reset": false}'
```

### MCP Server

作为 MCP Server 使用：

```bash
python -m src.mcp_server.server
```

MCP Tools:

| Tool | 说明 |
|------|------|
| `list_databases` | 列出所有数据库 |
| `switch_database` | 切换数据库 |
| `get_schema` | 获取 Schema |
| `get_schema_text` | 获取 Schema 文本描述 |
| `execute_sql` | 执行 SQL |
| `explain_schema` | 解释表结构 |
| `calculate` | 执行数学计算（四则运算、百分比） |
| `read_file` | 读取文件内容 |
| `write_file` | 写入或追加文件 |
| `edit_file` | 编辑文件（替换文本） |

## 项目结构

```
text2sql_agent/
├── src/
│   ├── config.py               # 配置管理
│   ├── mcp_server/             # MCP Server 模块
│   │   ├── server.py           # MCP Server 主程序
│   │   ├── tools.py            # SQL 执行工具
│   │   ├── calculator_tools.py # 计算器工具
│   │   └── document_tools.py   # 文档操作工具
│   ├── mcp_client/             # MCP Client 模块
│   │   ├── client.py           # MCP Client 实现
│   │   └── session.py          # 会话管理
│   ├── agent/                  # Agent 核心模块
│   │   ├── core.py             # Text2SQL Agent
│   │   ├── unified_core.py     # 统一 Agent (SQL + RAG)
│   │   ├── prompts.py          # Prompt 模板
│   │   └── history.py          # 对话历史
│   ├── rag/                    # RAG 模块
│   │   ├── pipeline.py         # RAG Pipeline 主流程
│   │   ├── ingestion/          # 数据摄入
│   │   │   ├── pdf_parser.py   # PDF 解析器
│   │   │   └── chunker.py      # 文档分块器
│   │   ├── storage/            # 向量存储
│   │   │   ├── milvus_client.py # Milvus 客户端
│   │   │   └── schema.py       # 集合 Schema
│   │   ├── retrieval/          # 检索模块
│   │   │   ├── query_rewriter.py  # 查询重写
│   │   │   ├── multi_retriever.py # 多路检索
│   │   │   ├── reranker.py     # 重排序
│   │   │   └── citation.py     # 引用溯源
│   │   └── embeddings/         # Embedding 模块
│   │       └── embedding_client.py
│   ├── api/                    # Web API
│   │   └── server.py           # FastAPI 服务
│   └── cli/                    # CLI 接口
│       └── main.py             # Click 命令
├── scripts/                    # 脚本
│   └── ingest_documents.py     # 文档摄入脚本
├── data/                       # PDF 文档目录
├── test_database/              # 测试数据库 (206个)
├── docker-compose.yml          # Milvus 部署配置
├── .env                        # 环境配置
└── pyproject.toml              # 项目定义
```

## RAG 架构

```
用户查询
    │
    ▼
┌─────────────────┐
│  Query Router   │  ← 意图分类 (SQL/RAG/HYBRID)
└─────────────────┘
    │
    ├─── SQL → Text2SQL Agent
    │
    └─── RAG → RAG Pipeline
              │
              ▼
        ┌─────────────────┐
        │ Query Rewriter  │  ← 查询扩展/澄清/分解
        └─────────────────┘
              │
              ▼
        ┌─────────────────┐
        │ Multi-path      │  ← 密集向量检索
        │ Retriever       │     + 元数据过滤
        └─────────────────┘
              │
              ▼
        ┌─────────────────┐
        │ Reranker        │  ← Cross-Encoder
        └─────────────────┘     + 多样性重排
              │
              ▼
        ┌─────────────────┐
        │ Citation        │  ← 引用溯源
        │ Tracker         │
        └─────────────────┘
              │
              ▼
          生成的答案
```

## 依赖

### 核心依赖
- `mcp` - Model Context Protocol SDK
- `openai` - OpenAI API 客户端
- `fastapi` - Web 框架
- `click` - CLI 框架
- `rich` - 终端美化
- `aiosqlite` - 异步 SQLite
- `aiofiles` - 异步文件操作

### RAG 依赖
- `pymilvus` - Milvus 向量数据库
- `pymupdf` - PDF 解析
- `tiktoken` - Token 计数
- `tqdm` - 进度条

## License

MIT