"""Persistent ChromaDB storage isolated to the managed policy collection."""

from collections.abc import Mapping, Sequence
import json
from pathlib import Path

from app.rag.models import PolicyChunk


class VectorStoreError(RuntimeError):
    """The managed policy vector store could not be read or updated safely."""


class IncompatibleEmbeddingConfigurationError(VectorStoreError):
    """An existing collection uses a different model or vector dimension."""


class ChromaPolicyVectorStore:
    """Store policy chunks in one explicitly managed persistent Chroma collection."""

    def __init__(self, persist_directory: Path, collection_name: str) -> None:
        self._persist_directory = persist_directory
        self._collection_name = collection_name
        self._client = None

    def existing_configuration(self) -> dict[str, object] | None:
        collection = self._existing_collection()
        return dict(collection.metadata or {}) if collection is not None else None

    def existing_content_hashes(self) -> dict[str, str]:
        collection = self._existing_collection()
        if collection is None:
            return {}
        stored = collection.get(include=["metadatas"])
        return {
            chunk_id: str(metadata.get("content_hash", ""))
            for chunk_id, metadata in zip(stored["ids"], stored["metadatas"], strict=True)
        }

    def existing_chunk_metadata(self) -> dict[str, dict[str, object]]:
        """Return managed chunk metadata for ingestion change classification."""
        collection = self._existing_collection()
        if collection is None:
            return {}
        stored = collection.get(include=["metadatas"])
        return {
            chunk_id: dict(metadata)
            for chunk_id, metadata in zip(stored["ids"], stored["metadatas"], strict=True)
        }

    def synchronize(
        self,
        chunks: Sequence[PolicyChunk],
        embeddings_by_id: Mapping[str, Sequence[float]],
        *,
        embedding_model: str,
        embedding_dimension: int,
        rebuild: bool = False,
    ) -> tuple[int, int]:
        """Upsert prepared chunks, then remove stale IDs only from this collection."""
        if embedding_dimension <= 0:
            raise VectorStoreError("Embedding dimension must be positive.")
        if any(len(vector) != embedding_dimension for vector in embeddings_by_id.values()):
            raise VectorStoreError("Embedding dimensions do not match collection configuration.")

        collection = self._existing_collection()
        if collection is not None and not self._configuration_matches(
            collection.metadata or {}, embedding_model, embedding_dimension
        ):
            if not rebuild:
                raise IncompatibleEmbeddingConfigurationError(
                    "Existing policy collection uses a different embedding configuration. "
                    "Run ingestion with --rebuild after embeddings are prepared."
                )
            self._client_or_raise().delete_collection(self._collection_name)
            collection = None

        if collection is None:
            collection = self._client_or_raise().get_or_create_collection(
                name=self._collection_name,
                metadata={
                    "embedding_model": embedding_model,
                    "embedding_dimension": embedding_dimension,
                },
            )

        active_ids = {chunk.chunk_id for chunk in chunks}
        changed = [chunk for chunk in chunks if chunk.chunk_id in embeddings_by_id]
        if changed:
            collection.upsert(
                ids=[chunk.chunk_id for chunk in changed],
                documents=[chunk.text for chunk in changed],
                embeddings=[list(embeddings_by_id[chunk.chunk_id]) for chunk in changed],
                metadatas=[self._metadata(chunk) for chunk in changed],
            )

        stored = collection.get(include=[])
        stale_ids = [chunk_id for chunk_id in stored["ids"] if chunk_id not in active_ids]
        if stale_ids:
            collection.delete(ids=stale_ids)
        return len(changed), len(stale_ids)

    def search(self, query_embedding: Sequence[float], top_k: int) -> list[dict[str, object]]:
        """Return nearest stored policy chunks with their text, metadata, and distance."""
        collection = self._existing_collection()
        if collection is None or collection.count() == 0:
            return []
        result = collection.query(
            query_embeddings=[list(query_embedding)],
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        return [
            {
                "id": chunk_id,
                "text": document,
                "metadata": metadata,
                "distance": distance,
            }
            for chunk_id, document, metadata, distance in zip(
                result["ids"][0],
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
                strict=True,
            )
        ]

    def _client_or_raise(self):
        if self._client is None:
            try:
                import chromadb
            except ImportError as exc:
                raise VectorStoreError(
                    "The chromadb package is required for policy vector storage."
                ) from exc
            self._persist_directory.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self._persist_directory))
        return self._client

    def _existing_collection(self):
        client = self._client_or_raise()
        collections = client.list_collections()
        # Chroma 0.5 returned Collection objects; 0.6 returns names. Converting
        # to str supports both without calling the deprecated ``.name`` shim.
        names = {str(collection) for collection in collections}
        if self._collection_name not in names:
            return None
        return client.get_collection(self._collection_name)

    @staticmethod
    def _configuration_matches(
        metadata: Mapping[str, object],
        model: str,
        dimension: int,
    ) -> bool:
        return (
            metadata.get("embedding_model") == model
            and int(metadata.get("embedding_dimension", -1)) == dimension
        )

    @staticmethod
    def _metadata(chunk: PolicyChunk) -> dict[str, str]:
        return {
            "content_hash": chunk.content_hash,
            "policy_id": chunk.policy_id or "",
            "document_title": chunk.document_title or "",
            "policy_version": chunk.policy_version or "",
            "effective_date": chunk.effective_date.isoformat() if chunk.effective_date else "",
            "section_heading": chunk.section_heading,
            "heading_path": json.dumps(chunk.heading_path),
            "source_filename": chunk.source_filename,
            "source_path": chunk.source_path,
            "source_brand_reference": chunk.source_brand_reference or "",
            "consuming_application_name": chunk.consuming_application_name,
        }
