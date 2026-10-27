"""Verify source-backed semantic retrieval from the already ingested policy index."""

import sys

from app.core.config import get_settings
from app.rag.embeddings import EmbeddingGenerationError, OpenAIEmbeddingGenerator
from app.rag.retriever import PolicyRetriever
from app.rag.vector_store import VectorStoreError

_QUERIES = (
    "What is the standard return window?",
    "How should a damaged product be handled?",
    "What evidence is available for a shipment delay?",
    "How are refunds handled after a return?",
    "When is human review and escalation required?",
)


def main() -> int:
    """Run representative non-sensitive policy queries and validate citations."""
    try:
        settings = get_settings()
        retriever = PolicyRetriever.from_settings(OpenAIEmbeddingGenerator(settings), settings)
        for query in _QUERIES:
            result = retriever.retrieve_policy_evidence(query)
            print(f"Query: {query}")
            if not result.passages:
                print("  NO EVIDENCE:", "; ".join(result.missing_information))
                continue
            for passage in result.passages:
                if not all(
                    (
                        passage.source_path,
                        passage.source_filename,
                        passage.section_heading,
                        passage.text,
                    )
                ):
                    print("FAIL: Retrieved citation metadata is incomplete.", file=sys.stderr)
                    return 1
                print(
                    "  MATCH:"
                    f" {passage.policy_id or 'missing ID'}"
                    f" v{passage.policy_version or 'missing version'}"
                    f" — {passage.source_path} / {passage.section_heading}"
                )
        print("PASS: Policy retrieval verification completed.")
        return 0
    except (EmbeddingGenerationError, VectorStoreError, ValueError) as exc:
        print(f"FAIL: Policy retrieval verification unavailable: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
