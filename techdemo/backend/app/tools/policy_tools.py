"""Deterministic lookup of policy documents from trusted local directories."""

from pathlib import Path

from app.schemas.investigation import (
    MissingData,
    PolicyLookupOutcome,
    PolicyLookupResult,
    PolicyReference,
    PolicyTopic,
)
from app.tools.context import CustomerInvestigationContext

_TOPIC_TERMS: dict[PolicyTopic, tuple[str, ...]] = {
    PolicyTopic.RETURN: ("return",),
    PolicyTopic.REFUND: ("refund",),
    PolicyTopic.DAMAGED_ITEM: ("damaged", "damage"),
}


class PolicyLookupTool:
    """Read trusted local Markdown policies without adding policy rules in code."""

    def __init__(self, policy_directories: tuple[Path, ...] | None = None) -> None:
        project_root = Path(__file__).resolve().parents[3]
        self._project_root = project_root
        self._policy_directories = policy_directories or (
            project_root / "policies",
            project_root / "docs",
        )

    def lookup(
        self,
        topic: PolicyTopic,
        context: CustomerInvestigationContext,
    ) -> PolicyLookupResult:
        """Return verbatim matching policy documents for a permitted topic.

        The trusted context keeps this interface consistent with customer-scoped
        tools. Policy lookup does not use its identity because it reads only
        static, trusted project documents.
        """
        del context  # The context is intentionally not an LLM-provided argument.
        matches = self._matching_documents(topic)
        if not matches:
            return PolicyLookupResult(
                topic=topic,
                outcome=PolicyLookupOutcome.NOT_FOUND,
                missing_data=[
                    MissingData(
                        field=f"policy:{topic.value}",
                        reason="No documented policy source was found for this topic.",
                    )
                ],
            )

        references = [
            PolicyReference(topic=topic, source=source, text=document)
            for source, document in matches
        ]
        if len(references) > 1:
            return PolicyLookupResult(
                topic=topic,
                outcome=PolicyLookupOutcome.AMBIGUOUS,
                policies=references,
                missing_data=[
                    MissingData(
                        field=f"policy:{topic.value}",
                        reason="Multiple documented policy sources matched this topic.",
                    )
                ],
            )

        return PolicyLookupResult(
            topic=topic,
            outcome=PolicyLookupOutcome.FOUND,
            policies=references,
        )

    def _matching_documents(self, topic: PolicyTopic) -> list[tuple[str, str]]:
        terms = _TOPIC_TERMS[topic]
        matches: list[tuple[str, str]] = []
        for directory in self._policy_directories:
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*.md")):
                document = path.read_text(encoding="utf-8").strip()
                searchable = f"{path.name}\n{document}".casefold()
                if document and any(term in searchable for term in terms):
                    matches.append((self._source_name(path), document))
        return matches

    def _source_name(self, path: Path) -> str:
        try:
            return path.relative_to(self._project_root).as_posix()
        except ValueError:
            return path.name
