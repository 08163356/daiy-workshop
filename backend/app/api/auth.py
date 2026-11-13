"""认证 API - 密码验证 & Token 管理"""

import secrets
import bcrypt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.auth import AuthConfig, AuthToken, LockSettings
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["认证"])


def hash_password(password: str) -> str:
    """使用带盐的 bcrypt 存储密码。"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password_hash(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


class VerifyRequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/verify")
async def verify_password(
    data: VerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """验证密码，返回 token（前端存 localStorage 实现记住登录）"""
    # 获取数据库中的密码
    result = await db.execute(select(AuthConfig).limit(1))
    config = result.scalar_one_or_none()

    if not config:
        if not settings.initial_admin_password:
            raise HTTPException(
                status_code=503,
                detail="尚未初始化管理员密码，请设置 INITIAL_ADMIN_PASSWORD 后重启",
            )
        config = AuthConfig(password_hash=hash_password(settings.initial_admin_password))
        db.add(config)
        await db.flush()

    # 验证
    if not verify_password_hash(data.password, config.password_hash):
        raise HTTPException(status_code=401, detail="密码错误")

    # 生成 token
    token = secrets.token_hex(32)
    device_info = request.headers.get("user-agent", "")[:200]
    auth_token = AuthToken(
        token=token,
        device_info=device_info,
        expires_at=datetime.now() + timedelta(days=90),  # 90天有效
    )
    db.add(auth_token)
    await db.flush()

    return {"token": token, "expires_in_days": 90}


@router.post("/check")
async def check_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """检查 token 是否有效（前端每次加载时调用）"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供 token")

    token = auth_header[7:]
    result = await db.execute(
        select(AuthToken).where(AuthToken.token == token)
    )
    auth_token = result.scalar_one_or_none()

    if not auth_token:
        raise HTTPException(status_code=401, detail="token 无效")

    # 检查过期
    if auth_token.expires_at and auth_token.expires_at < datetime.now():
        raise HTTPException(status_code=401, detail="token 已过期")

    return {"valid": True}


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """修改密码"""
    result = await db.execute(select(AuthConfig).limit(1))
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=400, detail="尚未设置密码")

    if not verify_password_hash(data.old_password, config.password_hash):
        raise HTTPException(status_code=401, detail="旧密码错误")

    if len(data.new_password) < 10:
        raise HTTPException(status_code=400, detail="新密码至少需要 10 个字符")

    config.password_hash = hash_password(data.new_password)
    await db.flush()

    return {"message": "密码修改成功"}


@router.post("/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """登出（删除 token）"""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        result = await db.execute(
            select(AuthToken).where(AuthToken.token == token)
        )
        auth_token = result.scalar_one_or_none()
        if auth_token:
            await db.delete(auth_token)

    return {"message": "已登出"}


# ==================== 锁屏设置 ====================


class LockSettingsUpdate(BaseModel):
    auto_lock_minutes: int


@router.get("/lock-settings")
async def get_lock_settings(db: AsyncSession = Depends(get_db)):
    """获取锁屏设置"""
    result = await db.execute(select(LockSettings).limit(1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = LockSettings(auto_lock_minutes=13)
        db.add(settings)
        await db.flush()
    return {"auto_lock_minutes": settings.auto_lock_minutes}


@router.put("/lock-settings")
async def update_lock_settings(
    data: LockSettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新锁屏设置"""
    if data.auto_lock_minutes < 1 or data.auto_lock_minutes > 120:
        raise HTTPException(status_code=400, detail="自动锁定时间需在 1-120 分钟之间")
    result = await db.execute(select(LockSettings).limit(1))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = LockSettings(auto_lock_minutes=data.auto_lock_minutes)
        db.add(settings)
    else:
        settings.auto_lock_minutes = data.auto_lock_minutes
    await db.flush()
    return {"auto_lock_minutes": settings.auto_lock_minutes}
