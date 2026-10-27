from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.rag.chunker import PolicyChunker
from app.rag.document_loader import PolicyDocumentError, PolicyDocumentLoader
from app.rag.embeddings import EmbeddingGenerationError, OpenAIEmbeddingGenerator
from app.rag.models import LoadedPolicyDocument, PolicyChunk, RetrievalStatus
from app.rag.retriever import PolicyRetriever
from app.rag.vector_store import (
    ChromaPolicyVectorStore,
    IncompatibleEmbeddingConfigurationError,
)
from app.schemas.investigation import PolicyLookupOutcome, PolicyTopic
from app.tools.context import CustomerInvestigationContext
from app.tools.policy_tools import PolicyLookupTool


class FakeEmbeddings:
    model = "test-embedding-v1"

    def embed_documents(self, texts):
        return [self._embed(text) for text in texts]

    def embed_query(self, text):
        return self._embed(text)

    @staticmethod
    def _embed(text):
        lowered = text.casefold()
        return [
            1.0 if "return" in lowered else 0.0,
            1.0 if "refund" in lowered else 0.0,
            1.0 if "damage" in lowered else 0.0,
        ]


def make_document(text: str, *, effective_date: date | None = date(2026, 10, 1)) -> LoadedPolicyDocument:
    return LoadedPolicyDocument(
        policy_id="NTE-POL-TEST",
        title="Test Policy",
        policy_version="1.0",
        effective_date=effective_date,
        text=text,
        source_filename="test_policy.md",
        source_path="policies/test_policy.md",
        content_hash="document-hash",
    )


def test_loader_discovers_authoritative_policy_metadata() -> None:
    documents = PolicyDocumentLoader().load_all()

    assert len(documents) == 5
    assert {document.policy_id for document in documents} == {
        "NTE-POL-01",
        "NTE-POL-02",
        "NTE-POL-03",
        "NTE-POL-04",
        "NTE-POL-05",
    }
    assert all(document.policy_version == "1.0" for document in documents)
    assert all(document.effective_date == date(2026, 10, 1) for document in documents)
    assert all(document.source_brand_reference == "NovaTech" for document in documents)
    assert any("NovaTech" in document.text for document in documents)


def test_loader_rejects_empty_unsupported_and_invalid_documents(tmp_path: Path) -> None:
    loader = PolicyDocumentLoader(tmp_path)
    empty = tmp_path / "empty.md"
    empty.write_text("\n", encoding="utf-8")
    unsupported = tmp_path / "policy.txt"
    unsupported.write_text("policy", encoding="utf-8")
    invalid_date = tmp_path / "invalid.md"
    invalid_date.write_text(
        "# Test\n\nPolicy ID: X | Version: 1.0 | Effective: never\n",
        encoding="utf-8",
    )

    with pytest.raises(PolicyDocumentError):
        loader.load_file(empty)
    with pytest.raises(PolicyDocumentError):
        loader.load_file(unsupported)
    with pytest.raises(PolicyDocumentError):
        loader.load_file(invalid_date)

    missing_metadata = tmp_path / "missing.md"
    missing_metadata.write_text("# Untagged Policy\n\n## Rule\n\nEvidence.", encoding="utf-8")
    loaded = loader.load_file(missing_metadata)
    assert loaded.missing_metadata == ("policy_id", "policy_version", "effective_date")


def test_chunker_preserves_heading_paths_and_stable_ids() -> None:
    document = make_document(
        "# Test Policy\n\nPolicy ID: NTE-POL-TEST | Version: 1.0 | Effective: 2026-10-01\n\n"
        "## Rule\n\nKeep this rule and its exception together.\n\n"
        "### Exception\n\nThis is the exception.\n"
    )
    chunker = PolicyChunker(chunk_size=256, overlap=20)

    first = chunker.chunk_document(document)
    second = chunker.chunk_document(document)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert first[0].heading_path == ("Test Policy", "Rule")
    assert first[1].heading_path == ("Test Policy", "Rule", "Exception")
    assert "Keep this rule" in first[0].text


def test_chunker_splits_oversized_sections_without_empty_or_duplicate_chunks() -> None:
    paragraphs = "\n\n".join(f"Paragraph {index} has a policy condition." for index in range(20))
    chunks = PolicyChunker(chunk_size=300, overlap=30).chunk_document(
        make_document(f"# Test Policy\n\n## Large section\n\n{paragraphs}")
    )

    assert len(chunks) > 1
    assert all(chunk.text.strip() for chunk in chunks)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


def test_openai_embedding_generator_batches_and_validates_vectors() -> None:
    calls = []

    class Client:
        class embeddings:
            @staticmethod
            def create(*, model, input):
                calls.append((model, input))
                return SimpleNamespace(
                    data=[SimpleNamespace(embedding=[1.0, 0.0]) for _ in input]
                )

    settings = SimpleNamespace(
        openai_api_key="test-key",
        rag_embedding_model="test-model",
        rag_embedding_batch_size=2,
    )
    generator = OpenAIEmbeddingGenerator(settings, client=Client())

    assert generator.embed_documents(["one", "two", "three"]) == [
        [1.0, 0.0],
        [1.0, 0.0],
        [1.0, 0.0],
    ]
    assert len(calls) == 2

    with pytest.raises(EmbeddingGenerationError):
        generator._validate_embeddings([[1.0], [float("nan")]])

    class FailingClient:
        class embeddings:
            @staticmethod
            def create(*, model, input):
                raise TimeoutError("simulated timeout")

    with pytest.raises(EmbeddingGenerationError):
        OpenAIEmbeddingGenerator(
            settings,
            client=FailingClient(),
            max_retries=0,
        ).embed_query("return policy")


def test_chroma_store_is_idempotent_handles_updates_and_rejects_incompatible_config(
    tmp_path: Path,
) -> None:
    document = make_document("# Test Policy\n\n## Returns\n\nReturn policy evidence.")
    chunks = PolicyChunker().chunk_document(document)
    store = ChromaPolicyVectorStore(tmp_path / "chroma", "policy-test")
    vectors = {chunk.chunk_id: [1.0, 0.0, 0.0] for chunk in chunks}

    upserted, removed = store.synchronize(
        chunks,
        vectors,
        embedding_model="test-embedding-v1",
        embedding_dimension=3,
    )
    assert (upserted, removed) == (len(chunks), 0)
    assert store.synchronize(
        chunks,
        {},
        embedding_model="test-embedding-v1",
        embedding_dimension=3,
    ) == (0, 0)
    updated_chunks = PolicyChunker().chunk_document(
        make_document("# Test Policy\n\n## Returns\n\nUpdated return policy evidence.")
    )
    assert store.synchronize(
        updated_chunks,
        {chunk.chunk_id: [1.0, 0.0, 0.0] for chunk in updated_chunks},
        embedding_model="test-embedding-v1",
        embedding_dimension=3,
    ) == (len(updated_chunks), len(chunks))
    assert store.synchronize(
        [],
        {},
        embedding_model="test-embedding-v1",
        embedding_dimension=3,
    ) == (0, len(chunks))

    with pytest.raises(IncompatibleEmbeddingConfigurationError):
        store.synchronize(
            chunks,
            vectors,
            embedding_model="different-model",
            embedding_dimension=3,
        )


def test_retriever_preserves_citations_and_filters_future_and_low_relevance(tmp_path: Path) -> None:
    document = make_document("# Test Policy\n\n## Returns\n\nReturn policy evidence.")
    future_document = make_document(
        "# Test Policy\n\n## Future\n\nFuture return policy.",
        effective_date=date(2099, 1, 1),
    ).model_copy(update={"source_filename": "future.md", "source_path": "policies/future.md"})
    chunks = PolicyChunker().chunk_documents([document, future_document])
    store = ChromaPolicyVectorStore(tmp_path / "chroma", "retrieve-test")
    store.synchronize(
        chunks,
        {chunk.chunk_id: FakeEmbeddings().embed_query(chunk.text) for chunk in chunks},
        embedding_model=FakeEmbeddings.model,
        embedding_dimension=3,
    )
    retriever = PolicyRetriever(FakeEmbeddings(), store, distance_threshold=0.5)

    result = retriever.retrieve_policy_evidence("return policy", as_of_date=date(2026, 10, 26))

    assert result.status is RetrievalStatus.FOUND
    assert result.passages[0].source_path == "policies/test_policy.md"
    assert all(passage.effective_date != date(2099, 1, 1) for passage in result.passages)
    assert retriever.retrieve_policy_evidence("refund policy").status is RetrievalStatus.NO_EVIDENCE


def test_policy_lookup_tool_uses_retrieval_evidence() -> None:
    class Retriever:
        def retrieve_policy_evidence(self, query):
            from app.rag.models import PolicyRetrievalResult, RetrievedPolicyPassage

            return PolicyRetrievalResult(
                query=query,
                status=RetrievalStatus.FOUND,
                passages=[
                    RetrievedPolicyPassage(
                        policy_id="NTE-POL-01",
                        document_title="Returns & Eligibility",
                        policy_version="1.0",
                        effective_date=date(2026, 10, 1),
                        section_heading="Standard window",
                        heading_path=("Returns & Eligibility", "Standard window"),
                        source_filename="returns_and_eligibility.md",
                        source_path="policies/returns_and_eligibility.md",
                        text="A customer may request a standard return within 30 calendar days.",
                        distance=0.1,
                    )
                ],
            )

    result = PolicyLookupTool(Retriever()).lookup(
        PolicyTopic.RETURN,
        CustomerInvestigationContext(customer_id="CUST-001"),
    )

    assert result.outcome is PolicyLookupOutcome.FOUND
    assert result.policies[0].source == "policies/returns_and_eligibility.md"
