"""PDF document parser using PyMuPDF."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class ParsedSection:
    """Represents a parsed section/chapter from the document."""
    level: int  # 1=chapter, 2=article, 3=paragraph
    number: str  # e.g., "第一章", "第二条"
    title: str
    content: str
    page_numbers: list[int] = field(default_factory=list)
    char_start: int = 0
    char_end: int = 0


@dataclass
class ParsedTable:
    """Represents a parsed table from the document."""
    content: str  # Markdown format
    page_number: int
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """Container for parsed PDF document."""
    doc_id: str
    doc_name: str
    full_text: str
    sections: list[ParsedSection]
    tables: list[ParsedTable]
    metadata: dict
    page_count: int


class PDFParser:
    """Parse PDF documents with structure extraction."""

    # Patterns for Chinese document structure
    CHAPTER_PATTERN = re.compile(r'^(第[一二三四五六七八九十百]+章)\s*(.*)$')
    ARTICLE_PATTERN = re.compile(r'^(第[一二三四五六七八九十百]+条)\s*(.*)$')
    SECTION_PATTERN = re.compile(r'^第[一二三四五六七八九十百]+节\s*(.*)$')

    def __init__(self):
        pass

    def parse(self, pdf_path: Path) -> ParsedDocument:
        """Parse a PDF document.

        Args:
            pdf_path: Path to PDF file

        Returns:
            ParsedDocument with extracted content and structure
        """
        doc = fitz.open(pdf_path)

        doc_id = pdf_path.stem
        doc_name = pdf_path.name

        # Extract metadata
        metadata = self._extract_metadata(doc, pdf_path)

        # Extract full text and structure
        full_text, sections = self._extract_text_and_sections(doc)

        # Extract tables
        tables = self._extract_tables(doc)

        parsed = ParsedDocument(
            doc_id=doc_id,
            doc_name=doc_name,
            full_text=full_text,
            sections=sections,
            tables=tables,
            metadata=metadata,
            page_count=len(doc)
        )

        doc.close()
        logger.info(f"Parsed {doc_name}: {len(sections)} sections, {len(tables)} tables")
        return parsed

    def _extract_metadata(self, doc: fitz.Document, pdf_path: Path) -> dict:
        """Extract document metadata."""
        metadata = {
            "file_name": pdf_path.name,
            "file_size": pdf_path.stat().st_size,
            "page_count": len(doc),
        }

        # Extract document type and version from filename
        filename = pdf_path.stem

        # Extract version (e.g., "2024年版", "2025年版")
        version_match = re.search(r'（(\d{4})年(?:修订)?版）', filename)
        if version_match:
            metadata["version"] = version_match.group(1) + "年版"

        # Extract document type
        if "住房贷款" in filename:
            metadata["doc_type"] = "住房贷款"
        elif "汽车贷款" in filename or "车辆贷款" in filename:
            metadata["doc_type"] = "汽车贷款"
        elif "留学贷款" in filename:
            metadata["doc_type"] = "留学贷款"
        elif "经营" in filename:
            metadata["doc_type"] = "经营贷款"
        elif "循环贷款" in filename:
            metadata["doc_type"] = "循环贷款"
        elif "网络贷款" in filename or "E贷" in filename:
            metadata["doc_type"] = "网络贷款"
        elif "质押" in filename:
            metadata["doc_type"] = "质押合同"
        elif "抵押" in filename:
            metadata["doc_type"] = "抵押合同"
        elif "保证" in filename:
            metadata["doc_type"] = "保证合同"
        else:
            metadata["doc_type"] = "其他"

        return metadata

    def _extract_text_and_sections(
        self,
        doc: fitz.Document
    ) -> tuple[str, list[ParsedSection]]:
        """Extract full text and identify document sections."""
        full_text_parts = []
        sections = []
        char_pos = 0

        for page_num, page in enumerate(doc):
            text = page.get_text("text")
            lines = text.split('\n')

            current_section = None
            current_content = []
            section_start = char_pos

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Check for chapter heading
                chapter_match = self.CHAPTER_PATTERN.match(line)
                if chapter_match:
                    # Save previous section
                    if current_section and current_content:
                        current_section.content = '\n'.join(current_content)
                        current_section.char_end = char_pos
                        sections.append(current_section)

                    current_section = ParsedSection(
                        level=1,
                        number=chapter_match.group(1),
                        title=chapter_match.group(2),
                        content="",
                        page_numbers=[page_num],
                        char_start=char_pos
                    )
                    current_content = []
                    continue

                # Check for article heading
                article_match = self.ARTICLE_PATTERN.match(line)
                if article_match:
                    # Save previous section
                    if current_section and current_content:
                        current_section.content = '\n'.join(current_content)
                        current_section.char_end = char_pos
                        sections.append(current_section)

                    current_section = ParsedSection(
                        level=2,
                        number=article_match.group(1),
                        title=article_match.group(2),
                        content="",
                        page_numbers=[page_num],
                        char_start=char_pos
                    )
                    current_content = []
                    continue

                # Add content to current section
                if current_section:
                    current_content.append(line)
                    if page_num not in current_section.page_numbers:
                        current_section.page_numbers.append(page_num)

                # Add to full text
                full_text_parts.append(line)
                char_pos += len(line) + 1  # +1 for newline

            # Save last section on page
            if current_section and current_content:
                current_section.content = '\n'.join(current_content)
                current_section.char_end = char_pos
                sections.append(current_section)
                current_section = None

        full_text = '\n'.join(full_text_parts)
        return full_text, sections

    def _extract_tables(self, doc: fitz.Document) -> list[ParsedTable]:
        """Extract tables from document."""
        tables = []

        for page_num, page in enumerate(doc):
            # Get tables using PyMuPDF's table extraction
            try:
                tab = page.find_tables()
                if tab.tables:
                    for table in tab.tables:
                        # Convert to markdown
                        md_content = self._table_to_markdown(table)
                        tables.append(ParsedTable(
                            content=md_content,
                            page_number=page_num,
                            headers=table.header.names if table.header else [],
                            rows=[row for row in table.extract()]
                        ))
            except Exception as e:
                logger.warning(f"Failed to extract table from page {page_num}: {e}")

        return tables

    def _table_to_markdown(self, table) -> str:
        """Convert table to Markdown format."""
        rows = table.extract()
        if not rows:
            return ""

        lines = []

        # Header row
        if rows:
            header = rows[0]
            lines.append("| " + " | ".join(str(cell or "") for cell in header) + " |")
            lines.append("| " + " | ".join("---" for _ in header) + " |")

            # Data rows
            for row in rows[1:]:
                lines.append("| " + " | ".join(str(cell or "") for cell in row) + " |")

        return '\n'.join(lines)


def parse_pdf(pdf_path: Path) -> ParsedDocument:
    """Convenience function to parse a PDF."""
    parser = PDFParser()
    return parser.parse(pdf_path)