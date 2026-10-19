"""Compose extraction and chunking without model calls or database writes."""

from app.schemas.pdf import PreparedPdf
from app.services.chunking import ChunkingOptions, chunk_pages
from app.services.pdf_extraction import PdfLimits, extract_pdf


def prepare_pdf(
    data: bytes, filename: str, content_type: str = "application/pdf",
    limits: PdfLimits | None = None, options: ChunkingOptions | None = None,
) -> PreparedPdf:
    options = options or ChunkingOptions()
    document = extract_pdf(data, filename, content_type, limits)
    return PreparedPdf(
        document=document, chunks=chunk_pages(document.pages, options),
        chunking_version=options.version,
    )
