"""FastAPI 应用入口"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db, close_db
from app.api import api_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    logger.info("初始化数据库...")
    await init_db()
    logger.info(f"读书目录: {settings.markdown_dir}")
    logger.info(f"投资目录: {settings.investment_dir}")

    # 定时任务调度（每日 21:00 日报，wake gate）
    import asyncio as _asyncio
    from app.services.scheduler import scheduler_loop
    _scheduler_task = _asyncio.create_task(scheduler_loop())

    yield

    # 关闭时清理资源
    _scheduler_task.cancel()
    logger.info("关闭数据库连接...")
    await close_db()


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Daily 系统后端 API - 读书 + 投资 + 日记 + AI 对话",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api_router)


@app.get("/", tags=["健康检查"])
async def root():
    """根路径 - 健康检查"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "modules": ["reading", "investment", "diary", "chat"],
    }


@app.get("/health", tags=["健康检查"])
async def health_check():
    """健康检查端点"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8088,
        reload=True,
    )
