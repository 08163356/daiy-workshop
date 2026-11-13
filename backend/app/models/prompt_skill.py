"""Prompt Skill 模型 —— 自进化技能体系（参考 hermes-agent / deepseek-harness）

技能 = 程序性记忆：报告模板、教练人格、分析模板等都存这里，
页面可编辑、对话中可引用（用户 / 显式调用 + AI use_skill 按需加载 + 管线绑定）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PromptSkill(Base):
    """Prompt 技能表"""

    __tablename__ = "prompt_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)  # kebab-case 唯一键
    title: Mapped[str] = mapped_column(String(100), nullable=False)  # 显示名
    description: Mapped[str] = mapped_column(String(300), nullable=False)  # 路由信号：前 57 字符要自包含
    content: Mapped[str] = mapped_column(Text, nullable=False)  # prompt 正文，支持 {user_profile}/{today} 等占位
    when_to_use: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)  # 补充触发提示

    # 调用策略（harness SkillInvocationPolicy 裁剪）
    user_invocable: Mapped[bool] = mapped_column(Boolean, default=True)   # / 命令面板可见
    model_invocable: Mapped[bool] = mapped_column(Boolean, default=True)  # AI 可 use_skill 自动加载
    bind_pipeline: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)  # 绑编排管线 report_daily 等
    is_persona: Mapped[bool] = mapped_column(Boolean, default=False)  # SOUL 人格（会话级注入 stable 段）

    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)  # 内置（可恢复默认）
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 改进有效性度量（hermes patch_generation 思想）：每次修改 +1，AI 使用命中更新 last_used_revision
    revision: Mapped[int] = mapped_column(Integer, default=1)
    last_used_revision: Mapped[int] = mapped_column(Integer, default=0)
    use_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<PromptSkill(name='{self.name}', title='{self.title}')>"


class SkillCandidate(Base):
    """自进化候选技能：复盘代理产出，用户确认（consent-first）后才转正"""

    __tablename__ = "skill_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 推荐理由（哪次对话的什么经验）
    source_session_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(20), default="create")  # create / patch（改进 target_name）
    target_name: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending/approved/rejected
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<SkillCandidate(name='{self.name}', status='{self.status}')>"
