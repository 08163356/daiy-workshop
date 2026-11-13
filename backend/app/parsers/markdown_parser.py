"""Markdown 解析器"""

import re
import hashlib
from pathlib import Path
from datetime import date
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedNote:
    """解析后的笔记数据"""

    filename: str
    title: str
    content: str
    summary: Optional[str]
    reading_date: Optional[date]
    word_count: int
    file_hash: str


class MarkdownParser:
    """Markdown 文件解析器"""

    # 日期提取正则（支持 MMDD、MM-DD、YYYY-MM-DD 等格式）
    DATE_PATTERNS = [
        r"^(\d{4})[-/]?(\d{2})[-/]?(\d{2})",  # 20241120 或 2024-11-20
        r"^(\d{2})(\d{2})",  # 1120 (MMDD)
    ]

    def __init__(self) -> None:
        pass

    def parse_file(self, file_path: Path) -> ParsedNote:
        """解析单个 MD 文件"""
        content = file_path.read_text(encoding="utf-8")
        filename = file_path.name

        # 提取标题（去掉日期前缀）
        title = self._extract_title(filename, content)

        # 提取摘要（第一段非标题内容）
        summary = self._extract_summary(content)

        # 提取阅读日期
        reading_date = self._extract_date(filename)

        # 计算字数（中文按字计，英文按词计）
        word_count = self._count_words(content)

        # 计算文件哈希
        file_hash = self._compute_hash(content)

        return ParsedNote(
            filename=filename,
            title=title,
            content=content,
            summary=summary,
            reading_date=reading_date,
            word_count=word_count,
            file_hash=file_hash,
        )

    def _extract_title(self, filename: str, content: str) -> str:
        """提取标题"""
        # 优先从文件名提取（去掉日期前缀和扩展名）
        name_without_ext = filename.rsplit(".", 1)[0]

        # 去掉开头的日期（4位或8位数字）
        title_from_filename = re.sub(r"^\d{4,8}", "", name_without_ext).strip()

        if title_from_filename:
            return title_from_filename

        # 如果文件名只有日期，尝试从内容的一级标题提取
        h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if h1_match:
            return h1_match.group(1).strip()

        return name_without_ext

    def _extract_summary(self, content: str) -> Optional[str]:
        """提取摘要（第一段有意义的文本）"""
        # 去掉标题行
        lines = content.split("\n")
        summary_lines = []

        in_content = False
        for line in lines:
            stripped = line.strip()
            # 跳过空行和标题
            if not stripped:
                if in_content:
                    break  # 遇到空行结束
                continue

            if stripped.startswith("#"):
                in_content = True
                continue

            if in_content or not stripped.startswith("#"):
                summary_lines.append(stripped)
                in_content = True
                if len("".join(summary_lines)) > 200:
                    break

        summary = " ".join(summary_lines)
        return summary[:500] if summary else None

    def _extract_date(self, filename: str) -> Optional[date]:
        """从文件名提取日期"""
        name_without_ext = filename.rsplit(".", 1)[0]

        # 尝试 MMDD 格式（假设是当前年份或上一年）
        match = re.match(r"^(\d{2})(\d{2})", name_without_ext)
        if match:
            month, day = int(match.group(1)), int(match.group(2))
            if 1 <= month <= 12 and 1 <= day <= 31:
                # 默认使用 2024 年
                try:
                    return date(2024, month, day)
                except ValueError:
                    pass

        # 尝试完整日期格式
        match = re.match(r"^(\d{4})[-/]?(\d{2})[-/]?(\d{2})", name_without_ext)
        if match:
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            try:
                return date(year, month, day)
            except ValueError:
                pass

        return None

    def _count_words(self, content: str) -> int:
        """计算字数"""
        # 去掉 Markdown 语法
        text = re.sub(r"[#*`\[\]()!]", "", content)
        text = re.sub(r"\s+", " ", text)

        # 中文字符数
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))

        # 英文单词数
        english_words = len(re.findall(r"[a-zA-Z]+", text))

        return chinese_chars + english_words

    def _compute_hash(self, content: str) -> str:
        """计算内容哈希"""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
