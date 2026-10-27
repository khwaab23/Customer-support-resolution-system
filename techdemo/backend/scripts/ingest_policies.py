"""Idempotently ingest trusted Markdown policies into the local Chroma collection."""

import argparse
from pathlib import Path
import sys

from app.core.config import get_settings
from app.rag.chunker import PolicyChunker
from app.rag.document_loader import PolicyDocumentError, PolicyDocumentLoader
from app.rag.embeddings import EmbeddingGenerationError, OpenAIEmbeddingGenerator
from app.rag.models import IngestionSummary
from app.rag.vector_store import (
    ChromaPolicyVectorStore,
    IncompatibleEmbeddingConfigurationError,
    VectorStoreError,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Replace only the managed policy collection after new embeddings are prepared.",
    )
    return parser.parse_args()


def main() -> int:
    """Load, chunk, embed, and synchronize policy evidence safely."""
    arguments = parse_args()
    settings = get_settings()
    try:
        documents = PolicyDocumentLoader().load_all()
        chunks = PolicyChunker(
            chunk_size=settings.rag_chunk_size,
            overlap=settings.rag_chunk_overlap,
        ).chunk_documents(documents)
        generator = OpenAIEmbeddingGenerator(settings)
        store = ChromaPolicyVectorStore(
            Path(settings.rag_persist_directory),
            settings.rag_collection_name,
        )
        configuration = store.existing_configuration()
        if (
            configuration is not None
            and configuration.get("embedding_model") != generator.model
            and not arguments.rebuild
        ):
            raise IncompatibleEmbeddingConfigurationError(
                "Existing policy index uses a different embedding model. Run with --rebuild."
            )

        existing_metadata = store.existing_chunk_metadata()
        existing_hashes = {
            chunk_id: str(metadata.get("content_hash", ""))
            for chunk_id, metadata in existing_metadata.items()
        }
        changed_chunks = (
            chunks
            if arguments.rebuild
            else [
                chunk
                for chunk in chunks
                if existing_hashes.get(chunk.chunk_id) != chunk.content_hash
            ]
        )
        existing_sources = {
            str(metadata.get("source_path", "")) for metadata in existing_metadata.values()
        }
        new_chunks = sum(
            1 for chunk in changed_chunks if chunk.source_path not in existing_sources
        )
        updated_chunks = len(changed_chunks) - new_chunks

        # All potentially billable network work occurs before a --rebuild can
        # delete the prior valid collection.
        vectors = generator.embed_documents([chunk.text for chunk in changed_chunks])
        embedding_dimension = (
            len(vectors[0])
            if vectors
            else int((configuration or {}).get("embedding_dimension", 0))
        )
        if embedding_dimension <= 0:
            raise VectorStoreError("Cannot establish embedding dimension for an empty index.")
        upserted, removed = store.synchronize(
            chunks,
            {chunk.chunk_id: vector for chunk, vector in zip(changed_chunks, vectors, strict=True)},
            embedding_model=generator.model,
            embedding_dimension=embedding_dimension,
            rebuild=arguments.rebuild,
        )
        summary = IngestionSummary(
            documents=len(documents),
            chunks=len(chunks),
            new_chunks=new_chunks,
            unchanged_chunks=len(chunks) - len(changed_chunks),
            removed_chunks=removed,
            embedding_model=generator.model,
            embedding_dimension=embedding_dimension,
        )
    except (
        PolicyDocumentError,
        EmbeddingGenerationError,
        VectorStoreError,
    ) as exc:
        print(f"FAIL: Policy ingestion failed: {exc}", file=sys.stderr)
        return 1

    print(f"Documents: {summary.documents}")
    print(f"Chunks: {summary.chunks}")
    print(f"New chunks: {summary.new_chunks}")
    print(f"Updated chunks: {updated_chunks}")
    print(f"Unchanged chunks: {summary.unchanged_chunks}")
    print(f"Removed chunks: {summary.removed_chunks}")
    print(f"Embedding model: {summary.embedding_model}")
    print(f"Embedding dimension: {summary.embedding_dimension}")
    print(f"Upserted chunks: {upserted}")
    print("PASS: Policy ingestion completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
