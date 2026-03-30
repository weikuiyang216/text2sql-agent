"""Embedding client for text vectorization."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from openai import AsyncOpenAI


@dataclass
class EmbeddingResult:
    """Embedding result container."""
    vector: list[float]
    model: str
    tokens_used: int


class BaseEmbeddingClient(ABC):
    """Base class for embedding clients."""

    @abstractmethod
    async def embed(self, text: str) -> EmbeddingResult:
        """Embed a single text."""
        pass

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed multiple texts."""
        pass


class OpenAIEmbeddingClient(BaseEmbeddingClient):
    """OpenAI-compatible embedding client."""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int | None = None,
        batch_size: int = 10  # DashScope limit is 10
    ):
        self.client = AsyncOpenAI(base_url=api_base, api_key=api_key)
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size

    async def embed(self, text: str) -> EmbeddingResult:
        """Embed a single text."""
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed multiple texts with batching."""
        all_results = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            response = await self.client.embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self.dimensions
            )

            for item in response.data:
                all_results.append(EmbeddingResult(
                    vector=item.embedding,
                    model=self.model,
                    tokens_used=response.usage.total_tokens // len(batch)
                ))

        return all_results


class ZhipuEmbeddingClient(BaseEmbeddingClient):
    """Zhipu AI embedding client."""

    def __init__(
        self,
        api_key: str,
        model: str = "embedding-3",
        batch_size: int = 16
    ):
        self.api_key = api_key
        self.model = model
        self.batch_size = batch_size
        self.client = AsyncOpenAI(
            base_url="https://open.bigmodel.cn/api/paas/v4",
            api_key=api_key
        )

    async def embed(self, text: str) -> EmbeddingResult:
        """Embed a single text."""
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed multiple texts."""
        all_results = []

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            response = await self.client.embeddings.create(
                model=self.model,
                input=batch
            )

            for item in response.data:
                all_results.append(EmbeddingResult(
                    vector=item.embedding,
                    model=self.model,
                    tokens_used=response.usage.total_tokens // len(batch)
                ))

        return all_results


def create_embedding_client(
    provider: Literal["openai", "zhipu", "dashscope"] = "dashscope",
    api_base: str | None = None,
    api_key: str | None = None,
    model: str = "text-embedding-v4",
    dimensions: int | None = None
) -> BaseEmbeddingClient:
    """Factory function to create embedding client."""

    if provider == "openai":
        return OpenAIEmbeddingClient(
            api_base=api_base or "https://api.openai.com/v1",
            api_key=api_key or "",
            model=model,
            dimensions=dimensions
        )
    elif provider == "zhipu":
        return ZhipuEmbeddingClient(
            api_key=api_key or "",
            model=model
        )
    elif provider == "dashscope":
        # DashScope uses OpenAI-compatible API
        return OpenAIEmbeddingClient(
            api_base=api_base or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=api_key or "",
            model=model,
            dimensions=dimensions
        )
    else:
        raise ValueError(f"Unsupported embedding provider: {provider}")