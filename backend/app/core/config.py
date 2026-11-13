"""配置管理模块"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


def get_default_markdown_dir() -> Path:
    """默认把用户内容放在仓库外可挂载的数据目录中。"""
    return Path("./user-data/reading")


def get_default_investment_dir() -> Path:
    return Path("./user-data/investment")


class Settings(BaseSettings):
    """应用配置"""

    # 应用配置
    app_name: str = "Daily 系统"
    app_version: str = "2.0.0"
    debug: bool = False
    initial_admin_password: Optional[str] = None

    # 读书 MD 文件路径 (支持环境变量覆盖)
    markdown_dir: Path = get_default_markdown_dir()
    
    # 投资 MD 文件路径 (支持环境变量覆盖)
    investment_dir: Path = get_default_investment_dir()

    # 数据库配置（统一数据库）
    database_url: str = "sqlite+aiosqlite:///./reading_system.db"

    # CORS 配置
    cors_origins: list[str] = ["http://localhost:5173"]

    # 同步配置
    sync_batch_size: int = 50

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
