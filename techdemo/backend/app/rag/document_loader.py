"""Loading and metadata validation for trusted local Markdown policy sources."""

from datetime import date
from hashlib import sha256
from pathlib import Path
import re

from app.rag.models import LoadedPolicyDocument

_TITLE_PATTERN = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_METADATA_PATTERN = re.compile(
    r"^Policy ID:\s*(?P<policy_id>[^|\n]+?)\s*\|\s*"
    r"Version:\s*(?P<version>[^|\n]+?)\s*\|\s*"
    r"Effective:\s*(?P<effective>[^\n]+?)\s*$",
    re.MULTILINE,
)


class PolicyDocumentError(ValueError):
    """A local policy source is unreadable, unsupported, or structurally invalid."""


def default_policy_directory() -> Path:
    """Return the repository policy directory without relying on a user path."""
    return Path(__file__).resolve().parents[3] / "policies"


class PolicyDocumentLoader:
    """Load authoritative UTF-8 Markdown policies without changing their text."""

    def __init__(self, policy_directory: Path | None = None) -> None:
        self._policy_directory = policy_directory or default_policy_directory()
        self._project_root = Path(__file__).resolve().parents[3]

    def load_all(self) -> list[LoadedPolicyDocument]:
        """Load all Markdown policies, rejecting duplicate documented policy IDs."""
        if not self._policy_directory.is_dir():
            raise PolicyDocumentError(
                f"Policy directory does not exist: {self._policy_directory.name}"
            )

        documents = [self.load_file(path) for path in sorted(self._policy_directory.glob("*.md"))]
        if not documents:
            raise PolicyDocumentError("No Markdown policy documents were found.")

        seen_ids: set[str] = set()
        seen_hashes: set[str] = set()
        for document in documents:
            if document.policy_id is not None:
                if document.policy_id in seen_ids:
                    raise PolicyDocumentError(
                        f"Duplicate policy ID: {document.policy_id}"
                    )
                seen_ids.add(document.policy_id)
            if document.content_hash in seen_hashes:
                raise PolicyDocumentError(
                    f"Duplicate policy content: {document.source_filename}"
                )
            seen_hashes.add(document.content_hash)
        return documents

    def load_file(self, path: Path) -> LoadedPolicyDocument:
        """Load one UTF-8 Markdown policy and record missing metadata explicitly."""
        if path.suffix.lower() != ".md":
            raise PolicyDocumentError(f"Unsupported policy format: {path.name}")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise PolicyDocumentError(f"Could not read policy document: {path.name}") from exc
        if not text.strip():
            raise PolicyDocumentError(f"Policy document is empty: {path.name}")

        title_match = _TITLE_PATTERN.search(text)
        metadata_match = _METADATA_PATTERN.search(text)
        title = title_match.group(1).strip() if title_match else None
        policy_id = metadata_match.group("policy_id").strip() if metadata_match else None
        version = metadata_match.group("version").strip() if metadata_match else None
        effective_date = self._parse_effective_date(metadata_match, path.name)
        missing = tuple(
            field
            for field, value in (
                ("title", title),
                ("policy_id", policy_id),
                ("policy_version", version),
                ("effective_date", effective_date),
            )
            if value is None
        )
        # The supplied authoritative corpus is NovaTech material. Some documents
        # state that name directly; the remaining NTE-* policy IDs identify the
        # same source corpus without rewriting any source wording.
        source_brand = (
            "NovaTech"
            if "NovaTech" in text or (policy_id is not None and policy_id.startswith("NTE-"))
            else None
        )
        naming_note = (
            "Source document references NovaTech; it is consumed by TechDemo."
            if source_brand is not None
            else None
        )
        return LoadedPolicyDocument(
            policy_id=policy_id,
            title=title,
            policy_version=version,
            effective_date=effective_date,
            text=text,
            source_filename=path.name,
            source_path=self._relative_source_path(path),
            content_hash=sha256(text.encode("utf-8")).hexdigest(),
            missing_metadata=missing,
            source_brand_reference=source_brand,
            naming_note=naming_note,
        )

    @staticmethod
    def _parse_effective_date(
        metadata_match: re.Match[str] | None,
        source_filename: str,
    ) -> date | None:
        if metadata_match is None:
            return None
        raw_value = metadata_match.group("effective").strip()
        try:
            return date.fromisoformat(raw_value)
        except ValueError as exc:
            raise PolicyDocumentError(
                f"Invalid effective date in policy document: {source_filename}"
            ) from exc

    def _relative_source_path(self, path: Path) -> str:
        try:
            return path.relative_to(self._project_root).as_posix()
        except ValueError:
            return path.name
