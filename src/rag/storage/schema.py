"""Milvus collection schema definitions."""

from enum import Enum

from pymilvus import CollectionSchema, FieldSchema, DataType


class ChunkType(str, Enum):
    """Document chunk types."""
    DOCUMENT = "document"
    CHAPTER = "chapter"
    ARTICLE = "article"
    PARAGRAPH = "paragraph"
    TABLE = "table"


def get_dense_collection_schema(dim: int = 1024) -> CollectionSchema:
    """Get schema for dense vector collection.

    Args:
        dim: Vector dimension (default 1024 for text-embedding-3-small)
    """
    return CollectionSchema(
        fields=[
            # Primary key
            FieldSchema(
                name="id",
                dtype=DataType.VARCHAR,
                max_length=64,
                is_primary=True,
                auto_id=False
            ),
            # Dense vector
            FieldSchema(
                name="vector",
                dtype=DataType.FLOAT_VECTOR,
                dim=dim
            ),
            # Content
            FieldSchema(
                name="content",
                dtype=DataType.VARCHAR,
                max_length=8000
            ),
            # Document metadata
            FieldSchema(
                name="doc_id",
                dtype=DataType.VARCHAR,
                max_length=128
            ),
            FieldSchema(
                name="doc_name",
                dtype=DataType.VARCHAR,
                max_length=512
            ),
            FieldSchema(
                name="doc_type",
                dtype=DataType.VARCHAR,
                max_length=64
            ),
            FieldSchema(
                name="version",
                dtype=DataType.VARCHAR,
                max_length=32
            ),
            # Structure metadata
            FieldSchema(
                name="chapter_num",
                dtype=DataType.INT64
            ),
            FieldSchema(
                name="chapter_title",
                dtype=DataType.VARCHAR,
                max_length=256
            ),
            FieldSchema(
                name="article_num",
                dtype=DataType.INT64
            ),
            FieldSchema(
                name="chunk_type",
                dtype=DataType.VARCHAR,
                max_length=32
            ),
            # Retrieval metadata
            FieldSchema(
                name="page_numbers",
                dtype=DataType.ARRAY,
                element_type=DataType.INT64,
                max_capacity=20
            ),
            FieldSchema(
                name="keywords",
                dtype=DataType.VARCHAR,
                max_length=512
            ),
        ],
        description="Bank loan contract document collection"
    )


def get_dense_index_params() -> dict:
    """Get index parameters for dense vector collection."""
    return {
        "metric_type": "COSINE",
        "index_type": "HNSW",
        "params": {
            "M": 16,
            "efConstruction": 256
        }
    }


def get_sparse_collection_schema() -> CollectionSchema:
    """Get schema for sparse vector collection (optional)."""
    return CollectionSchema(
        fields=[
            FieldSchema(
                name="id",
                dtype=DataType.VARCHAR,
                max_length=64,
                is_primary=True,
                auto_id=False
            ),
            FieldSchema(
                name="sparse_vector",
                dtype=DataType.SPARSE_FLOAT_VECTOR
            ),
            FieldSchema(
                name="content",
                dtype=DataType.VARCHAR,
                max_length=8000
            ),
            FieldSchema(
                name="doc_id",
                dtype=DataType.VARCHAR,
                max_length=64
            ),
        ],
        description="Sparse vector collection for keyword search"
    )


def get_sparse_index_params() -> dict:
    """Get index parameters for sparse vector collection."""
    return {
        "metric_type": "IP",
        "index_type": "SPARSE_INVERTED_INDEX",
        "params": {"drop_ratio_build": 0.2}
    }