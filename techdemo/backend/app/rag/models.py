"""Typed contracts shared by the policy RAG pipeline."""

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class LoadedPolicyDocument(BaseModel):
    """An authoritative policy Markdown document, preserved verbatim."""

    model_config = ConfigDict(frozen=True)

    policy_id: str | None
    title: str | None
    policy_version: str | None
    effective_date: date | None
    text: str = Field(min_length=1)
    source_filename: str
    source_path: str
    content_hash: str
    missing_metadata: tuple[str, ...] = ()
    source_brand_reference: str | None = None
    consuming_application_name: str = "TechDemo"
    naming_note: str | None = None


class PolicyChunk(BaseModel):
    """A deterministic, independently retrievable section of a policy document."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    policy_id: str | None
    document_title: str | None
    policy_version: str | None
    effective_date: date | None
    section_heading: str
    heading_path: tuple[str, ...]
    source_filename: str
    source_path: str
    text: str = Field(min_length=1)
    content_hash: str
    source_brand_reference: str | None = None
    consuming_application_name: str = "TechDemo"


class IngestionSummary(BaseModel):
    """A concise, non-sensitive record of one policy-index ingestion run."""

    documents: int
    chunks: int
    new_chunks: int
    unchanged_chunks: int
    removed_chunks: int
    embedding_model: str
    embedding_dimension: int | None


class RetrievalStatus(str, Enum):
    """Outcome of semantic retrieval without interpreting policy evidence."""

    FOUND = "FOUND"
    NO_EVIDENCE = "NO_EVIDENCE"


class RetrievedPolicyPassage(BaseModel):
    """One source-backed policy passage returned by vector similarity search."""

    policy_id: str | None
    document_title: str | None
    policy_version: str | None
    effective_date: date | None
    section_heading: str
    heading_path: tuple[str, ...]
    source_filename: str
    source_path: str
    text: str
    distance: float


class PolicyRetrievalResult(BaseModel):
    """A structured semantic search result suitable for future tool calling."""

    query: str
    status: RetrievalStatus
    passages: list[RetrievedPolicyPassage] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
