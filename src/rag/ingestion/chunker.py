"""Document chunker for splitting documents into retrieval units."""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .pdf_parser import ParsedDocument, ParsedSection, ParsedTable

logger = logging.getLogger(__name__)


class ChunkType(str, Enum):
    """Type of document chunk."""
    DOCUMENT = "document"
    CHAPTER = "chapter"
    ARTICLE = "article"
    PARAGRAPH = "paragraph"
    TABLE = "table"


@dataclass
class Chunk:
    """A chunk of document content for retrieval."""
    id: str
    content: str
    chunk_type: ChunkType
    doc_id: str
    doc_name: str
    doc_type: str
    version: str
    chapter_num: int | None = None
    chapter_title: str | None = None
    article_num: int | None = None
    page_numbers: list[int] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    parent_id: str | None = None
    children_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for Milvus insertion."""
        # Filter out None values from keywords
        keywords = [k for k in self.keywords if k is not None]
        return {
            "id": self.id,
            "content": self.content,
            "doc_id": self.doc_id,
            "doc_name": self.doc_name,
            "doc_type": self.doc_type,
            "version": self.version,
            "chapter_num": self.chapter_num or 0,
            "chapter_title": self.chapter_title or "",
            "article_num": self.article_num or 0,
            "chunk_type": self.chunk_type.value,
            "page_numbers": self.page_numbers,
            "keywords": ",".join(keywords) if keywords else "",
        }


class DocumentChunker:
    """Split documents into chunks for vector storage."""

    # Chinese numeral to integer mapping
    CHINESE_NUM_MAP = {
        "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
        "十": 10, "百": 100
    }

    def __init__(
        self,
        chapter_max_tokens: int = 1500,
        article_max_tokens: int = 500,
        paragraph_max_tokens: int = 800,
        overlap_tokens: int = 150
    ):
        self.chapter_max_tokens = chapter_max_tokens
        self.article_max_tokens = article_max_tokens
        self.paragraph_max_tokens = paragraph_max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, doc: ParsedDocument) -> list[Chunk]:
        """Chunk a parsed document.

        Args:
            doc: Parsed document from PDFParser

        Returns:
            List of Chunk objects
        """
        chunks = []

        # Create document-level chunk
        doc_chunk = self._create_document_chunk(doc)
        chunks.append(doc_chunk)

        # Track chapter for parent-child relationships
        current_chapter_id = None

        for section in doc.sections:
            if section.level == 1:  # Chapter
                chapter_chunk = self._create_chapter_chunk(doc, section)
                chunks.append(chapter_chunk)
                current_chapter_id = chapter_chunk.id

                # Add as child of document
                doc_chunk.children_ids.append(chapter_chunk.id)

            elif section.level == 2:  # Article
                article_chunk = self._create_article_chunk(
                    doc, section, current_chapter_id
                )
                chunks.append(article_chunk)

                # Add as child of chapter
                if current_chapter_id:
                    for c in chunks:
                        if c.id == current_chapter_id:
                            c.children_ids.append(article_chunk.id)
                            break

        # Create table chunks
        for i, table in enumerate(doc.tables):
            table_chunk = self._create_table_chunk(doc, table, i)
            chunks.append(table_chunk)

        logger.info(f"Created {len(chunks)} chunks from {doc.doc_name}")
        return chunks

    def _create_document_chunk(self, doc: ParsedDocument) -> Chunk:
        """Create document-level chunk."""
        # Use first 2000 chars as summary
        content = doc.full_text[:2000]
        if len(doc.full_text) > 2000:
            content += "..."

        return Chunk(
            id=self._generate_id(doc.doc_id, "doc"),
            content=content,
            chunk_type=ChunkType.DOCUMENT,
            doc_id=doc.doc_id,
            doc_name=doc.doc_name,
            doc_type=doc.metadata.get("doc_type", ""),
            version=doc.metadata.get("version", ""),
            page_numbers=list(range(min(3, doc.page_count))),
            keywords=self._extract_keywords(content)
        )

    def _create_chapter_chunk(
        self,
        doc: ParsedDocument,
        section: ParsedSection
    ) -> Chunk:
        """Create chapter-level chunk."""
        chapter_num = self._chinese_to_int(section.number)

        # Build content
        content = f"{section.number} {section.title}\n\n{section.content}"

        return Chunk(
            id=self._generate_id(doc.doc_id, f"ch{chapter_num}"),
            content=self._truncate(content, self.chapter_max_tokens),
            chunk_type=ChunkType.CHAPTER,
            doc_id=doc.doc_id,
            doc_name=doc.doc_name,
            doc_type=doc.metadata.get("doc_type", ""),
            version=doc.metadata.get("version", ""),
            chapter_num=chapter_num,
            chapter_title=section.title,
            page_numbers=section.page_numbers,
            keywords=self._extract_keywords(content)
        )

    def _create_article_chunk(
        self,
        doc: ParsedDocument,
        section: ParsedSection,
        parent_chapter_id: str | None
    ) -> Chunk:
        """Create article-level chunk."""
        article_num = self._chinese_to_int(section.number)

        # Build content
        content = f"{section.number} {section.title}\n\n{section.content}"

        # Split long articles into paragraphs
        if len(content) > self.article_max_tokens * 2:
            return self._split_article(doc, section, parent_chapter_id)

        return Chunk(
            id=self._generate_id(doc.doc_id, f"art{article_num}"),
            content=self._truncate(content, self.article_max_tokens),
            chunk_type=ChunkType.ARTICLE,
            doc_id=doc.doc_id,
            doc_name=doc.doc_name,
            doc_type=doc.metadata.get("doc_type", ""),
            version=doc.metadata.get("version", ""),
            chapter_num=self._find_chapter_num(doc, section),
            article_num=article_num,
            page_numbers=section.page_numbers,
            parent_id=parent_chapter_id,
            keywords=self._extract_keywords(content)
        )

    def _split_article(
        self,
        doc: ParsedDocument,
        section: ParsedSection,
        parent_chapter_id: str | None
    ) -> Chunk:
        """Split long article into paragraph chunks."""
        # For now, just truncate - could be extended to split
        article_num = self._chinese_to_int(section.number)
        content = f"{section.number} {section.title}\n\n{section.content}"

        return Chunk(
            id=self._generate_id(doc.doc_id, f"art{article_num}"),
            content=self._truncate(content, self.article_max_tokens),
            chunk_type=ChunkType.ARTICLE,
            doc_id=doc.doc_id,
            doc_name=doc.doc_name,
            doc_type=doc.metadata.get("doc_type", ""),
            version=doc.metadata.get("version", ""),
            chapter_num=self._find_chapter_num(doc, section),
            article_num=article_num,
            page_numbers=section.page_numbers,
            parent_id=parent_chapter_id,
            keywords=self._extract_keywords(content)
        )

    def _create_table_chunk(
        self,
        doc: ParsedDocument,
        table: ParsedTable,
        index: int
    ) -> Chunk:
        """Create table chunk."""
        return Chunk(
            id=self._generate_id(doc.doc_id, f"tbl{index}"),
            content=table.content,
            chunk_type=ChunkType.TABLE,
            doc_id=doc.doc_id,
            doc_name=doc.doc_name,
            doc_type=doc.metadata.get("doc_type", ""),
            version=doc.metadata.get("version", ""),
            page_numbers=[table.page_number],
            keywords=table.headers
        )

    def _generate_id(self, doc_id: str, suffix: str) -> str:
        """Generate unique chunk ID."""
        base = f"{doc_id}_{suffix}"
        return hashlib.md5(base.encode()).hexdigest()[:16]

    def _chinese_to_int(self, chinese_num: str) -> int:
        """Convert Chinese numeral to integer.

        e.g., "第一章" -> 1, "第十二条" -> 12
        """
        # Extract the number part
        match = re.search(r'第([一二三四五六七八九十百]+)', chinese_num)
        if not match:
            return 0

        num_str = match.group(1)

        # Simple conversion for common cases
        if len(num_str) == 1:
            return self.CHINESE_NUM_MAP.get(num_str, 0)
        elif num_str == "十":
            return 10
        elif num_str.startswith("十"):
            return 10 + self.CHINESE_NUM_MAP.get(num_str[1], 0)
        elif num_str.endswith("十"):
            return self.CHINESE_NUM_MAP.get(num_str[0], 0) * 10
        else:
            # Handle cases like "二十三"
            result = 0
            for i, char in enumerate(num_str):
                if char == "十":
                    result += 10
                elif char == "百":
                    result += 100
                else:
                    val = self.CHINESE_NUM_MAP.get(char, 0)
                    if i + 1 < len(num_str) and num_str[i + 1] in "十百":
                        result += val * (10 if num_str[i + 1] == "十" else 100)
                    elif i == 0 or num_str[i - 1] not in "十百":
                        result += val
            return result

    def _find_chapter_num(self, doc: ParsedDocument, section: ParsedSection) -> int:
        """Find the chapter number for a section."""
        chapter_num = 0
        for s in doc.sections:
            if s.level == 1:
                chapter_num = self._chinese_to_int(s.number)
            if s == section:
                break
        return chapter_num

    def _truncate(self, text: str, max_tokens: int) -> str:
        """Truncate text to approximate token limit.

        Using rough estimate: 1 Chinese char ≈ 1 token
        """
        if len(text) <= max_tokens:
            return text
        return text[:max_tokens - 3] + "..."

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract keywords from text.

        Simple implementation - could be enhanced with LLM or NER.
        """
        keywords = []

        # Common financial terms to look for
        financial_terms = [
            "利率", "期限", "金额", "还款", "贷款", "利息",
            "违约", "保证", "抵押", "质押", "担保",
            "合同", "借款人", "贷款人", "银行",
            "年利率", "月利率", "逾期", "罚息"
        ]

        for term in financial_terms:
            if term in text:
                keywords.append(term)

        return keywords[:10]  # Limit to 10 keywords


def chunk_document(doc: ParsedDocument) -> list[Chunk]:
    """Convenience function to chunk a document."""
    chunker = DocumentChunker()
    return chunker.chunk(doc)