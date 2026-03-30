"""RAG Pipeline - Main orchestration module."""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from ..config import config
from .embeddings.embedding_client import create_embedding_client
from .ingestion.chunker import DocumentChunker, Chunk
from .ingestion.pdf_parser import PDFParser, ParsedDocument
from .storage.milvus_client import MilvusClient
from .retrieval.citation import Citation, CitationTracker
from .retrieval.multi_retriever import MultiPathRetriever, RetrievalResult, RetrievalStrategy
from .retrieval.query_rewriter import QueryRewriter, RewrittenQuery
from .retrieval.reranker import Reranker, RerankedResult, RerankStrategy

logger = logging.getLogger(__name__)


@dataclass
class RAGResponse:
    """RAG response container."""
    query: str
    answer: str
    sources: list[RerankedResult]
    citations: list[Citation]
    rewritten_query: RewrittenQuery | None = None
    metadata: dict[str, Any] = None


class RAGPipeline:
    """Main RAG pipeline for document ingestion and retrieval."""

    def __init__(
        self,
        llm_client: AsyncOpenAI | None = None,
        milvus_client: MilvusClient | None = None,
        embedding_client: Any = None,
        model: str | None = None
    ):
        # LLM client
        self.llm = llm_client or AsyncOpenAI(
            base_url=config.OPENAI_API_BASE,
            api_key=config.OPENAI_API_KEY
        )
        self.model = model or config.DEFAULT_MODEL

        # Milvus client
        self.milvus = milvus_client or MilvusClient(
            host=config.MILVUS_HOST,
            port=config.MILVUS_PORT,
            collection_prefix=config.MILVUS_COLLECTION_PREFIX,
            dim=config.EMBEDDING_DIM
        )

        # Embedding client
        self.embedder = embedding_client or create_embedding_client(
            provider=config.EMBEDDING_PROVIDER,
            api_base=config.EMBEDDING_API_BASE,
            api_key=config.EMBEDDING_API_KEY,
            model=config.EMBEDDING_MODEL,
            dimensions=config.EMBEDDING_DIM
        )

        # Pipeline components
        self.query_rewriter = QueryRewriter(self.llm, self.model)
        self.retriever = MultiPathRetriever(self.milvus, self.embedder)
        self.reranker = Reranker(self.llm, self.model)
        self.citation_tracker = CitationTracker(self.llm, self.model)

        # Parser and chunker
        self.parser = PDFParser()
        self.chunker = DocumentChunker()

        self._initialized = False

    async def initialize(self):
        """Initialize the pipeline (connect to Milvus, etc.)."""
        if self._initialized:
            return

        # Connect to Milvus
        if not self.milvus.connect():
            raise RuntimeError("Failed to connect to Milvus")

        # Ensure collection exists
        self.milvus.create_collection()

        self._initialized = True
        logger.info("RAG Pipeline initialized")

    async def close(self):
        """Close connections."""
        self.milvus.disconnect()
        self._initialized = False

    # ==================== Ingestion ====================

    async def ingest_document(self, pdf_path: Path) -> int:
        """Ingest a single PDF document.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Number of chunks inserted
        """
        await self.initialize()

        # Parse PDF
        logger.info(f"Parsing {pdf_path}")
        parsed = self.parser.parse(pdf_path)

        # Chunk document
        chunks = self.chunker.chunk(parsed)

        # Generate embeddings
        texts = [c.content for c in chunks]
        embedding_results = await self.embedder.embed_batch(texts)

        # Prepare data for Milvus
        data = []
        for chunk, emb in zip(chunks, embedding_results):
            row = chunk.to_dict()
            row["vector"] = emb.vector
            data.append(row)

        # Insert into Milvus
        count = self.milvus.insert(data)

        logger.info(f"Ingested {pdf_path.name}: {count} chunks")
        return count

    async def ingest_documents(
        self,
        pdf_paths: list[Path],
        show_progress: bool = True
    ) -> int:
        """Ingest multiple PDF documents.

        Args:
            pdf_paths: List of PDF file paths
            show_progress: Whether to show progress

        Returns:
            Total chunks inserted
        """
        total = 0
        for i, path in enumerate(pdf_paths):
            try:
                count = await self.ingest_document(path)
                total += count
                if show_progress:
                    logger.info(f"Progress: {i + 1}/{len(pdf_paths)}")
            except Exception as e:
                logger.error(f"Failed to ingest {path}: {e}")

        return total

    async def ingest_all_pdfs(self, data_dir: Path | None = None) -> int:
        """Ingest all PDF files from data directory.

        Args:
            data_dir: Directory containing PDFs (default from config)

        Returns:
            Total chunks inserted
        """
        doc_dir = data_dir or config.DOCUMENT_DIR
        pdf_paths = list(doc_dir.glob("*.pdf"))

        if not pdf_paths:
            logger.warning(f"No PDF files found in {doc_dir}")
            return 0

        logger.info(f"Found {len(pdf_paths)} PDF files")
        return await self.ingest_documents(pdf_paths)

    # ==================== Retrieval ====================

    async def query(
        self,
        question: str,
        top_k: int | None = None,
        rerank_top_k: int | None = None,
        filters: dict | None = None,
        with_citations: bool = True
    ) -> RAGResponse:
        """Query the RAG pipeline.

        Args:
            question: User question
            top_k: Number of initial results
            rerank_top_k: Number of results after reranking
            filters: Metadata filters
            with_citations: Whether to generate citations

        Returns:
            RAGResponse with answer and sources
        """
        await self.initialize()

        top_k = top_k or config.RAG_TOP_K
        rerank_top_k = rerank_top_k or config.RAG_RERANK_TOP_K

        # Step 1: Query rewriting
        rewritten = await self.query_rewriter.rewrite(question)
        logger.debug(f"Rewritten queries: {rewritten.all_queries()}")

        # Step 2: Multi-path retrieval
        results = await self.retriever.retrieve(
            query=question,
            queries=rewritten.expanded,
            top_k=top_k,
            filters=filters,
            strategy=RetrievalStrategy.DENSE
        )

        if not results:
            return RAGResponse(
                query=question,
                answer="抱歉，未找到相关文档内容。",
                sources=[],
                citations=[],
                rewritten_query=rewritten
            )

        # Step 3: Reranking
        reranked = await self.reranker.rerank(
            question, results, rerank_top_k, RerankStrategy.CROSS_ENCODER
        )

        # Step 4: Generate answer
        answer = await self._generate_answer(question, reranked)

        # Step 5: Generate citations
        citations = []
        if with_citations:
            citations = await self.citation_tracker.generate_citations(
                answer, reranked
            )

        return RAGResponse(
            query=question,
            answer=answer,
            sources=reranked,
            citations=citations,
            rewritten_query=rewritten
        )

    async def _generate_answer(
        self,
        question: str,
        sources: list[RerankedResult]
    ) -> str:
        """Generate answer from retrieved sources."""
        context = "\n\n---\n\n".join([
            f"【文档{i + 1}】{s.metadata.get('doc_name', '')}\n{s.content}"
            for i, s in enumerate(sources)
        ])

        prompt = f"""基于以下文档内容，回答用户问题。

文档内容：
{context}

用户问题：{question}

要求：
1. 基于文档内容回答，不要编造信息
2. 如果文档中没有相关信息，直接说明
3. 回答要简洁、准确
4. 可以引用文档编号（如【文档1】）来支持回答

回答："""

        response = await self.llm.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000
        )

        answer = response.choices[0].message.content or ""

        # Add citations
        if sources:
            answer += self.citation_tracker.format_citations([
                Citation(
                    citation_id=f"[{i + 1}]",
                    source_id=s.chunk_id,
                    doc_name=s.metadata.get("doc_name", ""),
                    chapter=s.metadata.get("chapter_title", ""),
                    pages=s.metadata.get("page_numbers", []),
                    quoted_text="",
                    confidence=0.9
                )
                for i, s in enumerate(sources)
            ])

        return answer

    # ==================== Management ====================

    async def get_stats(self) -> dict:
        """Get pipeline statistics."""
        await self.initialize()
        count = self.milvus.count()
        return {
            "total_chunks": count,
            "collection": self.milvus.collection_prefix
        }

    async def delete_document(self, doc_id: str):
        """Delete all chunks for a document."""
        await self.initialize()
        self.milvus.delete_by_doc_id(doc_id)
        logger.info(f"Deleted document: {doc_id}")


# Convenience function
async def create_rag_pipeline() -> RAGPipeline:
    """Create and initialize a RAG pipeline."""
    pipeline = RAGPipeline()
    await pipeline.initialize()
    return pipeline