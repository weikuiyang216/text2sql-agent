"""FastAPI Web Server for Text-to-SQL Agent."""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..config import config
from ..agent.core import Text2SQLAgent
from ..mcp_client.session import session_manager


# 全局 Agent 实例
agent: Optional[Text2SQLAgent] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global agent
    # 启动时初始化
    agent = Text2SQLAgent()
    await agent._get_mcp()  # 预连接
    yield
    # 关闭时清理
    if agent:
        await agent.close()


# 创建 FastAPI 应用
app = FastAPI(
    title="Text-to-SQL Agent",
    description="自然语言转 SQL 查询服务",
    version="0.1.0",
    lifespan=lifespan
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== 请求/响应模型 =====

class ChatRequest(BaseModel):
    """聊天请求"""
    question: str
    session_id: Optional[str] = None
    database: Optional[str] = None
    auto_fix: bool = True
    explain: bool = False


class ChatResponse(BaseModel):
    """聊天响应"""
    sql: str
    result: dict
    explanation: Optional[str] = None
    success: bool
    session_id: str


class SwitchDatabaseRequest(BaseModel):
    """切换数据库请求"""
    db_name: str


class ExecuteSQLRequest(BaseModel):
    """执行 SQL 请求"""
    sql: str
    database: Optional[str] = None


class DatabaseInfo(BaseModel):
    """数据库信息"""
    name: str
    tables: int
    path: str


# ===== API 端点 =====

@app.get("/")
async def root():
    """根端点"""
    return {"message": "Text-to-SQL Agent API", "version": "0.1.0"}


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy", "database": agent.current_db if agent else None}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """处理自然语言问题，返回 SQL 和查询结果"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    try:
        # 切换数据库
        if request.database:
            result = await agent.switch_database(request.database)
            if not result.get("success"):
                raise HTTPException(status_code=400, detail=result.get("error"))

        # 处理问题
        result = await agent.chat(
            request.question,
            auto_fix=request.auto_fix,
            explain=request.explain
        )

        # 获取或创建会话
        session = session_manager.get_or_create_session(request.session_id)

        return ChatResponse(
            sql=result["sql"],
            result=result["result"],
            explanation=result.get("explanation"),
            success=result["success"],
            session_id=session.id
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/databases")
async def list_databases():
    """列出所有可用数据库"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    dbs = await agent.list_databases()
    return {"databases": dbs, "count": len(dbs)}


@app.post("/database/switch")
async def switch_database(request: SwitchDatabaseRequest):
    """切换当前数据库"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    result = await agent.switch_database(request.db_name)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return {"success": True, "current_database": request.db_name}


@app.get("/database/current")
async def get_current_database():
    """获取当前数据库"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    return {
        "database": agent.current_db,
        "schema": await agent.get_schema_text()
    }


@app.post("/sql/execute")
async def execute_sql(request: ExecuteSQLRequest):
    """直接执行 SQL"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    try:
        # 切换数据库
        if request.database:
            await agent.switch_database(request.database)

        result = await agent.execute_sql(request.sql)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/schema")
async def get_schema(database: Optional[str] = None):
    """获取数据库 Schema"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    if database:
        await agent.switch_database(database)

    return {"schema": await agent.get_schema_text()}


@app.get("/history")
async def get_history(session_id: Optional[str] = None):
    """获取对话历史"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    return {"history": agent.history.to_dict()}


@app.delete("/history")
async def clear_history():
    """清空对话历史"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent 未初始化")

    agent.history.clear()
    return {"success": True, "message": "历史已清空"}


# ===== 启动配置 =====

def run_server():
    """启动服务器"""
    import uvicorn
    uvicorn.run(
        "src.api.server:app",
        host=config.MCP_SERVER_HOST,
        port=config.MCP_SERVER_PORT,
        reload=True
    )


if __name__ == "__main__":
    run_server()