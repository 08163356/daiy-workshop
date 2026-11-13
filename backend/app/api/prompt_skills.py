"""Prompt Skill 管理 API（页面可新建/编辑/启停/恢复默认；候选审核）"""

import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.prompt_skill import PromptSkill, SkillCandidate
from app.services import skill_service
from app.services.skill_service import BUILTIN_SKILLS

router = APIRouter(prefix="/prompt-skills", tags=["Prompt Skill 管理"])

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SkillUpsert(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    title: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=300)
    content: str = Field(..., min_length=1)
    when_to_use: Optional[str] = None
    user_invocable: bool = True
    model_invocable: bool = True
    is_persona: bool = False


class SkillUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    when_to_use: Optional[str] = None
    user_invocable: Optional[bool] = None
    model_invocable: Optional[bool] = None


def _to_dict(s: PromptSkill) -> dict:
    return {
        "id": s.id, "name": s.name, "title": s.title, "description": s.description,
        "content": s.content, "when_to_use": s.when_to_use,
        "user_invocable": s.user_invocable, "model_invocable": s.model_invocable,
        "bind_pipeline": s.bind_pipeline, "is_persona": s.is_persona,
        "is_builtin": s.is_builtin, "enabled": s.enabled,
        "revision": s.revision, "use_count": s.use_count,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.get("")
async def list_skills(include_disabled: bool = True, db: AsyncSession = Depends(get_db)):
    query = select(PromptSkill).order_by(PromptSkill.is_persona, PromptSkill.id)
    if not include_disabled:
        query = query.where(PromptSkill.enabled == True)  # noqa: E712
    result = await db.execute(query)
    return {"items": [_to_dict(s) for s in result.scalars()]}


@router.post("")
async def create_skill(data: SkillUpsert, db: AsyncSession = Depends(get_db)):
    if not NAME_RE.match(data.name):
        raise HTTPException(400, "name 必须是 kebab-case（小写字母/数字/中划线）")
    if await skill_service.get_skill(db, data.name):
        raise HTTPException(400, "同名 skill 已存在")
    skill = PromptSkill(**data.model_dump(), is_builtin=False)
    db.add(skill)
    await db.flush()
    await db.commit()
    return _to_dict(skill)


@router.get("/candidates")
async def list_candidates(status: str = "pending", db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SkillCandidate).where(SkillCandidate.status == status).order_by(SkillCandidate.created_at.desc())
    )
    return {"items": [
        {
            "id": c.id, "name": c.name, "title": c.title, "description": c.description,
            "content": c.content, "reason": c.reason, "action": c.action,
            "target_name": c.target_name, "source_session_id": c.source_session_id,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in result.scalars()
    ]}


@router.post("/candidates/{candidate_id}/approve")
async def approve_candidate(candidate_id: int, db: AsyncSession = Depends(get_db)):
    try:
        skill = await skill_service.approve_candidate(db, candidate_id)
        await db.commit()
        return {"message": "已转正", "skill": _to_dict(skill)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/candidates/{candidate_id}/reject")
async def reject_candidate(candidate_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await skill_service.reject_candidate(db, candidate_id)
        await db.commit()
        return {"message": "已拒绝"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{name}")
async def get_skill(name: str, db: AsyncSession = Depends(get_db)):
    skill = await skill_service.get_skill(db, name)
    if not skill:
        raise HTTPException(404, "skill 不存在")
    return _to_dict(skill)


@router.put("/{name}")
async def update_skill(name: str, data: SkillUpdate, db: AsyncSession = Depends(get_db)):
    skill = await skill_service.get_skill(db, name)
    if not skill:
        raise HTTPException(404, "skill 不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(skill, field, value)
    skill.revision += 1
    skill.updated_at = datetime.now()
    await db.flush()
    await db.commit()
    return _to_dict(skill)


@router.post("/{name}/toggle")
async def toggle_skill(name: str, db: AsyncSession = Depends(get_db)):
    skill = await skill_service.get_skill(db, name)
    if not skill:
        raise HTTPException(404, "skill 不存在")
    skill.enabled = not skill.enabled
    await db.flush()
    await db.commit()
    return {"name": name, "enabled": skill.enabled}


@router.post("/{name}/reset")
async def reset_skill(name: str, db: AsyncSession = Depends(get_db)):
    """内置 skill 恢复默认内容"""
    skill = await skill_service.get_skill(db, name)
    if not skill or not skill.is_builtin:
        raise HTTPException(400, "只有内置 skill 可以恢复默认")
    spec = next((s for s in BUILTIN_SKILLS if s["name"] == name), None)
    if not spec:
        raise HTTPException(400, "内置定义不存在")
    skill.content = spec["content"]
    skill.description = spec["description"]
    skill.title = spec["title"]
    skill.revision += 1
    skill.enabled = True
    await db.flush()
    await db.commit()
    return _to_dict(skill)


@router.delete("/{name}")
async def delete_skill(name: str, db: AsyncSession = Depends(get_db)):
    """仅自定义 skill 可删；内置的只能禁用（防误删默认模板）"""
    skill = await skill_service.get_skill(db, name)
    if not skill:
        raise HTTPException(404, "skill 不存在")
    if skill.is_builtin:
        raise HTTPException(400, "内置 skill 不能删除，可以禁用")
    await db.delete(skill)
    await db.flush()
    await db.commit()
    return {"message": "已删除"}
