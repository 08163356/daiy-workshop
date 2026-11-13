"""审批待办模型 — 用于 AI 自动化产出（简历/博客/GBrain/部署）的人工审批"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON

from app.core.database import Base


class ReviewItem(Base):
    """待审批条目

    AI 或自动化脚本生成候选内容后，写入此表等待用户审批。
    用户在 daily 系统的「审批中心」页面审核，同意后调用 sync_command 完成同步。
    所有数据存于 reading_system.db，可通过 /api/review/export 导出 JSON 迁移。
    """
    __tablename__ = "review_items"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 类型：resume(简历) | blog(博客) | gbrain(知识库) | deploy(部署) | general(通用)
    type = Column(String(32), nullable=False, index=True)

    title = Column(String(256), nullable=False)
    summary = Column(Text, default="")          # 摘要：变更了什么、为什么需要审批
    content = Column(Text, default="")          # 正文：diff、完整 markdown 或 JSON

    # pending | approved | rejected | expired
    status = Column(String(16), default="pending", index=True)

    # 来源标识：codebuddy | cursor | automation | manual
    source = Column(String(64), default="manual")

    # 附加信息（文件路径、目标 URL、构建产物路径等）
    metadata_json = Column(JSON, default=dict)

    # 审批通过后要执行的命令/脚本/API
    sync_command = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    reviewer_note = Column(Text, default="")     # 审批时的批注

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "summary": self.summary,
            "content": self.content,
            "status": self.status,
            "source": self.source,
            "metadata": self.metadata_json or {},
            "syncCommand": self.sync_command,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
            "reviewedAt": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewerNote": self.reviewer_note,
        }
