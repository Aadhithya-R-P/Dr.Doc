import sys

from app.services.pdf_preparation import prepare_pdf
from pdf_fixtures import make_pdf
from scripts import preview_pdf


def test_pdf_to_chunks_preserves_evidence_and_has_no_model_or_database_dependency():
    prepared = prepare_pdf(
        make_pdf(["Redis caches database reads.", "If Redis fails, query PostgreSQL."]),
        "architecture.pdf",
    )
    assert prepared.chunking_version == "char4-v1-target500-overlap75"
    assert prepared.document.page_count == 2
    assert len(prepared.chunks) == 1
    assert "Redis caches" in prepared.chunks[0].text
    assert "PostgreSQL" in prepared.chunks[0].text
    assert (prepared.chunks[0].page_start, prepared.chunks[0].page_end) == (1, 2)


def test_preview_command_for_generated_pdf(tmp_path, monkeypatch, capsys):
    path = tmp_path / "architecture.pdf"
    path.write_bytes(make_pdf(["Redis caches data.", "PostgreSQL is the source of truth."]))
    monkeypatch.setattr(sys, "argv", ["preview_pdf", str(path)])
    assert preview_pdf.main() == 0
    output = capsys.readouterr().out
    assert "Pages: 2" in output
    assert "pages 1-2" in output
    assert "No original copy, embeddings or database rows were stored." in output


def test_preview_rejects_invalid_file(tmp_path, monkeypatch, capsys):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not pdf")
    monkeypatch.setattr(sys, "argv", ["preview_pdf", str(path)])
    assert preview_pdf.main() == 1
    assert "Rejected [invalid_pdf]" in capsys.readouterr().out
