"""Bounded text-only PDF validation and page-by-page extraction."""

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import re

from pypdf import PdfReader, apply_configuration
from pypdf.errors import LimitReachedError

from app.schemas.pdf import ExtractedPage, ExtractedPdf


class PdfValidationError(ValueError):
    """Safe, stable error code and message for eventual API error mapping."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PdfLimits:
    max_bytes: int = 5 * 1024 * 1024
    max_pages: int = 30
    max_text_characters: int = 200_000
    max_page_stream_bytes: int = 2 * 1024 * 1024
    max_total_stream_bytes: int = 8 * 1024 * 1024

    def __post_init__(self):
        if min(
            self.max_bytes, self.max_pages, self.max_text_characters,
            self.max_page_stream_bytes, self.max_total_stream_bytes,
        ) <= 0:
            raise ValueError("PDF limits must be positive.")


def normalize_page_text(text: str) -> str:
    # Keep line/paragraph boundaries; avoid guessing reading order or dehyphenation.
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def extract_pdf(
    data: bytes, filename: str, content_type: str, limits: PdfLimits | None = None,
) -> ExtractedPdf:
    limits = limits or PdfLimits()
    filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not filename or len(filename) > 255 or any(ord(char) < 32 for char in filename):
        raise PdfValidationError("invalid_filename", "Provide a PDF filename of at most 255 characters.")
    if not filename.lower().endswith(".pdf") or content_type != "application/pdf":
        raise PdfValidationError("unsupported_file_type", "Only application/pdf files with a .pdf filename are supported.")
    if not data:
        raise PdfValidationError("empty_file", "The uploaded file is empty.")
    if len(data) > limits.max_bytes:
        raise PdfValidationError("file_too_large", f"PDF exceeds the {limits.max_bytes}-byte upload limit.")
    if not data.startswith(b"%PDF-"):
        raise PdfValidationError("invalid_pdf", "The file does not have a valid PDF header.")

    try:
        # Context-local parser budgets, not global settings shared by concurrent requests.
        with apply_configuration(
            maximum_declared_stream_length=limits.max_bytes,
            zlib_maximum_output_length=limits.max_page_stream_bytes,
            lzw_maximum_output_length=limits.max_page_stream_bytes,
            run_length_maximum_output_length=limits.max_page_stream_bytes,
            array_based_stream_maximum_output_length=limits.max_page_stream_bytes,
            stream_decoding_work_maximum_length=limits.max_total_stream_bytes,
            stream_parsing_work_maximum_count=200_000,
            page_tree_maximum_entries=1000,
            page_tree_maximum_depth=30,
        ):
            with PdfReader(BytesIO(data), strict=True) as reader:
                if reader.is_encrypted:
                    raise PdfValidationError("encrypted_pdf", "Encrypted PDFs are not supported. Upload an unencrypted copy.")
                page_count = len(reader.pages)
                if not 1 <= page_count <= limits.max_pages:
                    raise PdfValidationError("page_limit", f"PDF must contain 1 to {limits.max_pages} pages.")
                pages = []
                warnings = []
                total_text = 0
                total_stream = 0
                for number, page in enumerate(reader.pages, start=1):
                    content = page.get_contents()
                    stream_size = len(content.get_data()) if content is not None else 0
                    total_stream += stream_size
                    if stream_size > limits.max_page_stream_bytes or total_stream > limits.max_total_stream_bytes:
                        raise PdfValidationError("content_limit", "PDF content streams exceed the processing limit.")
                    raw_text = page.extract_text() or ""
                    total_text += len(raw_text)
                    if total_text > limits.max_text_characters:
                        raise PdfValidationError("text_limit", "PDF exceeds the extracted-text character limit.")
                    text = normalize_page_text(raw_text)
                    if not any(char.isalnum() for char in text):
                        # Listing image IDs does not decode image pixels or perform OCR.
                        if len(page.images):
                            raise PdfValidationError(
                                "image_only_page",
                                f"Page {number} is image-only with no readable text. OCR is not supported.",
                            )
                        warnings.append(f"Page {number} has no readable text and was omitted from chunks.")
                        text = ""
                    pages.append(ExtractedPage(page_number=number, text=text))
                characters = sum(len(page.text) for page in pages)
                if not characters:
                    raise PdfValidationError(
                        "no_extractable_text",
                        "PDF has no readable text. Scanned/image-only PDFs require OCR, which is not supported.",
                    )
                return ExtractedPdf(
                    filename=filename, content_hash=sha256(data).hexdigest(), page_count=page_count,
                    extracted_characters=characters, pages=tuple(pages), warnings=tuple(warnings),
                )
    except PdfValidationError:
        raise
    except LimitReachedError:
        raise PdfValidationError("content_limit", "PDF exceeds the parser's processing limits.") from None
    except Exception:
        # Do not expose parser traces, PDF contents or object values to API callers.
        raise PdfValidationError("invalid_pdf", "PDF could not be parsed and its text extracted.") from None
