"""模块级 AI 模型配置数据模型"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ModuleModelConfig(Base):
    """模块模型配置表 - 每个模块可独立绑定不同的 AI 模型"""

    __tablename__ = "module_model_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module_name: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )  # 模块名: diary / todo / reading / investment / kb / note 等
    ai_config_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ai_configs.id", ondelete="CASCADE"),
        nullable=False,
    )  # 关联的 AI 配置 ID
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    def __repr__(self) -> str:
        return f"<ModuleModelConfig(module='{self.module_name}', ai_config_id={self.ai_config_id})>"
