"""Milvus client wrapper for vector storage operations."""

import logging
from typing import Any

from pymilvus import (
    Collection,
    connections,
    utility
)

from .schema import (
    get_dense_collection_schema,
    get_dense_index_params,
    ChunkType
)

logger = logging.getLogger(__name__)


class MilvusClient:
    """Milvus vector database client."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        collection_prefix: str = "boc_contracts",
        dim: int = 1024
    ):
        self.host = host
        self.port = port
        self.collection_prefix = collection_prefix
        self.dim = dim
        self._connected = False
        self._collection: Collection | None = None

    def connect(self) -> bool:
        """Connect to Milvus server."""
        try:
            connections.connect(
                alias="default",
                host=self.host,
                port=self.port
            )
            self._connected = True
            logger.info(f"Connected to Milvus at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            return False

    def disconnect(self):
        """Disconnect from Milvus server."""
        try:
            connections.disconnect("default")
            self._connected = False
            logger.info("Disconnected from Milvus")
        except Exception as e:
            logger.error(f"Failed to disconnect: {e}")

    def create_collection(self, collection_name: str | None = None) -> str:
        """Create a collection with predefined schema.

        Args:
            collection_name: Optional custom collection name

        Returns:
            Collection name
        """
        if not self._connected:
            self.connect()

        name = collection_name or f"{self.collection_prefix}_dense_v1"

        if utility.has_collection(name):
            logger.info(f"Collection {name} already exists")
            return name

        schema = get_dense_collection_schema(self.dim)
        collection = Collection(name=name, schema=schema)

        # Create index
        index_params = get_dense_index_params()
        collection.create_index(
            field_name="vector",
            index_params=index_params
        )

        logger.info(f"Created collection {name} with index")
        return name

    def drop_collection(self, collection_name: str | None = None):
        """Drop a collection."""
        name = collection_name or f"{self.collection_prefix}_dense_v1"
        if utility.has_collection(name):
            utility.drop_collection(name)
            logger.info(f"Dropped collection {name}")

    def get_collection(self, collection_name: str | None = None) -> Collection:
        """Get collection instance."""
        name = collection_name or f"{self.collection_prefix}_dense_v1"

        if self._collection is None or self._collection.name != name:
            if not utility.has_collection(name):
                self.create_collection(name)
            self._collection = Collection(name)

        return self._collection

    def insert(
        self,
        data: list[dict],
        collection_name: str | None = None
    ) -> int:
        """Insert documents into collection.

        Args:
            data: List of document dicts

        Returns:
            Number of inserted documents
        """
        collection = self.get_collection(collection_name)

        # Use row-based format for Milvus
        insert_data = []
        for item in data:
            row = {
                "id": item["id"],
                "vector": item["vector"],
                "content": item.get("content", ""),
                "doc_id": item.get("doc_id", ""),
                "doc_name": item.get("doc_name", ""),
                "doc_type": item.get("doc_type", ""),
                "version": item.get("version", ""),
                "chapter_num": item.get("chapter_num", 0),
                "chapter_title": item.get("chapter_title", ""),
                "article_num": item.get("article_num", 0),
                "chunk_type": item.get("chunk_type", ChunkType.PARAGRAPH.value),
                "page_numbers": item.get("page_numbers", []),
                "keywords": item.get("keywords", ""),
            }
            insert_data.append(row)

        result = collection.insert(insert_data)
        collection.flush()

        logger.info(f"Inserted {len(insert_data)} documents")
        return result.insert_count

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filter_expr: str | None = None,
        output_fields: list[str] | None = None,
        collection_name: str | None = None
    ) -> list[dict]:
        """Search for similar documents.

        Args:
            query_vector: Query embedding vector
            top_k: Number of results to return
            filter_expr: Milvus filter expression
            output_fields: Fields to return
            collection_name: Collection to search

        Returns:
            List of search results with scores and metadata
        """
        collection = self.get_collection(collection_name)
        collection.load()

        if output_fields is None:
            output_fields = [
                "id", "content", "doc_id", "doc_name", "doc_type",
                "version", "chapter_num", "chapter_title", "article_num",
                "chunk_type", "page_numbers", "keywords"
            ]

        search_params = {
            "metric_type": "COSINE",
            "params": {"ef": 64}
        }

        results = collection.search(
            data=[query_vector],
            anns_field="vector",
            param=search_params,
            limit=top_k,
            expr=filter_expr,
            output_fields=output_fields
        )

        # Format results
        formatted_results = []
        for hits in results:
            for hit in hits:
                formatted_results.append({
                    "id": hit.id,
                    "score": hit.score,
                    "entity": {field: hit.entity.get(field) for field in output_fields}
                })

        return formatted_results

    def delete_by_doc_id(
        self,
        doc_id: str,
        collection_name: str | None = None
    ):
        """Delete all chunks belonging to a document."""
        collection = self.get_collection(collection_name)
        expr = f'doc_id == "{doc_id}"'
        collection.delete(expr)
        collection.flush()
        logger.info(f"Deleted chunks for doc_id: {doc_id}")

    def count(self, collection_name: str | None = None) -> int:
        """Get number of documents in collection."""
        collection = self.get_collection(collection_name)
        collection.load()
        return collection.num_entities

    def build_filter_expr(self, filters: dict) -> str:
        """Build Milvus filter expression from dict.

        Args:
            filters: Dict like {"doc_type": "住房贷款", "version": "2025年版"}

        Returns:
            Milvus filter expression string
        """
        conditions = []
        for key, value in filters.items():
            if isinstance(value, str):
                conditions.append(f'{key} == "{value}"')
            elif isinstance(value, list):
                values_str = ', '.join(f'"{v}"' for v in value)
                conditions.append(f'{key} in [{values_str}]')
            elif isinstance(value, (int, float)):
                conditions.append(f'{key} == {value}')
        return ' and '.join(conditions) if conditions else ""