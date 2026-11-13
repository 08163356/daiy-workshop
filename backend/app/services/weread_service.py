"""微信读书 API 服务层"""
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GATEWAY_URL = "https://i.weread.qq.com/api/agent/gateway"
SKILL_VERSION = "1.0.4"


class WeReadService:
    """微信读书 API 客户端，统一通过 gateway 调用"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def _call(self, api_name: str, **kwargs) -> dict:
        """统一 API 调用入口（不raise_for_status，处理 WeRead 非标准499响应）"""
        payload = {"api_name": api_name, "skill_version": SKILL_VERSION, **kwargs}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(GATEWAY_URL, json=payload, headers=self.headers)

        # 尝试解析 JSON（WeRead 的499 响应也带有效 JSON body）
        try:
            data = resp.json()
        except Exception:
            # 真的无法解析才抛 HTTP 级别的异常
            resp.raise_for_status()
            return {}

        # 检查 WeRead 业务错误码（负数表示错误）
        if isinstance(data, dict) and data.get("errcode", 0) != 0:
            errcode = data.get("errcode", -1)
            errmsg = data.get("errmsg", "未知错误")
            raise Exception(f"WeRead API 错误 {errcode}: {errmsg}")

        return data

    async def get_shelf(self, synckey: str = "") -> dict:
        """获取书架（支持增量 synckey）"""
        kwargs: dict = {}
        if synckey:
            kwargs["synckey"] = synckey
        return await self._call("/shelf/sync", **kwargs)

    async def get_notebooks(self, count: int = 500) -> dict:
        """获取有笔记的书列表"""
        return await self._call("/user/notebooks", count=count)

    async def get_bookmarks(self, book_id: str) -> dict:
        """获取某书的全部划线"""
        return await self._call("/book/bookmarklist", bookId=book_id)

    async def get_reviews(self, book_id: str, count: int = 500) -> dict:
        """获取某书的个人想法（注意：此接口参数名为 bookid 全小写）"""
        return await self._call("/review/list/mine", bookid=book_id, count=count)

    async def get_read_stats(self) -> dict:
        """获取阅读统计数据"""
        return await self._call("/readdata/detail", readingType=0)

    async def verify_key(self) -> bool:
        """验证 API Key是否有效（严格）"""
        try:
            result = await self._call("/readdata/detail", readingType=0)
            return isinstance(result, dict)
        except Exception as e:
            logger.error(f"WeRead API Key验证失败: {e}")
            return False

    async def verify_key_loose(self) -> bool:
        """宽松验证：只要能连接到 WeRead 并得到响应就算成功（忽略业务错误码）"""
        try:
            payload = {"api_name": "/shelf/sync", "skill_version": SKILL_VERSION}
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(GATEWAY_URL, json=payload, headers=self.headers)
            # 只要服务器有响应（不论状态码）就认为 key 格式可用
            return resp is not None
        except Exception as e:
            logger.warning(f"WeRead 宽松验证失败: {e}")
            return False

    @staticmethod
    def format_notes_markdown(
        title: str,
        author: Optional[str],
        bookmarks: list,
        reviews: list,
    ) -> str:
        """将划线和想法格式化为 Markdown 笔记"""
        lines = [
            f"# {title}",
            f"作者：{author or '未知'}",
            "来源：微信读书",
            "",
        ]

        if bookmarks:
            lines.append(f"## 划线摘录（共{len(bookmarks)} 条）")
            lines.append("")
            # 按章节分组
            chapter_map: dict[str, list[str]] = {}
            for bm in bookmarks:
                chapter = bm.get("chapterName") or "未知章节"
                text = bm.get("markText", "").strip()
                if text:
                    chapter_map.setdefault(chapter, []).append(text)
            for chapter, texts in chapter_map.items():
                lines.append(f"### {chapter}")
                for t in texts:
                    lines.append(f"> {t}")
                    lines.append("")

        if reviews:
            lines.append(f"## 个人想法（共 {len(reviews)} 条）")
            lines.append("")
            for r in reviews:
                review = r.get("review", r)# 有时 review 包在 review 字段里
                content = review.get("content", "").strip()
                chapter = review.get("chapterName") or ""
                if content:
                    if chapter:
                        lines.append(f"*{chapter}*")
                    lines.append(f"> {content}")
                    lines.append("")

        return "\n".join(lines)
