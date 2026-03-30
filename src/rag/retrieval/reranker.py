"""Reranker for improving retrieval quality."""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from openai import AsyncOpenAI

from .multi_retriever import RetrievalResult

logger = logging.getLogger(__name__)


class RerankStrategy(str, Enum):
    """Reranking strategy options."""
    CROSS_ENCODER = "cross_encoder"  # LLM-based scoring
    DIVERSITY = "diversity"           # MMR-style diversity
    COMBINED = "combined"             # Combined approach


@dataclass
class RerankedResult:
    """A reranked retrieval result."""
    original: RetrievalResult
    rerank_score: float
    combined_score: float

    @property
    def chunk_id(self) -> str:
        return self.original.chunk_id

    @property
    def content(self) -> str:
        return self.original.content

    @property
    def metadata(self) -> dict[str, Any]:
        return self.original.metadata


class Reranker:
    """Reranker for improving retrieval quality."""

    def __init__(
        self,
        llm_client: AsyncOpenAI,
        model: str = "qwen2.5"
    ):
        self.llm = llm_client
        self.model = model

    async def rerank(
        self,
        query: str,
        results: list[RetrievalResult],
        top_k: int = 5,
        strategy: RerankStrategy = RerankStrategy.CROSS_ENCODER
    ) -> list[RerankedResult]:
        """Rerank retrieval results.

        Args:
            query: Original query
            results: Retrieval results to rerank
            top_k: Number of results to return
            strategy: Reranking strategy

        Returns:
            Reranked results
        """
        if not results:
            return []

        if strategy == RerankStrategy.CROSS_ENCODER:
            return await self._cross_encoder_rerank(query, results, top_k)
        elif strategy == RerankStrategy.DIVERSITY:
            return await self._diversity_rerank(query, results, top_k)
        else:  # COMBINED
            reranked = await self._cross_encoder_rerank(query, results, top_k * 2)
            return await self._diversity_rerank(query, reranked, top_k)

    async def _cross_encoder_rerank(
        self,
        query: str,
        results: list[RetrievalResult],
        top_k: int
    ) -> list[RerankedResult]:
        """Rerank using LLM relevance scoring."""
        batch_size = 5
        scored_results = []

        for i in range(0, len(results), batch_size):
            batch = results[i:i + batch_size]
            scores = await self._score_relevance_batch(query, batch)

            for result, score in zip(batch, scores):
                combined = 0.7 * score + 0.3 * result.score
                scored_results.append(RerankedResult(
                    original=result,
                    rerank_score=score,
                    combined_score=combined
                ))

        # Sort by combined score
        scored_results.sort(key=lambda x: x.combined_score, reverse=True)
        return scored_results[:top_k]

    async def _score_relevance_batch(
        self,
        query: str,
        results: list[RetrievalResult]
    ) -> list[float]:
        """Score relevance of documents to query using LLM."""
        docs_text = "\n\n---\n\n".join([
            f"[文档{i + 1}]\n{r.content[:500]}..."
            for i, r in enumerate(results)
        ])

        prompt = f"""请评估以下文档与查询的相关性，为每个文档打分（0-10分）。

查询：{query}

{docs_text}

请只输出分数，每行一个，格式如下：
文档1: X分
文档2: X分
...

评分标准：
- 10分：完全回答了查询
- 7-9分：高度相关，包含关键信息
- 4-6分：部分相关
- 1-3分：低相关
- 0分：不相关"""

        response = await self._call_llm(prompt)

        # Parse scores
        scores = []
        for i in range(len(results)):
            pattern = rf"文档{i + 1}:\s*(\d+(?:\.\d+)?)\s*分"
            match = re.search(pattern, response)
            if match:
                scores.append(float(match.group(1)) / 10.0)
            else:
                scores.append(0.5)  # Default score

        return scores

    async def _diversity_rerank(
        self,
        query: str,
        results: list[RetrievalResult] | list[RerankedResult],
        top_k: int,
        lambda_param: float = 0.7
    ) -> list[RerankedResult]:
        """MMR-style diversity reranking."""
        selected: list[RerankedResult] = []
        remaining = list(results)

        while len(selected) < top_k and remaining:
            best_score = float('-inf')
            best_idx = 0

            for i, candidate in enumerate(remaining):
                # Get relevance score
                if isinstance(candidate, RerankedResult):
                    relevance = candidate.combined_score
                    content = candidate.content
                else:
                    relevance = candidate.score
                    content = candidate.content

                # Calculate diversity penalty
                if selected:
                    max_sim = max(
                        self._compute_similarity(content, s.content)
                        for s in selected
                    )
                else:
                    max_sim = 0

                # MMR score
                mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i

            best = remaining.pop(best_idx)
            if isinstance(best, RerankedResult):
                selected.append(best)
            else:
                selected.append(RerankedResult(
                    original=best,
                    rerank_score=best.score,
                    combined_score=best.score
                ))

        return selected

    def _compute_similarity(self, text1: str, text2: str) -> float:
        """Compute simple text similarity (Jaccard on words)."""
        # Simple word-based similarity
        words1 = set(text1)
        words2 = set(text2)

        if not words1 or not words2:
            return 0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM with prompt."""
        response = await self.llm.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300
        )
        return response.choices[0].message.content or ""