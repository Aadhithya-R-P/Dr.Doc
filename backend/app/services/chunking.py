"""Paragraph-aware character windows with explicit estimated token accounting."""

from dataclasses import dataclass
from math import ceil

from app.schemas.pdf import ExtractedPage, TextChunk


@dataclass(frozen=True)
class ChunkingOptions:
    target_tokens: int = 500
    overlap_tokens: int = 75

    def __post_init__(self):
        if self.target_tokens <= 0 or not 0 <= self.overlap_tokens < self.target_tokens:
            raise ValueError("Require target_tokens > 0 and 0 <= overlap_tokens < target_tokens.")

    @property
    def version(self) -> str:
        return f"char4-v1-target{self.target_tokens}-overlap{self.overlap_tokens}"


def estimate_tokens(text: str) -> int:
    """A deterministic English-oriented heuristic, not Gemini's tokenizer."""
    return ceil(len(text) / 4)


def chunk_pages(
    pages: tuple[ExtractedPage, ...], options: ChunkingOptions | None = None,
) -> tuple[TextChunk, ...]:
    options = options or ChunkingOptions()
    max_chars, overlap_chars = options.target_tokens * 4, options.overlap_tokens * 4
    text_parts = []
    spans = []
    offset = 0
    previous_page = 0
    for page in pages:
        if page.page_number <= previous_page:
            raise ValueError("Pages must have strictly increasing page numbers.")
        previous_page = page.page_number
        if not page.text.strip():
            continue
        if text_parts:
            text_parts.append("\n\n")
            offset += 2
        start = offset
        text_parts.append(page.text)
        offset += len(page.text)
        spans.append((start, offset, page.page_number))
    text = "".join(text_parts)
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            # Prefer a paragraph, then line/word boundary in the latter half.
            # Always leave more than the overlap so the next window advances.
            lower = start + max(max_chars // 2, overlap_chars + 1)
            for separator in ("\n\n", "\n", " "):
                boundary = text.rfind(separator, lower, end)
                if boundary != -1:
                    end = boundary
                    break
        left, right = start, end
        while left < right and text[left].isspace():
            left += 1
        while right > left and text[right - 1].isspace():
            right -= 1
        if left < right:
            source_pages = [number for a, b, number in spans if a < right and b > left]
            if source_pages:
                passage = text[left:right]
                chunks.append(TextChunk(
                    chunk_index=len(chunks), text=passage,
                    page_start=source_pages[0], page_end=source_pages[-1],
                    token_count=estimate_tokens(passage),
                ))
        if end == len(text):
            break
        start = max(start + 1, end - overlap_chars)
    return tuple(chunks)
