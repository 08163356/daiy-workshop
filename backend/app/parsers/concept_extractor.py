"""概念提取器"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractedConcept:
    """提取的概念"""

    name: str
    category: Optional[str] = None
    position: int = 0  # 在文本中的位置
    context: str = ""  # 上下文


@dataclass
class ExtractionResult:
    """提取结果"""

    concepts: list[ExtractedConcept] = field(default_factory=list)
    relations: list[tuple[str, str, str, float]] = field(
        default_factory=list
    )  # (source, target, type, strength)


class ConceptExtractor:
    """概念提取器"""

    # 概念分类映射
    CATEGORY_PATTERNS = {
        "书籍": r"《(.+?)》",
        "模型": r"([\u4e00-\u9fff]+模型)",
        "理论": r"([\u4e00-\u9fff]+理论)",
        "法则": r"([\u4e00-\u9fff]+法则)",
        "效应": r"([\u4e00-\u9fff]+效应)",
        "定律": r"([\u4e00-\u9fff]+定律)",
        "原则": r"([\u4e00-\u9fff]+原则)",
        "思维": r"([\u4e00-\u9fff]+思维)",
        "方法": r"([\u4e00-\u9fff]+方法|[\u4e00-\u9fff]+法)",
    }

    # 英文专有名词模式（首字母大写，至少2个单词）
    ENGLISH_PROPER_NOUN = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b"

    # 加粗文本
    BOLD_TEXT = r"\*\*([^*]+)\*\*"

    # 停用词（不应被提取的常见词）
    STOP_WORDS = {
        "的", "是", "在", "有", "和", "与", "或", "但", "而",
        "这个", "那个", "一个", "什么", "怎么", "如何", "为什么",
        "The", "This", "That", "What", "How", "Why", "When",
    }

    # 最小概念长度
    MIN_CONCEPT_LENGTH = 2
    MAX_CONCEPT_LENGTH = 30

    def __init__(self) -> None:
        pass

    def extract(self, content: str) -> ExtractionResult:
        """从内容中提取概念和关系"""
        result = ExtractionResult()
        seen_concepts: dict[str, ExtractedConcept] = {}

        # 1. 提取书名号内容
        self._extract_book_titles(content, seen_concepts)

        # 2. 提取中文术语（模型、理论等）
        self._extract_chinese_terms(content, seen_concepts)

        # 3. 提取英文专有名词
        self._extract_english_proper_nouns(content, seen_concepts)

        # 4. 提取加粗文本
        self._extract_bold_text(content, seen_concepts)

        # 去重并过滤
        result.concepts = self._filter_concepts(list(seen_concepts.values()))

        # 5. 推断概念关系（同篇文章共现）
        result.relations = self._infer_relations(result.concepts)

        return result

    def _extract_book_titles(
        self, content: str, seen: dict[str, ExtractedConcept]
    ) -> None:
        """提取书名号内容"""
        pattern = self.CATEGORY_PATTERNS["书籍"]
        for match in re.finditer(pattern, content):
            name = match.group(1).strip()
            if self._is_valid_concept(name) and name not in seen:
                seen[name] = ExtractedConcept(
                    name=name,
                    category="书籍",
                    position=match.start(),
                    context=self._get_context(content, match.start()),
                )

    def _extract_chinese_terms(
        self, content: str, seen: dict[str, ExtractedConcept]
    ) -> None:
        """提取中文术语"""
        for category, pattern in self.CATEGORY_PATTERNS.items():
            if category == "书籍":
                continue  # 已单独处理

            for match in re.finditer(pattern, content):
                name = match.group(1).strip()
                if self._is_valid_concept(name) and name not in seen:
                    seen[name] = ExtractedConcept(
                        name=name,
                        category=category,
                        position=match.start(),
                        context=self._get_context(content, match.start()),
                    )

    def _extract_english_proper_nouns(
        self, content: str, seen: dict[str, ExtractedConcept]
    ) -> None:
        """提取英文专有名词"""
        for match in re.finditer(self.ENGLISH_PROPER_NOUN, content):
            name = match.group(1).strip()
            if self._is_valid_concept(name) and name not in seen:
                seen[name] = ExtractedConcept(
                    name=name,
                    category="专有名词",
                    position=match.start(),
                    context=self._get_context(content, match.start()),
                )

    def _extract_bold_text(
        self, content: str, seen: dict[str, ExtractedConcept]
    ) -> None:
        """提取加粗文本"""
        for match in re.finditer(self.BOLD_TEXT, content):
            name = match.group(1).strip()
            # 加粗文本需要更严格的过滤
            if (
                self._is_valid_concept(name)
                and name not in seen
                and len(name) >= 2
                and not name.isdigit()
                and not re.match(r"^[\d\s\-:,.]+$", name)  # 排除纯数字/符号
            ):
                seen[name] = ExtractedConcept(
                    name=name,
                    category="关键词",
                    position=match.start(),
                    context=self._get_context(content, match.start()),
                )

    def _is_valid_concept(self, name: str) -> bool:
        """检查是否是有效概念"""
        if not name:
            return False

        if len(name) < self.MIN_CONCEPT_LENGTH or len(name) > self.MAX_CONCEPT_LENGTH:
            return False

        if name in self.STOP_WORDS:
            return False

        # 排除纯数字
        if name.isdigit():
            return False

        # 排除 URL
        if name.startswith(("http://", "https://", "www.")):
            return False

        return True

    def _get_context(self, content: str, position: int, context_len: int = 50) -> str:
        """获取概念的上下文"""
        start = max(0, position - context_len)
        end = min(len(content), position + context_len)
        context = content[start:end]
        # 清理换行
        return re.sub(r"\s+", " ", context).strip()

    def _filter_concepts(
        self, concepts: list[ExtractedConcept]
    ) -> list[ExtractedConcept]:
        """过滤和去重概念"""
        # 按位置排序
        concepts.sort(key=lambda c: c.position)
        return concepts

    def _infer_relations(
        self, concepts: list[ExtractedConcept]
    ) -> list[tuple[str, str, str, float]]:
        """推断概念关系"""
        relations: list[tuple[str, str, str, float]] = []

        # 同一文章中的概念建立 co_occurs 关系
        for i, c1 in enumerate(concepts):
            for c2 in concepts[i + 1 :]:
                # 关系强度 = 1 / (位置差距 / 1000 + 1)
                distance = abs(c2.position - c1.position)
                strength = round(1 / (distance / 1000 + 1), 3)

                # 只保留强度大于 0.1 的关系
                if strength > 0.1:
                    relations.append((c1.name, c2.name, "co_occurs", strength))

        return relations
