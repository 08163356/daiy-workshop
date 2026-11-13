"""API 路由模块"""

from fastapi import APIRouter

from app.api import notes, concepts, sync, investment, diary, chat, skills, todo, reading, kb, time_log, auth, wellbeing, basketball, coaching, uploads, time_capsule, weread, wishlist, ai_question, agent, prompt_skills, profile_admin, review, blog, interview

api_router = APIRouter(prefix="/api")

# 认证模块（不需要鉴权的公开路由）
api_router.include_router(auth.router)

# 读书模块
api_router.include_router(notes.router)
api_router.include_router(concepts.router)
api_router.include_router(sync.router)
api_router.include_router(reading.router)

# 投资模块
api_router.include_router(investment.router)

# 日记模块
api_router.include_router(diary.router)

# 待办模块
api_router.include_router(todo.router)

# 统一对话 & AI 配置
api_router.include_router(chat.router)

# Skill 管理
api_router.include_router(skills.router)

# 知识库模块
api_router.include_router(kb.router)

# 时间记录模块
api_router.include_router(time_log.router)

# 心力模块（成就 + 感恩）
api_router.include_router(wellbeing.router)

# 篮球反思模块
api_router.include_router(basketball.router)

# 教练对话模块
api_router.include_router(coaching.router)

# 文件上传模块
api_router.include_router(uploads.router)

# 时光胶囊模块
api_router.include_router(time_capsule.router)

# 微信读书模块
api_router.include_router(weread.router)

# 心愿清单模块
api_router.include_router(wishlist.router)

# AI 提问队列模块
api_router.include_router(ai_question.router)

# 统一 AI 助手模块
api_router.include_router(agent.router)

# Prompt Skill 管理模块
api_router.include_router(prompt_skills.router)

# 用户画像管理模块（分层：画像层 CRUD + 快照 + 整理提案）
api_router.include_router(profile_admin.router)

# 审批中心模块（AI 自动化产出的人工审核）
api_router.include_router(review.router)

# 个人博客公开索引检索（助手 search_blog / 调试）
api_router.include_router(blog.router)

# interview 作品集/面试材料检索（助手 search_interview / 调试）
api_router.include_router(interview.router)

__all__ = ["api_router"]
