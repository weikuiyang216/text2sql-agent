"""Multi-path retriever for hybrid search."""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..embeddings.embedding_client import BaseEmbeddingClient
from ..storage.milvus_client import MilvusClient

logger = logging.getLogger(__name__)


class RetrievalStrategy(str, Enum):
    """Search strategy options."""
    DENSE = "dense"          # Dense vector search only
    HYBRID = "hybrid"        # Dense + keyword hybrid
    ADAPTIVE = "adaptive"    # Adaptive selection


@dataclass
class RetrievalResult:
    """A single retrieval result."""
    chunk_id: str
    content: str
    score: float
    score_type: str  # "dense", "sparse", "hybrid"
    metadata: dict[str, Any]

    @classmethod
    def from_milvus_hit(
        cls,
        hit: dict,
        score_type: str = "dense"
    ) -> "RetrievalResult":
        """Create from Milvus search hit."""
        entity = hit.get("entity", {})
        return cls(
            chunk_id=hit.get("id", ""),
            content=entity.get("content", ""),
            score=hit.get("score", 0),
            score_type=score_type,
            metadata={
                "doc_id": entity.get("doc_id", ""),
                "doc_name": entity.get("doc_name", ""),
                "doc_type": entity.get("doc_type", ""),
                "version": entity.get("version", ""),
                "chapter_num": entity.get("chapter_num", 0),
                "chapter_title": entity.get("chapter_title", ""),
                "article_num": entity.get("article_num", 0),
                "chunk_type": entity.get("chunk_type", ""),
                # Convert Milvus RepeatedScalarContainer to Python list
                "page_numbers": list(entity.get("page_numbers", [])),
                "keywords": entity.get("keywords", ""),
            }
        )


class MultiPathRetriever:
    """Multi-path retriever with hybrid search support."""

    def __init__(
        self,
        milvus_client: MilvusClient,
        embedding_client: BaseEmbeddingClient,
        collection_name: str | None = None
    ):
        self.milvus = milvus_client
        self.embedder = embedding_client
        self.collection_name = collection_name

    async def retrieve(
        self,
        query: str,
        queries: list[str] | None = None,
        top_k: int = 10,
        filters: dict | None = None,
        strategy: RetrievalStrategy = RetrievalStrategy.DENSE
    ) -> list[RetrievalResult]:
        """Retrieve relevant documents.

        Args:
            query: Main query string
            queries: Additional query variants
            top_k: Number of results to return
            filters: Metadata filters
            strategy: Retrieval strategy

        Returns:
            List of RetrievalResult
        """
        all_queries = [query]
        if queries:
            all_queries.extend(queries)

        all_results = []

        for q in all_queries:
            results = await self._single_query_retrieve(
                q, top_k * 2, filters, strategy
            )
            all_results.extend(results)

        # Merge and deduplicate
        merged = self._merge_results(all_results, top_k)
        return merged

    async def _single_query_retrieve(
        self,
        query: str,
        top_k: int,
        filters: dict | None,
        strategy: RetrievalStrategy
    ) -> list[RetrievalResult]:
        """Retrieve for a single query."""
        results = []

        # Dense retrieval
        if strategy in [RetrievalStrategy.DENSE, RetrievalStrategy.HYBRID]:
            dense_results = await self._dense_retrieve(query, top_k, filters)
            results.extend(dense_results)

        # Could add sparse retrieval here for HYBRID strategy
        # For now, we focus on dense retrieval

        return results

    async def _dense_retrieve(
        self,
        query: str,
        top_k: int,
        filters: dict | None
    ) -> list[RetrievalResult]:
        """Dense vector retrieval."""
        # Get query embedding
        embedding_result = await self.embedder.embed(query)
        query_vector = embedding_result.vector

        # Build filter expression
        filter_expr = None
        if filters:
            filter_expr = self.milvus.build_filter_expr(filters)

        # Search Milvus
        hits = self.milvus.search(
            query_vector=query_vector,
            top_k=top_k,
            filter_expr=filter_expr,
            collection_name=self.collection_name
        )

        return [RetrievalResult.from_milvus_hit(hit, "dense") for hit in hits]

    def _merge_results(
        self,
        results: list[RetrievalResult],
        top_k: int
    ) -> list[RetrievalResult]:
        """Merge and deduplicate results."""
        # Deduplicate by chunk_id, keeping highest score
        unique = {}
        for r in results:
            if r.chunk_id not in unique or r.score > unique[r.chunk_id].score:
                unique[r.chunk_id] = r

        # Sort by score
        sorted_results = sorted(unique.values(), key=lambda x: x.score, reverse=True)
        return sorted_results[:top_k]