# Text-to-SQL Agent

基于 MCP 架构的智能助手，通过 Function Calling 实现统一的自然语言交互入口。

## 功能特性

### 统一入口
- 🎯 **一个入口，多种能力**：`/unified/chat` 自动路由 SQL/RAG/计算器/文件操作
- 🤖 **Function Calling**：LLM 自动判断并调用所需工具
- 🔄 **多轮交互**：支持 Agent 循环模式，复杂任务自动分解

### 核心能力
- **Text-to-SQL**: 自然语言转 SQL，支持多数据库切换和错误自动修复
- **Agentic RAG**: PDF 文档问答，支持向量检索和引用溯源
- **计算器**: 四则运算、百分比计算
- **文件操作**: 读取、写入、编辑文件

### 接口支持
- 📊 CLI 和 Web API 两种交互方式

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

# 数据库配置
DATABASE_DIR=./test_database
DEFAULT_DATABASE=bakery_1

# Milvus 配置（RAG 功能）
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION_PREFIX=boc_contracts

# Embedding 配置
EMBEDDING_PROVIDER=dashscope
EMBEDDING_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=your-dashscope-api-key
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIM=1024

# RAG 配置
RAG_TOP_K=10
RAG_RERANK_TOP_K=5
DOCUMENT_DIR=./data

# 日志配置
LOG_LEVEL=INFO          # DEBUG, INFO, WARNING, ERROR
LOG_FILE=               # 可选：日志文件路径，如 logs/app.log
LOG_RICH_OUTPUT=true    # 控制台彩色输出

# SQL 安全配置
SQL_ALLOW_WRITE=false   # 是否允许 INSERT/UPDATE/DELETE（默认只读）
SQL_MAX_ROWS=1000       # 查询结果最大行数
SQL_TIMEOUT_SECONDS=30  # SQL 执行超时时间（秒）

# Query 重写配置
ENABLE_QUERY_REWRITE=true  # 是否启用查询重写（时间转换、问题澄清）
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

# 启动详细日志模式（调试）
text2sql chat --db bakery_1 -v

# 列出所有可用数据库
text2sql list-db

# 显示数据库结构
text2sql schema --db bakery_1

# 直接执行 SQL
text2sql exec "SELECT * FROM goods LIMIT 5" --db bakery_1
```

### Web API

#### 统一入口

所有请求都通过 `/unified/chat` 发送，LLM 自动判断需要调用哪些工具：

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

#### API 示例

```bash
# SQL 查询 - 自动调用 execute_sql
curl -X POST http://localhost:8765/unified/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "找出所有价格低于5元的商品"}'

# RAG 问答 - 自动调用 rag_query
curl -X POST http://localhost:8765/unified/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "住房贷款合同中关于提前还款的规定是什么？"}'

# 数学计算 - 自动调用 calculate
curl -X POST http://localhost:8765/unified/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "帮我计算 100 * 20% + 50"}'

# 文件操作 - 自动调用 read_file/write_file
curl -X POST http://localhost:8765/unified/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "读取 /tmp/test.txt 文件内容"}'

# 混合操作 - 自动调用多个工具
curl -X POST http://localhost:8765/unified/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "查询商品总数并写入文件 /tmp/count.txt"}'
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
| `rag_query` | RAG 文档问答 |
| `calculate` | 数学计算（四则运算、百分比） |
| `read_file` | 读取文件内容 |
| `write_file` | 写入或追加文件 |
| `edit_file` | 编辑文件（替换文本） |

## 项目结构

```
text2sql_agent/
├── src/
│   ├── config.py               # 配置管理
│   ├── logging_config.py       # 日志配置（Rich 彩色输出）
│   ├── mcp_server/             # MCP Server 模块
│   │   ├── server.py           # MCP Server 主程序
│   │   ├── tools.py            # SQL 执行工具
│   │   ├── sql_security.py     # SQL 安全验证（防注入）
│   │   ├── calculator_tools.py # 计算器工具
│   │   └── document_tools.py   # 文档操作工具
│   ├── mcp_client/             # MCP Client 模块
│   ├── agent/                  # Agent 核心模块
│   │   ├── core.py             # Text2SQL Agent
│   │   ├── query_rewriter.py   # 查询重写（时间转换、问题澄清）
│   │   ├── unified_core.py     # 统一 Agent (Function Calling)
│   │   ├── tools.py            # 工具定义注册表
│   │   ├── prompts.py          # Prompt 模板
│   │   └── history.py          # 对话历史
│   ├── rag/                    # RAG 模块
│   │   ├── pipeline.py         # RAG Pipeline 主流程
│   │   ├── ingestion/          # 数据摄入
│   │   ├── storage/            # 向量存储
│   │   ├── retrieval/          # 检索模块
│   │   └── embeddings/         # Embedding 模块
│   ├── api/                    # Web API
│   │   └── server.py           # FastAPI 服务
│   └── cli/                    # CLI 接口
│       └── main.py             # Click 命令
├── scripts/                    # 脚本
├── data/                       # PDF 文档目录
├── test_database/              # 测试数据库
├── docker-compose.yml          # Milvus 部署配置
├── .env                        # 环境配置
└── pyproject.toml              # 项目定义
```

## 架构

### Agent 循环流程

```
用户问题
    │
    ▼
┌─────────────────────────────┐
│         LLM + 工具定义        │
│  判断是否需要调用工具          │
└─────────────┬───────────────┘
              │
    ┌─────────┴─────────┐
    │                   │
    ▼                   ▼
需要工具？            不需要
    │                   │
    ▼                   ▼
执行工具              返回回答
    │
    ▼
结果加入上下文
    │
    └──→ 返回 LLM（循环）
```

### 可用工具

| 类别 | 工具 | 说明 |
|------|------|------|
| SQL | `execute_sql` | 执行 SQL 查询 |
| SQL | `get_schema` | 获取数据库结构 |
| SQL | `switch_database` | 切换数据库 |
| SQL | `list_databases` | 列出所有数据库 |
| RAG | `rag_query` | 文档问答 |
| 计算 | `calculate` | 数学计算 |
| 文件 | `read_file` | 读取文件 |
| 文件 | `write_file` | 写入文件 |
| 文件 | `edit_file` | 编辑文件 |

## 安全机制

### SQL 安全

`src/mcp_server/sql_security.py` 提供多层安全保护：

| 保护措施 | 说明 | 默认值 |
|----------|------|--------|
| 语句类型限制 | 默认只允许 SELECT，禁止 INSERT/UPDATE/DELETE | 只读 |
| 危险操作阻止 | 禁止 DROP/ALTER/CREATE/TRUNCATE/GRANT | 启用 |
| 多语句阻止 | 防止 `SELECT * FROM t; DROP TABLE t;` 注入 | 启用 |
| 注释过滤 | 阻止 `--` 和 `/* */` 注释注入 | 启用 |
| 系统表保护 | 禁止访问 `sqlite_master` 等系统表 | 启用 |
| 结果行数限制 | 防止大量数据泄露 | 1000 行 |
| 执行超时 | 防止长时间运行的查询 | 30 秒 |

**配置选项**：

```env
SQL_ALLOW_WRITE=false    # 是否允许写操作（INSERT/UPDATE/DELETE）
SQL_MAX_ROWS=1000        # 查询结果最大行数
SQL_TIMEOUT_SECONDS=30   # SQL 执行超时时间（秒）
```

**示例**：

```python
from src.mcp_server.tools import SQLExecutorTools

# 默认只读模式
tools = SQLExecutorTools()
await tools.execute_sql("SELECT * FROM goods")  # ✓ 允许
await tools.execute_sql("DELETE FROM goods")    # ✗ 拒绝

# 允许写操作
tools = SQLExecutorTools(allow_write=True)
await tools.execute_sql("INSERT INTO goods VALUES (...)")  # ✓ 允许
```

## 查询重写

`src/agent/query_rewriter.py` 提供智能查询重写功能，优化用户输入以提高 SQL 生成质量。

### 支持的时间表达式

| 表达式类型 | 示例 | 转换结果 |
|------------|------|----------|
| 相对时间 | 今天、昨天、前天 | 具体日期 |
| 时间偏移 | 最近7天、过去一个月 | 日期范围 |
| 周期时间 | 本周、上周、本月 | 周期起止日期 |
| 年度时间 | 今年、去年、明年 | 年度起止日期 |
| 季度时间 | 2024年第一季度、Q2 | 季度日期范围 |
| 具体日期 | 2024年1月15日 | 标准日期格式 |

**示例**：

```python
from src.agent.query_rewriter import parse_time_expressions

# 解析时间表达式
results = parse_time_expressions("最近7天的订单")
# [{'original': '最近7天', 'sql_value': {'start': "'2026-03-25'", 'end': "'2026-04-01'"}}]

results = parse_time_expressions("2024年第一季度的销售数据")
# [{'original': '2024年第一季度', 'sql_value': {'start': "'2024-01-01'", 'end': "'2024-03-31'"}}]
```

### 问题澄清

当用户问题包含模糊指代时，系统会尝试澄清：

```python
# 对话历史：
# Q: 查询电子产品的销售额
# A: 电子产品的销售额为 100 万

# 用户追问：
# Q: 它的利润是多少？

# 澄清后：
# Q: 电子产品的利润是多少？
```

### 配置

```env
ENABLE_QUERY_REWRITE=true  # 启用/禁用查询重写功能
```

## 依赖

### 核心依赖
- `mcp` - Model Context Protocol SDK
- `openai` - OpenAI API 客户端
- `fastapi` - Web 框架
- `click` - CLI 框架
- `rich` - 终端美化、日志彩色输出
- `aiosqlite` - 异步 SQLite
- `aiofiles` - 异步文件操作

### RAG 依赖
- `pymilvus` - Milvus 向量数据库
- `pymupdf` - PDF 解析
- `tiktoken` - Token 计数
- `tqdm` - 进度条

## 调试

### 日志配置

项目使用 Rich 库提供彩色日志输出：

```env
LOG_LEVEL=INFO          # 日志级别：DEBUG, INFO, WARNING, ERROR
LOG_FILE=               # 可选：日志文件路径，如 logs/app.log
LOG_RICH_OUTPUT=true    # 控制台彩色输出
```

### CLI 调试模式

```bash
# 启动交互式对话（详细日志）
text2sql chat --db bakery_1 -v
```

### 日志输出示例

```
[03/31/26 14:10:47] INFO     Logging initialized: level=DEBUG
                    INFO     SQL executor initialized: write_mode=False
                    DEBUG    Processing question: 查询所有商品
                    DEBUG    SQL generated: SELECT * FROM goods
                    INFO     SQL executed successfully: 15 rows
```

## License

MIT