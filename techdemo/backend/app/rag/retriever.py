"""Semantic policy retrieval without interpreting evidence as a business decision."""

from datetime import date
import json
from pathlib import Path

from app.core.config import Settings, get_settings
from app.rag.embeddings import EmbeddingGenerator
from app.rag.models import (
    PolicyRetrievalResult,
    RetrievedPolicyPassage,
    RetrievalStatus,
)
from app.rag.vector_store import ChromaPolicyVectorStore


class PolicyRetriever:
    """Retrieve source-backed applicable policy chunks from the local Chroma index."""

    def __init__(
        self,
        embedding_generator: EmbeddingGenerator,
        vector_store: ChromaPolicyVectorStore,
        *,
        default_top_k: int = 5,
        distance_threshold: float | None = None,
    ) -> None:
        self._embeddings = embedding_generator
        self._store = vector_store
        self._default_top_k = default_top_k
        self._distance_threshold = distance_threshold

    @classmethod
    def from_settings(
        cls,
        embedding_generator: EmbeddingGenerator,
        settings: Settings | None = None,
    ) -> "PolicyRetriever":
        configured = settings or get_settings()
        return cls(
            embedding_generator,
            ChromaPolicyVectorStore(
                Path(configured.rag_persist_directory),
                configured.rag_collection_name,
            ),
            default_top_k=configured.rag_retrieval_top_k,
            distance_threshold=configured.rag_distance_threshold,
        )

    def retrieve_policy_evidence(
        self,
        query: str,
        top_k: int | None = None,
        as_of_date: date | None = None,
    ) -> PolicyRetrievalResult:
        """Return relevant, applicable passages or an explicit no-evidence result."""
        cleaned_query = query.strip()
        if not cleaned_query or len(cleaned_query) > 2_000:
            raise ValueError("Retrieval query must contain 1 to 2,000 characters.")
        requested_count = top_k if top_k is not None else self._default_top_k
        if not 1 <= requested_count <= 20:
            raise ValueError("top_k must be between 1 and 20.")

        query_embedding = self._embeddings.embed_query(cleaned_query)
        records = self._store.search(query_embedding, requested_count)
        applicable_date = as_of_date or date.today()
        passages: list[RetrievedPolicyPassage] = []
        missing_information: list[str] = []
        for record in records:
            metadata = record["metadata"]
            assert isinstance(metadata, dict)
            effective_date = self._effective_date(metadata, missing_information)
            if effective_date is not None and effective_date > applicable_date:
                continue
            distance = float(record["distance"])
            if self._distance_threshold is not None and distance > self._distance_threshold:
                continue
            passages.append(
                RetrievedPolicyPassage(
                    policy_id=self._none_if_empty(metadata.get("policy_id")),
                    document_title=self._none_if_empty(metadata.get("document_title")),
                    policy_version=self._none_if_empty(metadata.get("policy_version")),
                    effective_date=effective_date,
                    section_heading=str(metadata["section_heading"]),
                    heading_path=tuple(json.loads(str(metadata["heading_path"]))),
                    source_filename=str(metadata["source_filename"]),
                    source_path=str(metadata["source_path"]),
                    text=str(record["text"]),
                    distance=distance,
                )
            )

        if not passages:
            return PolicyRetrievalResult(
                query=cleaned_query,
                status=RetrievalStatus.NO_EVIDENCE,
                missing_information=[
                    *missing_information,
                    "No applicable policy evidence met the retrieval criteria.",
                ],
            )
        if len({(item.policy_id, item.policy_version) for item in passages}) > 1:
            missing_information.append(
                "Multiple policy versions or documents were retrieved; applicability requires review."
            )
        return PolicyRetrievalResult(
            query=cleaned_query,
            status=RetrievalStatus.FOUND,
            passages=passages,
            missing_information=missing_information,
        )

    @staticmethod
    def _effective_date(metadata: dict[str, object], missing: list[str]) -> date | None:
        raw_value = str(metadata.get("effective_date", "")).strip()
        if not raw_value:
            missing.append("A retrieved policy passage has no effective date metadata.")
            return None
        try:
            return date.fromisoformat(raw_value)
        except ValueError:
            missing.append("A retrieved policy passage has an invalid effective date metadata value.")
            return None

    @staticmethod
    def _none_if_empty(value: object) -> str | None:
        cleaned = str(value).strip()
        return cleaned or None
