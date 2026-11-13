"""图片上传 API"""

import os
import uuid
import logging
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uploads", tags=["文件上传"])

# 上传目录（相对于后端工作目录）
UPLOAD_DIR = Path("uploads/images")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 允许的图片格式
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    """上传图片文件
    
    返回图片的访问 URL，可用于日记、笔记、对话等模块
    支持 jpg/png/gif/webp/heic 格式，最大 10MB
    """
    # 验证文件类型
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}，允许: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # 读取文件内容
    content = await file.read()
    
    # 验证文件大小
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"文件过大，最大允许 {MAX_FILE_SIZE // 1024 // 1024}MB")
    
    # 生成唯一文件名：年月/uuid.ext
    now = datetime.now()
    sub_dir = UPLOAD_DIR / now.strftime("%Y%m")
    sub_dir.mkdir(parents=True, exist_ok=True)
    
    unique_name = f"{uuid.uuid4().hex[:12]}{ext}"
    file_path = sub_dir / unique_name
    
    # 写入文件
    with open(file_path, "wb") as f:
        f.write(content)
    
    # 返回相对路径作为 URL（前端通过 /api/uploads/images/xxx 访问）
    relative_path = f"{now.strftime('%Y%m')}/{unique_name}"
    
    logger.info(f"图片上传成功: {relative_path}, 大小: {len(content)} bytes")
    
    return {
        "url": f"/api/uploads/images/{relative_path}",
        "filename": file.filename,
        "size": len(content),
        "content_type": file.content_type,
    }


@router.post("/images")
async def upload_multiple_images(files: list[UploadFile] = File(...)):
    """批量上传图片（最多 9 张）"""
    if len(files) > 9:
        raise HTTPException(status_code=400, detail="最多同时上传 9 张图片")
    
    results = []
    for file in files:
        if not file.filename:
            continue
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            continue
        
        now = datetime.now()
        sub_dir = UPLOAD_DIR / now.strftime("%Y%m")
        sub_dir.mkdir(parents=True, exist_ok=True)
        
        unique_name = f"{uuid.uuid4().hex[:12]}{ext}"
        file_path = sub_dir / unique_name
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        relative_path = f"{now.strftime('%Y%m')}/{unique_name}"
        results.append({
            "url": f"/api/uploads/images/{relative_path}",
            "filename": file.filename,
            "size": len(content),
        })
    
    return {"images": results, "count": len(results)}


@router.get("/images/{year_month}/{filename}")
async def get_image(year_month: str, filename: str):
    """获取已上传的图片"""
    file_path = UPLOAD_DIR / year_month / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    
    # 安全检查：防止路径穿越
    try:
        file_path.resolve().relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="访问被拒绝")
    
    return FileResponse(file_path)
