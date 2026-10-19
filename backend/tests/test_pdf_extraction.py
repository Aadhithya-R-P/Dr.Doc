from dataclasses import replace
from hashlib import sha256

import pytest

from app.services.pdf_extraction import PdfLimits, PdfValidationError, extract_pdf
from pdf_fixtures import make_pdf


def test_extracts_pages_hash_and_safe_filename():
    data = make_pdf(["Redis caches results.", "PostgreSQL stores records."])
    result = extract_pdf(data, "C:\\uploads\\architecture.PDF", "application/pdf")
    assert result.filename == "architecture.PDF"
    assert result.content_hash == sha256(data).hexdigest()
    assert result.page_count == 2
    assert [page.page_number for page in result.pages] == [1, 2]
    assert "Redis" in result.pages[0].text
    assert "PostgreSQL" in result.pages[1].text
    assert result.extracted_characters == sum(len(page.text) for page in result.pages)
    assert result.warnings == ()


@pytest.mark.parametrize("data,filename,mime,code", [
    (b"", "a.pdf", "application/pdf", "empty_file"),
    (b"not a PDF", "a.pdf", "application/pdf", "invalid_pdf"),
    (b"%PDF-1.7\nmalformed", "a.pdf", "application/pdf", "invalid_pdf"),
    (b"data", "a.txt", "application/pdf", "unsupported_file_type"),
    (b"data", "a.pdf", "text/plain", "unsupported_file_type"),
    (b"data", "", "application/pdf", "invalid_filename"),
    (b"data", "a\x00.pdf", "application/pdf", "invalid_filename"),
    (b"data", "a" * 256 + ".pdf", "application/pdf", "invalid_filename"),
])
def test_rejects_invalid_uploads(data, filename, mime, code):
    with pytest.raises(PdfValidationError) as error:
        extract_pdf(data, filename, mime)
    assert error.value.code == code


@pytest.mark.parametrize("limits,code", [
    (replace(PdfLimits(), max_bytes=10), "file_too_large"),
    (replace(PdfLimits(), max_pages=1), "page_limit"),
    (replace(PdfLimits(), max_text_characters=10), "text_limit"),
    (replace(PdfLimits(), max_page_stream_bytes=10), "content_limit"),
    (replace(PdfLimits(), max_total_stream_bytes=10), "content_limit"),
])
def test_processing_limits(limits, code):
    with pytest.raises(PdfValidationError) as error:
        extract_pdf(make_pdf(["First page has text.", "Second page has text."]), "a.pdf", "application/pdf", limits)
    assert error.value.code == code


def test_compressed_stream_expansion_is_limited():
    data = make_pdf(["repeated " * 2000], compress=True)
    limits = replace(PdfLimits(), max_page_stream_bytes=1000)
    with pytest.raises(PdfValidationError) as error:
        extract_pdf(data, "a.pdf", "application/pdf", limits)
    assert error.value.code == "content_limit"


def test_encrypted_pdf_is_rejected():
    with pytest.raises(PdfValidationError) as error:
        extract_pdf(make_pdf(["Secret"], encrypted=True), "a.pdf", "application/pdf")
    assert error.value.code == "encrypted_pdf"


@pytest.mark.parametrize("pages,image_page", [([None], 1), (["Text page", None], 2)])
def test_scanned_pages_are_rejected_even_in_mixed_documents(pages, image_page):
    with pytest.raises(PdfValidationError, match="OCR") as error:
        extract_pdf(make_pdf(pages, image_page=image_page), "scan.pdf", "application/pdf")
    assert error.value.code == "image_only_page"


def test_blank_pages_preserve_numbering_and_warn():
    result = extract_pdf(make_pdf(["Page one", None, "Page three"]), "a.pdf", "application/pdf")
    assert result.page_count == 3
    assert result.pages[1].text == ""
    assert result.pages[2].page_number == 3
    assert "Page 2" in result.warnings[0]


@pytest.mark.parametrize("pages", [[], [None], ["... ! ?"]])
def test_empty_or_unreadable_documents_are_rejected(pages):
    with pytest.raises(PdfValidationError) as error:
        extract_pdf(make_pdf(pages), "a.pdf", "application/pdf")
    assert error.value.code in {"page_limit", "no_extractable_text"}
