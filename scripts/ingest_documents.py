#!/usr/bin/env python
"""Document ingestion script for RAG pipeline.

Usage:
    python scripts/ingest_documents.py                    # Ingest all PDFs
    python scripts/ingest_documents.py --file contract.pdf # Ingest single file
    python scripts/ingest_documents.py --reset             # Reset collection first
"""

import argparse
import asyncio
import logging
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rag.pipeline import RAGPipeline
from src.config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Ingest documents into RAG pipeline")
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="Single PDF file to ingest"
    )
    parser.add_argument(
        "--dir", "-d",
        type=str,
        default=None,
        help="Directory containing PDFs (default: ./data)"
    )
    parser.add_argument(
        "--reset", "-r",
        action="store_true",
        help="Reset collection before ingestion"
    )
    args = parser.parse_args()

    # Create pipeline
    pipeline = RAGPipeline()
    await pipeline.initialize()

    try:
        # Reset if requested
        if args.reset:
            logger.info("Resetting collection...")
            pipeline.milvus.drop_collection()
            pipeline.milvus.create_collection()
            logger.info("Collection reset complete")

        # Ingest documents
        if args.file:
            pdf_path = Path(args.file)
            if not pdf_path.exists():
                logger.error(f"File not found: {pdf_path}")
                return 1

            count = await pipeline.ingest_document(pdf_path)
            logger.info(f"Ingested {count} chunks from {pdf_path.name}")
        else:
            data_dir = Path(args.dir) if args.dir else config.DOCUMENT_DIR
            count = await pipeline.ingest_all_pdfs(data_dir)
            logger.info(f"Total chunks ingested: {count}")

        # Show stats
        stats = await pipeline.get_stats()
        logger.info(f"Collection stats: {stats}")

    finally:
        await pipeline.close()

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)