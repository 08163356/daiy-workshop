"""微信读书模块API"""
import hashlib
import logging
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.note import Note
from app.models.weread import WeReadConfig, WeReadBook
from app.services.weread_service import WeReadService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/weread", tags=["微信读书"])


#======================== Schemas ========================

class ConfigCreate(BaseModel):
    api_key: str


# ======================== 配置管理 ========================

@router.get("/status", summary="获取微信读书状态")
async def get_status(db: AsyncSession = Depends(get_db)):
    """返回配置状态、最后同步时间和统计数字"""
    result = await db.execute(select(WeReadConfig).limit(1))
    config = result.scalar_one_or_none()

    # 已同步书目数
    book_count_result = await db.execute(select(WeReadBook))
    books = book_count_result.scalars().all()
    shelf_synced = len(books) > 0

    if not config:
        return {
            "configured": False,
            "last_sync_at": None,
            "total_books": 0,
            "total_notes_synced": 0,
            "shelf_synced": False,
        }

    return {
        "configured": True,
        "last_sync_at": config.last_sync_at.isoformat() if config.last_sync_at else None,
        "total_books": len(books),
        "total_notes_synced": config.total_notes_synced,
        "shelf_synced": shelf_synced,
    }


@router.post("/config", summary="保存微信读书 API Key")
async def save_config(data: ConfigCreate, db: AsyncSession = Depends(get_db)):
    """保存/更新 API Key（宽松验证：格式正确即保存，网络验证失败也不阻断）"""
    api_key = data.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 不能为空")

    # 格式校验（以 wrk- 开头）
    if not api_key.startswith("wrk-"):
        raise HTTPException(status_code=400, detail="API Key 格式不正确，应以 wrk- 开头")

    # 尝试宽松验证（失败不阻断保存）
    verify_msg = ""
    try:
        svc = WeReadService(api_key)
        verify_ok = await svc.verify_key_loose()
        verify_msg = "（接口连通性已验证）" if verify_ok else "（网络验证跳过，保存成功，请尝试同步书架）"
    except Exception:
        verify_msg = "（网络验证跳过，保存成功，请尝试同步书架）"

    result = await db.execute(select(WeReadConfig).limit(1))
    config = result.scalar_one_or_none()

    if config:
        config.api_key = api_key
        config.updated_at = datetime.now()
    else:
        config = WeReadConfig(api_key=api_key)
        db.add(config)

    await db.commit()
    return {"message": f"API Key 已保存{verify_msg}"}


@router.delete("/config", summary="删除微信读书配置")
async def delete_config(db: AsyncSession = Depends(get_db)):
    """删除 API Key 配置"""
    result = await db.execute(select(WeReadConfig).limit(1))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="未找到配置")
    await db.delete(config)
    await db.commit()
    return {"message": "配置已删除"}


# ======================== 书架========================

@router.get("/shelf", summary="获取书架列表")
async def get_shelf(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """返回数据库中的书目列表（分页）"""
    result = await db.execute(
        select(WeReadBook).order_by(desc(WeReadBook.updated_at)).offset(skip).limit(limit)
    )
    books = result.scalars().all()

    total_result = await db.execute(select(WeReadBook))
    total = len(total_result.scalars().all())

    return {
        "books": [
            {
                "id": b.id,
                "book_id": b.book_id,
                "title": b.title,
                "author": b.author,
                "cover": b.cover,
                "category": b.category,
                "reading_progress": b.reading_progress,
                "is_finished": b.is_finished,
                "note_count": b.note_count,
                "last_synced_at": b.last_synced_at.isoformat() if b.last_synced_at else None,
            }
            for b in books
        ],
        "total": total,
    }


# ======================== 统计 ========================

@router.get("/stats", summary="获取微信读书阅读统计")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """实时从微信读书API获取阅读统计"""
    result = await db.execute(select(WeReadConfig).limit(1))
    config = result.scalar_one_or_none()
    if not config:
        return {"today_minutes": None, "week_minutes": None, "month_minutes": None, "total_minutes": None, "total_days": None}

    try:
        svc = WeReadService(config.api_key)
        data = await svc.get_read_stats()

        # 解析 readingDetail
        detail = data.get("readingDetail", data)
        total_time = detail.get("totalTime", 0)  # 秒
        total_minutes = round(total_time / 60) if total_time else None

        # 尝试从bookProgress 或 dailyReadingTime 提取分时数据
        today_minutes = None
        week_minutes = None
        month_minutes = None

        daily_data = data.get("dailyReadingTime", [])
        if daily_data:
            today_str = date.today().isoformat().replace("-", "")
            week_total = 0
            month_total = 0
            today_total = 0
            for entry in daily_data:
                d = str(entry.get("readDate", ""))
                minutes = round(entry.get("readTime", 0) / 60)
                if d == today_str:
                    today_total += minutes
                if len(d) == 8:
                    entry_date = datetime.strptime(d, "%Y%m%d").date()
                    days_diff = (date.today() - entry_date).days
                    if days_diff< 7:
                        week_total += minutes
                    if days_diff < 30:
                        month_total += minutes
            today_minutes = today_total or None
            week_minutes = week_total or None
            month_minutes = month_total or None

        return {
            "today_minutes": today_minutes,
            "week_minutes": week_minutes,
            "month_minutes": month_minutes,
            "total_minutes": total_minutes,
            "total_days": detail.get("continueReadingDays") or detail.get("totalReadingDays"),
        }
    except Exception as e:
        logger.error(f"获取阅读统计失败: {e}")
        return {"today_minutes": None, "week_minutes": None, "month_minutes": None, "total_minutes": None, "total_days": None}


# ======================== 同步 ========================

@router.post("/sync/shelf", summary="同步书架元数据")
async def sync_shelf(db: AsyncSession = Depends(get_db)):
    """从微信读书拉取书架，更新 weread_books 表"""
    result = await db.execute(select(WeReadConfig).limit(1))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=400, detail="未配置微信读书 API Key")

    svc = WeReadService(config.api_key)
    try:
        shelf_data = await svc.get_shelf(synckey=config.sync_key or "")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步失败: {e}")

    books_data = shelf_data.get("books", [])
    sync_key = shelf_data.get("synckey", "")
    synced_count = 0

    for book_info in books_data:
        book = book_info.get("book", book_info)
        book_id = book.get("bookId") or book_info.get("bookId")
        if not book_id:
            continue

        title = book.get("title") or book_info.get("title", "")
        author = book.get("author") or book_info.get("author")
        cover = book.get("cover") or book_info.get("cover")
        category = (book.get("category") or {}).get("title") if isinstance(book.get("category"), dict) else book.get("category")
        intro = book.get("intro") or book_info.get("intro")
        finish_reading_rate = book_info.get("finishedDate") or book_info.get("readingProgress", 0)

        # upsert
        existing = await db.execute(select(WeReadBook).where(WeReadBook.book_id == book_id))
        wb = existing.scalar_one_or_none()
        if wb:
            wb.title = title
            wb.author = author
            wb.cover = cover
            wb.category = category
            wb.intro = intro
            wb.updated_at = datetime.now()
        else:
            wb = WeReadBook(
                book_id=book_id,
                title=title,
                author=author,
                cover=cover,
                category=category,
                intro=intro,
            )
            db.add(wb)
        synced_count += 1

    # 更新 config
    config.sync_key = sync_key
    config.last_sync_at = datetime.now()
    config.total_books = synced_count

    await db.commit()
    return {
        "message": f"书架同步完成，共 {synced_count} 本书",
        "synced_count": synced_count,
        "sync_key": sync_key,
    }


@router.post("/sync/book/{book_id}", summary="同步单本书笔记")
async def sync_book(book_id: str, db: AsyncSession = Depends(get_db)):
    """同步单本书的划线和想法到notes 表"""
    result = await db.execute(select(WeReadConfig).limit(1))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=400, detail="未配置微信读书 API Key")

    # 查书目信息
    book_result = await db.execute(select(WeReadBook).where(WeReadBook.book_id == book_id))
    wb = book_result.scalar_one_or_none()

    svc = WeReadService(config.api_key)
    try:
        bm_data = await svc.get_bookmarks(book_id)
        rv_data = await svc.get_reviews(book_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"拉取笔记失败: {e}")

    bookmarks = bm_data.get("updated", bm_data.get("bookmarks", []))
    reviews_raw = rv_data.get("reviews", [])

    if not bookmarks and not reviews_raw:
        return {"book_id": book_id, "title": wb.title if wb else book_id, "highlights_count": 0, "reviews_count": 0, "message": "没有笔记内容"}

    title = wb.title if wb else book_id
    author = wb.author if wb else None
    cover = wb.cover if wb else None

    content = WeReadService.format_notes_markdown(title, author, bookmarks, reviews_raw)
    content_hash = hashlib.md5(content.encode()).hexdigest()
    filename = f"weread_{book_id}"

    # 取最新划线日期
    create_times = [bm.get("createTime", 0) for bm in bookmarks if bm.get("createTime")]
    reading_date_val = None
    if create_times:
        ts = max(create_times)
        try:
            reading_date_val = datetime.fromtimestamp(ts).date()
        except Exception:
            pass

    # upsert note
    note_result = await db.execute(select(Note).where(Note.filename == filename))
    note = note_result.scalar_one_or_none()
    if note:
        note.title = title
        note.content = content
        note.file_hash = content_hash
        note.word_count = len(content)
        note.images = [cover] if cover else []
        if reading_date_val:
            note.reading_date = reading_date_val
        note.updated_at = datetime.now()
    else:
        note = Note(
            filename=filename,
            title=title,
            content=content,
            file_hash=content_hash,
            word_count=len(content),
            images=[cover] if cover else [],
            reading_date=reading_date_val,
        )
        db.add(note)

    await db.flush()
    note_id = note.id

    # 更新 WeReadBook
    if wb:
        wb.note_count = len(bookmarks) + len(reviews_raw)
        wb.last_synced_at = datetime.now()

    # 更新 config总计数
    config.total_notes_synced = (config.total_notes_synced or 0) + 1

    await db.commit()

    return {
        "book_id": book_id,
        "title": title,
        "note_id": note_id,
        "highlights_count": len(bookmarks),
        "reviews_count": len(reviews_raw),
        "message": f"已同步 {len(bookmarks)} 条划线 + {len(reviews_raw)} 条想法",
    }


@router.post("/sync/all", summary="同步所有有笔记的书")
async def sync_all(db: AsyncSession = Depends(get_db)):
    """同步所有有笔记的书，逐本调用"""
    result = await db.execute(select(WeReadConfig).limit(1))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=400, detail="未配置微信读书 API Key")

    svc = WeReadService(config.api_key)
    try:
        notebooks_data = await svc.get_notebooks()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取笔记列表失败: {e}")

    notebook_books = notebooks_data.get("books", [])
    results = []
    total_synced = 0

    for nb in notebook_books:
        book = nb.get("book", nb)
        book_id = book.get("bookId") or nb.get("bookId")
        if not book_id:
            continue
        try:
            # 内部调用（重用 db session）
            book_result = await db.execute(select(WeReadBook).where(WeReadBook.book_id == book_id))
            wb = book_result.scalar_one_or_none()

            bm_data = await svc.get_bookmarks(book_id)
            rv_data = await svc.get_reviews(book_id)
            bookmarks = bm_data.get("updated", bm_data.get("bookmarks", []))
            reviews_raw = rv_data.get("reviews", [])

            title = wb.title if wb else (book.get("title") or book_id)
            author = wb.author if wb else book.get("author")
            cover = wb.cover if wb else book.get("cover")

            if not bookmarks and not reviews_raw:
                continue

            content = WeReadService.format_notes_markdown(title, author, bookmarks, reviews_raw)
            content_hash = hashlib.md5(content.encode()).hexdigest()
            filename = f"weread_{book_id}"

            create_times = [bm.get("createTime", 0) for bm in bookmarks if bm.get("createTime")]
            reading_date_val = None
            if create_times:
                try:
                    reading_date_val = datetime.fromtimestamp(max(create_times)).date()
                except Exception:
                    pass

            note_result = await db.execute(select(Note).where(Note.filename == filename))
            note = note_result.scalar_one_or_none()
            if note:
                note.content = content
                note.file_hash = content_hash
                note.word_count = len(content)
                note.images = [cover] if cover else []
                if reading_date_val:
                    note.reading_date = reading_date_val
                note.updated_at = datetime.now()
            else:
                note = Note(
                    filename=filename,
                    title=title,
                    content=content,
                    file_hash=content_hash,
                    word_count=len(content),
                    images=[cover] if cover else [],
                    reading_date=reading_date_val,
                )
                db.add(note)

            await db.flush()

            if wb:
                wb.note_count = len(bookmarks) + len(reviews_raw)
                wb.last_synced_at = datetime.now()

            results.append({
                "book_id": book_id,
                "title": title,
                "highlights_count": len(bookmarks),
                "reviews_count": len(reviews_raw),
            })
            total_synced += 1

        except Exception as e:
            logger.warning(f"同步书{book_id} 失败: {e}")
            continue

    config.total_notes_synced = total_synced
    config.last_sync_at = datetime.now()
    await db.commit()

    return {
        "message": f"全量同步完成，成功同步 {total_synced} 本书",
        "results": results,
        "total_synced": total_synced,
    }
