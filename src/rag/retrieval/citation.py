"""Citation tracker for source attribution."""

import json
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from .reranker import RerankedResult

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """A citation reference."""
    citation_id: str
    source_id: str
    doc_name: str
    chapter: str
    pages: list[int]
    quoted_text: str
    confidence: float

    def to_markdown(self) -> str:
        """Format citation as markdown."""
        page_info = f"第{self.pages[0]}页" if self.pages else ""
        chapter_info = f"，{self.chapter}" if self.chapter else ""
        return f"{self.citation_id} {self.doc_name}{page_info}{chapter_info}"


class CitationTracker:
    """Track and generate citations for RAG responses."""

    def __init__(
        self,
        llm_client: AsyncOpenAI,
        model: str = "qwen2.5"
    ):
        self.llm = llm_client
        self.model = model

    async def generate_citations(
        self,
        answer: str,
        sources: list[RerankedResult]
    ) -> list[Citation]:
        """Generate citations for answer based on sources.

        Args:
            answer: Generated answer text
            sources: Source documents used

        Returns:
            List of Citation objects
        """
        citations = []

        for idx, source in enumerate(sources):
            try:
                cited_spans = await self._find_cited_spans(
                    answer, source.content, idx
                )

                for span in cited_spans:
                    citation = Citation(
                        citation_id=f"[{idx + 1}]",
                        source_id=source.chunk_id,
                        doc_name=source.metadata.get("doc_name", ""),
                        chapter=source.metadata.get("chapter_title", ""),
                        pages=source.metadata.get("page_numbers", []),
                        quoted_text=span.get("quote", ""),
                        confidence=span.get("confidence", 0.5)
                    )
                    citations.append(citation)
            except Exception as e:
                logger.warning(f"Failed to generate citation for source {idx}: {e}")

        return citations

    async def _find_cited_spans(
        self,
        answer: str,
        source_content: str,
        source_idx: int
    ) -> list[dict]:
        """Find spans in source content that support the answer."""
        prompt = f"""分析以下回答与源文档的关系，找出回答中哪些内容来自源文档。

回答：
{answer}

源文档[{source_idx + 1}]：
{source_content[:1500]}

请输出JSON格式：
{{
  "citations": [
    {{
      "answer_text": "回答中的具体文字",
      "source_text": "源文档中对应的原文",
      "confidence": 0.9
    }}
  ]
}}

如果没有明显引用关系，返回空列表。
只输出JSON，不要其他内容。"""

        response = await self._call_llm(prompt)

        try:
            # Try to extract JSON from response
            json_match = response
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                json_match = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                json_match = response[start:end].strip()

            data = json.loads(json_match)

            # Handle case where LLM returns a list directly instead of {"citations": [...]}
            if isinstance(data, list):
                citations_list = data
            else:
                citations_list = data.get("citations", [])

            return [
                {
                    "quote": c.get("source_text", ""),
                    "confidence": c.get("confidence", 0.5)
                }
                for c in citations_list
                if isinstance(c, dict) and c.get("source_text")
            ]
        except json.JSONDecodeError:
            return []

    def format_citations(self, citations: list[Citation]) -> str:
        """Format citations for display."""
        if not citations:
            return ""

        lines = ["\n\n---\n**引用来源：**\n"]

        # Group by document
        by_doc: dict[str, list[Citation]] = {}
        for c in citations:
            if c.doc_name not in by_doc:
                by_doc[c.doc_name] = []
            by_doc[c.doc_name].append(c)

        for doc_name, doc_citations in by_doc.items():
            lines.append(f"\n- **{doc_name}**")
            for c in doc_citations:
                page_info = f"第{c.pages[0]}页" if c.pages else ""
                chapter_info = f"，{c.chapter}" if c.chapter else ""
                lines.append(f"  - {c.citation_id} {page_info}{chapter_info}")

        return "\n".join(lines)

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with prompt."""
        response = await self.llm.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500
        )
        return response.choices[0].message.content or ""