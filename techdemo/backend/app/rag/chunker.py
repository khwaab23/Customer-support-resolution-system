"""Deterministic, section-aware chunking for authoritative Markdown policies."""

from dataclasses import dataclass
from hashlib import sha256
import re

from app.rag.models import LoadedPolicyDocument, PolicyChunk

_HEADING_PATTERN = re.compile(r"^(?P<markers>#{1,6})\s+(?P<heading>.+?)\s*$")


@dataclass(frozen=True)
class _Section:
    heading: str
    heading_path: tuple[str, ...]
    body: str


class PolicyChunker:
    """Chunk whole Markdown sections, splitting only unusually large sections.

    The default 1,800-character size keeps the short policy sections intact.
    When a section is larger, splitting occurs at paragraph boundaries and only
    then uses the configured overlap to retain local context.
    """

    def __init__(self, chunk_size: int = 1800, overlap: int = 200) -> None:
        if chunk_size < 256:
            raise ValueError("chunk_size must be at least 256 characters")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap must be non-negative and smaller than chunk_size")
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk_document(self, document: LoadedPolicyDocument) -> list[PolicyChunk]:
        """Return stable chunks for each non-empty Markdown section."""
        chunks: list[PolicyChunk] = []
        seen_hashes: set[str] = set()
        for section in self._sections(document.text):
            for part_index, part in enumerate(self._split_section(section)):
                content_hash = sha256(part.encode("utf-8")).hexdigest()
                if content_hash in seen_hashes:
                    continue
                seen_hashes.add(content_hash)
                identity = "|".join(
                    (
                        document.policy_id or "missing-policy-id",
                        document.source_path,
                        ">".join(section.heading_path),
                        str(part_index),
                        content_hash,
                    )
                )
                chunks.append(
                    PolicyChunk(
                        chunk_id=sha256(identity.encode("utf-8")).hexdigest(),
                        policy_id=document.policy_id,
                        document_title=document.title,
                        policy_version=document.policy_version,
                        effective_date=document.effective_date,
                        section_heading=section.heading,
                        heading_path=section.heading_path,
                        source_filename=document.source_filename,
                        source_path=document.source_path,
                        text=part,
                        content_hash=content_hash,
                        source_brand_reference=document.source_brand_reference,
                    )
                )
        return chunks

    def chunk_documents(self, documents: list[LoadedPolicyDocument]) -> list[PolicyChunk]:
        """Chunk a document set, rejecting duplicate deterministic chunk IDs."""
        chunks = [chunk for document in documents for chunk in self.chunk_document(document)]
        if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
            raise ValueError("Duplicate chunk IDs were generated.")
        return chunks

    def _sections(self, text: str) -> list[_Section]:
        hierarchy: list[tuple[int, str]] = []
        sections: list[_Section] = []
        current_heading: str | None = None
        current_path: tuple[str, ...] = ()
        body_lines: list[str] = []

        def finish_current() -> None:
            if current_heading is None:
                return
            body = "\n".join(body_lines).strip()
            if body:
                sections.append(_Section(current_heading, current_path, body))

        for line in text.splitlines():
            match = _HEADING_PATTERN.match(line)
            if match is None:
                if current_heading is not None:
                    body_lines.append(line)
                continue
            finish_current()
            level = len(match.group("markers"))
            heading = match.group("heading").strip()
            if level == 1 and not hierarchy:
                # The document title and its metadata preamble remain document
                # metadata. Retrieval begins at meaningful policy sections.
                hierarchy = [(level, heading)]
                current_heading = None
                current_path = ()
                body_lines = []
                continue
            hierarchy = [item for item in hierarchy if item[0] < level]
            hierarchy.append((level, heading))
            current_heading = heading
            current_path = tuple(item[1] for item in hierarchy)
            body_lines = []
        finish_current()
        return sections

    def _split_section(self, section: _Section) -> list[str]:
        heading_prefix = f"{' > '.join(section.heading_path)}\n\n"
        available = self._chunk_size - len(heading_prefix)
        if available <= 0:
            raise ValueError("chunk_size is too small for a policy heading path")
        if len(section.body) <= available:
            return [heading_prefix + section.body]

        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", section.body) if part.strip()]
        pieces: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) > available:
                if current:
                    pieces.append(current)
                    current = ""
                pieces.extend(self._split_long_text(paragraph, available))
                continue
            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if len(candidate) <= available:
                current = candidate
            else:
                pieces.append(current)
                current = paragraph
        if current:
            pieces.append(current)
        return [heading_prefix + piece for piece in pieces]

    def _split_long_text(self, text: str, limit: int) -> list[str]:
        pieces: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + limit)
            if end < len(text):
                boundary = text.rfind(" ", start, end)
                if boundary > start:
                    end = boundary
            pieces.append(text[start:end].strip())
            if end >= len(text):
                break
            start = max(end - self._overlap, start + 1)
        return pieces
