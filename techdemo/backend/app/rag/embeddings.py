"""Mockable OpenAI embedding generation for policy text and customer queries."""

from collections.abc import Sequence
import math
import time
from typing import Protocol

from app.core.config import Settings, get_settings


class EmbeddingGenerationError(RuntimeError):
    """Embedding credentials, validation, or API communication failed."""


class EmbeddingGenerator(Protocol):
    """Minimal interface allowing tests to replace the live OpenAI client."""

    model: str

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class OpenAIEmbeddingGenerator:
    """Generate compatible embeddings through the official OpenAI Python SDK."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: object | None = None,
        max_retries: int = 2,
        retry_delay_seconds: float = 0.5,
    ) -> None:
        configured = settings or get_settings()
        if not configured.openai_api_key:
            raise EmbeddingGenerationError(
                "OPENAI_API_KEY is required for live policy embedding generation."
            )
        self.model = configured.rag_embedding_model
        self._batch_size = configured.rag_embedding_batch_size
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise EmbeddingGenerationError(
                    "The openai package is required for live embedding generation."
                ) from exc
            client = OpenAI(api_key=configured.openai_api_key)
        self._client = client

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed non-empty texts in bounded batches and validate all vectors."""
        if not texts:
            return []
        if any(not text.strip() for text in texts):
            raise EmbeddingGenerationError("Embedding input must not contain empty text.")
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            response = self._request_embeddings(list(texts[start : start + self._batch_size]))
            batch = [list(item.embedding) for item in response.data]
            if len(batch) != len(texts[start : start + self._batch_size]):
                raise EmbeddingGenerationError("Embedding API returned an unexpected vector count.")
            embeddings.extend(batch)
        self._validate_embeddings(embeddings)
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        """Embed one policy query using the same model as document ingestion."""
        if not text.strip():
            raise EmbeddingGenerationError("The retrieval query must not be empty.")
        return self.embed_documents([text])[0]

    def _request_embeddings(self, inputs: list[str]):
        for attempt in range(self._max_retries + 1):
            try:
                return self._client.embeddings.create(model=self.model, input=inputs)
            except Exception as exc:
                if attempt == self._max_retries:
                    raise EmbeddingGenerationError(
                        "OpenAI embedding request failed after bounded retries."
                    ) from exc
                time.sleep(self._retry_delay_seconds * (attempt + 1))
        raise AssertionError("unreachable")

    @staticmethod
    def _validate_embeddings(embeddings: Sequence[Sequence[float]]) -> None:
        if not embeddings:
            return
        dimension = len(embeddings[0])
        if dimension == 0:
            raise EmbeddingGenerationError("Embedding vectors must not be empty.")
        for embedding in embeddings:
            if len(embedding) != dimension:
                raise EmbeddingGenerationError("Embedding vectors have incompatible dimensions.")
            if any(not math.isfinite(float(value)) for value in embedding):
                raise EmbeddingGenerationError("Embedding vectors must contain finite numbers.")
