"""Skill 管理 API"""

import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/skills", tags=["技能管理"])


class SkillUpdateRequest(BaseModel):
    content: str


def get_skills_dir() -> Path:
    """获取 skills 目录"""
    return Path(os.environ.get("DAILY_SKILLS_DIR", "./user-data/skills"))


@router.get("", summary="获取所有 Skill 列表")
async def list_skills():
    """列出所有可用的 Skill"""
    skills_dir = get_skills_dir()
    if not skills_dir.exists():
        return []

    skills = []
    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir():
            continue

        skill_md = item / "SKILL.md"
        skill_info = {
            "name": item.name,
            "has_config": skill_md.exists(),
            "description": "",
            "content": "",
        }

        if skill_md.exists():
            try:
                content = skill_md.read_text(encoding="utf-8")
                skill_info["content"] = content
                # 提取第一行非空、非标题行作为描述
                for line in content.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("---"):
                        skill_info["description"] = line[:200]
                        break
            except Exception:
                pass

        skills.append(skill_info)

    return skills


@router.get("/{skill_name}", summary="获取 Skill 详情")
async def get_skill(skill_name: str):
    """获取指定 Skill 的详细内容"""
    skills_dir = get_skills_dir()
    skill_dir = skills_dir / skill_name

    if not skill_dir.exists():
        return {"error": "Skill not found"}

    skill_md = skill_dir / "SKILL.md"
    content = ""
    if skill_md.exists():
        try:
            content = skill_md.read_text(encoding="utf-8")
        except Exception:
            content = "无法读取文件"

    # 列出 skill 目录下所有文件
    files = []
    for f in skill_dir.rglob("*"):
        if f.is_file():
            files.append(str(f.relative_to(skill_dir)))

    return {
        "name": skill_name,
        "content": content,
        "files": files,
    }


@router.put("/{skill_name}", summary="更新 Skill 内容")
async def update_skill(skill_name: str, data: SkillUpdateRequest):
    """更新指定 Skill 的 SKILL.md 内容"""
    skills_dir = get_skills_dir()
    skill_dir = skills_dir / skill_name

    if not skill_dir.exists():
        raise HTTPException(status_code=404, detail="Skill not found")

    skill_md = skill_dir / "SKILL.md"
    try:
        skill_md.write_text(data.content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入失败: {e}")

    return {"message": "更新成功", "name": skill_name}
