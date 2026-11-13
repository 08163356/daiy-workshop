"""画像工程化：快照与整理提案模型

分层设计：
- 原始层：日记/问答/分析原文（散落在各业务表，只增不删）
- 画像层：user_profiles（蒸馏后的当前理解，可编辑、可重建）
- 快照层：本文件，整理前自动快照，可回滚
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProfileSnapshot(Base):
    """画像快照：每次大整理前的全量备份"""
    __tablename__ = "profile_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)  # 快照原因
    entry_count: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[list] = mapped_column(JSON, nullable=False)  # 全量条目 [{category,key,value,confidence,...}]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ProfileProposal(Base):
    """画像整理提案（consent-first：AI 出方案，用户确认才执行）"""
    __tablename__ = "profile_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/applied/rejected
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 人类可读的方案摘要
    plan: Mapped[dict] = mapped_column(JSON, nullable=False)  # 可执行计划（行级 id 操作）
    stats: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # 预计前后对比 {before_count, after_count, ...}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
