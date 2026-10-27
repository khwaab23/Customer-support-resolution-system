"""Trusted policy lookup backed by the local semantic retrieval index."""

from app.rag.embeddings import EmbeddingGenerationError, OpenAIEmbeddingGenerator
from app.rag.retriever import PolicyRetriever
from app.rag.models import RetrievalStatus
from app.rag.vector_store import VectorStoreError
from app.schemas.investigation import (
    MissingData,
    PolicyLookupOutcome,
    PolicyLookupResult,
    PolicyReference,
    PolicyTopic,
)
from app.tools.context import CustomerInvestigationContext

_TOPIC_QUERIES: dict[PolicyTopic, str] = {
    PolicyTopic.RETURN: "return eligibility standard window inspection exceptions",
    PolicyTopic.REFUND: "refund payment handling approval execution and verification",
    PolicyTopic.DAMAGED_ITEM: "damaged product evidence assessment resolution escalation",
}

# This is an explicit policy taxonomy for the current controlled document set.
# Semantic search ranks passages; it does not itself prove a passage governs a
# particular decision type. Update this mapping when the approved policy set
# changes rather than allowing cross-topic citations by similarity alone.
_TOPIC_POLICY_IDS: dict[PolicyTopic, frozenset[str]] = {
    PolicyTopic.RETURN: frozenset({"NTE-POL-01"}),
    PolicyTopic.REFUND: frozenset({"NTE-POL-02"}),
    PolicyTopic.DAMAGED_ITEM: frozenset({"NTE-POL-04"}),
}


class PolicyLookupTool:
    """Retrieve source-backed policy passages without adding policy rules in code."""

    def __init__(self, retriever: PolicyRetriever | None = None) -> None:
        self._retriever = retriever

    def lookup(
        self,
        topic: PolicyTopic,
        context: CustomerInvestigationContext,
    ) -> PolicyLookupResult:
        """Return semantic source passages for a permitted policy topic.

        The trusted context keeps this interface consistent with customer-scoped
        tools. Policy lookup does not use its identity because it reads only
        static, trusted project documents.
        """
        del context  # The context is intentionally not an LLM-provided argument.
        try:
            result = self._get_retriever().retrieve_policy_evidence(_TOPIC_QUERIES[topic])
        except (EmbeddingGenerationError, VectorStoreError) as exc:
            return PolicyLookupResult(
                topic=topic,
                outcome=PolicyLookupOutcome.NOT_FOUND,
                missing_data=[
                    MissingData(
                        field=f"policy:{topic.value}",
                        reason=f"Policy retrieval is unavailable: {exc}",
                    )
                ],
            )
        references = [
            PolicyReference(
                topic=topic,
                source=passage.source_path,
                text=passage.text,
                policy_id=passage.policy_id,
                document_title=passage.document_title,
                policy_version=passage.policy_version,
                effective_date=passage.effective_date,
                section_heading=passage.section_heading,
            )
            for passage in result.passages
            if passage.policy_id in _TOPIC_POLICY_IDS[topic]
        ]
        if result.status is RetrievalStatus.NO_EVIDENCE or not references:
            return PolicyLookupResult(
                topic=topic,
                outcome=PolicyLookupOutcome.NOT_FOUND,
                missing_data=[
                    MissingData(
                        field=f"policy:{topic.value}",
                        reason=(
                            "; ".join(result.missing_information)
                            or "No applicable policy evidence was retrieved."
                        ),
                    )
                ],
            )
        if any("Multiple policy versions" in item for item in result.missing_information):
            return PolicyLookupResult(
                topic=topic,
                outcome=PolicyLookupOutcome.AMBIGUOUS,
                policies=references,
                missing_data=[
                    MissingData(
                        field=f"policy:{topic.value}",
                        reason="Multiple policy documents or versions require review.",
                    )
                ],
            )
        return PolicyLookupResult(
            topic=topic,
            outcome=PolicyLookupOutcome.FOUND,
            policies=references,
        )

    def _get_retriever(self) -> PolicyRetriever:
        if self._retriever is None:
            self._retriever = PolicyRetriever.from_settings(OpenAIEmbeddingGenerator())
        return self._retriever
