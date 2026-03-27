# Text-to-SQL Agent

基于 MCP 架构的 Text-to-SQL 智能助手，支持自然语言转 SQL 查询。

## 功能特性

- 🤖 支持本地 LLM（Ollama、vLLM 等 OpenAI 兼容 API）
- 🔧 MCP Server 提供标准化的 SQL 执行工具
- 💬 支持对话历史、多数据库切换
- 🔁 SQL 错误自动修复
- 📊 CLI 和 Web API 两种交互方式

## 安装

```bash
pip install -e .
```

## 配置

编辑 `.env` 文件：

```env
# LLM API 配置 (OpenAI 兼容)
OPENAI_API_BASE=http://localhost:11434/v1
OPENAI_API_KEY=ollama
DEFAULT_MODEL=qwen2.5

# MCP Server 配置
MCP_SERVER_HOST=localhost
MCP_SERVER_PORT=8765

# 数据库配置
DATABASE_DIR=./test_database
DEFAULT_DATABASE=bakery_1
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

在 `text2sql chat` 模式下（命令支持带或不带 `:` 前缀）：

| 命令 | 说明 |
|------|------|
| `help` | 显示帮助信息 |
| `quit` | 退出程序 |
| `dbs` | 列出所有数据库 |
| `use <db>` | 切换数据库 |
| `schema` | 显示当前数据库结构 |
| `clear` | 清空对话历史 |

### Web API

启动服务：

```bash
# 方式 1: 直接运行
python -m src.api.server

# 方式 2: 使用 uvicorn
uvicorn src.api.server:app --host 0.0.0.0 --port 8000
```

API 端点：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/chat` | POST | 自然语言查询 |
| `/databases` | GET | 列出数据库 |
| `/database/switch` | POST | 切换数据库 |
| `/schema` | GET | 获取 Schema |
| `/sql/execute` | POST | 执行 SQL |

示例：

```bash
# 自然语言查询
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "找出所有巧克力口味的商品", "database": "bakery_1"}'

# 执行 SQL
curl -X POST http://localhost:8000/sql/execute \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM goods WHERE Flavor = \"Chocolate\"", "database": "bakery_1"}'
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

## 项目结构

```
text2sql_agent/
├── src/
│   ├── config.py           # 配置管理
│   ├── mcp_server/         # MCP Server 模块
│   │   ├── server.py       # MCP Server 主程序
│   │   └── tools.py        # SQL 执行工具
│   ├── mcp_client/         # MCP Client 模块
│   │   ├── client.py       # MCP Client 实现
│   │   └── session.py      # 会话管理
│   ├── agent/              # Agent 核心模块
│   │   ├── core.py         # Agent 逻辑
│   │   ├── prompts.py      # Prompt 模板
│   │   └── history.py      # 对话历史
│   ├── api/                # Web API
│   │   └── server.py       # FastAPI 服务
│   └── cli/                # CLI 接口
│       └── main.py         # Click 命令
├── test_database/          # 测试数据库 (206个)
├── .env                    # 环境配置
└── pyproject.toml          # 项目定义
```

## 依赖

- `mcp` - Model Context Protocol SDK
- `openai` - OpenAI API 客户端
- `fastapi` - Web 框架
- `click` - CLI 框架
- `rich` - 终端美化
- `aiosqlite` - 异步 SQLite