"""Explicit opt-in: one real embedding call, with database writes rolled back."""

from functools import partial

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Chunk, Document
from app.services.embeddings import GeminiEmbedder
from app.services.ingestion import IngestionService
from pdf_fixtures import make_pdf


def test_real_embedding_and_atomic_storage_for_synthetic_pdf(request):
    if not request.config.getoption("--run-live-embedding"):
        pytest.skip("Live Google request requires --run-live-embedding; routine tests consume no quota.")
    connection = request.getfixturevalue("db_connection")
    settings = Settings()
    service = IngestionService(
        partial(Session, connection, join_transaction_mode="create_savepoint", expire_on_commit=False),
        GeminiEmbedder(settings),
    )
    result = service.ingest(
        make_pdf(["Public synthetic example: Redis caches data. PostgreSQL stores durable records."]),
        "synthetic-smoke.pdf", "application/pdf",
    )
    assert result.status == "ready"
    assert result.chunk_count == 1
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        stored = session.scalar(select(Chunk).where(Chunk.document_id == result.id))
        assert stored is not None
        assert len(stored.embedding) == 768
        assert stored.page_start == stored.page_end == 1
        doc = session.get(Document, result.id)
        assert doc.embedding_input_version == "gemini2-retrieval-v1"
