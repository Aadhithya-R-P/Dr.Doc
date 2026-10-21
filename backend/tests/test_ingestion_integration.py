from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import Chunk, Document
from app.routes.documents import get_ingestion_service
from app.services.embeddings import EmbeddingUnavailable
from app.services.ingestion import IngestionError, IngestionService
from app.services.pdf_extraction import PdfValidationError
from pdf_fixtures import make_pdf

pytestmark = pytest.mark.integration


def service_for(connection):
    sessions = []

    def factory():
        session = Session(connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        sessions.append(session)
        return session

    embedder = MagicMock()

    def embed(passages):
        # The duplicate-check session must be closed, with no active transaction.
        assert all(not session.in_transaction() for session in sessions)
        return [[1.0] + [0.0] * 767 for _ in passages]

    embedder.embed_documents.side_effect = embed
    return IngestionService(factory, embedder), embedder, factory


def count(connection, model):
    return connection.scalar(select(func.count()).select_from(model))


def test_api_ingests_two_pdfs_with_stored_provenance_and_vectors(db_connection):
    service, provider, _ = service_for(db_connection)
    app = create_app(Settings(_env_file=None, environment="test"))
    app.dependency_overrides[get_ingestion_service] = lambda: service
    with TestClient(app) as client:
        for title in ["Redis", "PostgreSQL"]:
            data = make_pdf([title + " architecture.", "Fallback behavior."])
            result = client.post("/documents", files={"file": (title + ".pdf", data, "application/pdf")})
            assert result.status_code == 201
            assert result.json()["chunk_count"] == 1
    assert count(db_connection, Document) == 2
    assert count(db_connection, Chunk) == 2
    with Session(db_connection) as session:
        chunks = session.scalars(select(Chunk)).all()
        assert all((c.page_start, c.page_end) == (1, 2) for c in chunks)
        assert all(len(c.embedding) == 768 for c in chunks)
        assert all(d.embedding_input_version == "gemini2-retrieval-v1" for d in session.scalars(select(Document)))
    assert provider.embed_documents.call_count == 2


def test_renamed_duplicate_avoids_embedding_calls(db_connection):
    service, provider, _ = service_for(db_connection)
    data = make_pdf(["Public example text."])
    service.ingest(data, "first.pdf", "application/pdf")
    with pytest.raises(IngestionError) as error:
        service.ingest(data, "renamed.pdf", "application/pdf")
    assert error.value.code == "duplicate_document"
    assert provider.embed_documents.call_count == 1
    assert count(db_connection, Document) == 1


def test_embedding_failure_preserves_existing_content(db_connection):
    service, provider, _ = service_for(db_connection)
    first = service.ingest(make_pdf(["Existing searchable text."]), "first.pdf", "application/pdf")
    provider.embed_documents.side_effect = EmbeddingUnavailable("embedding_quota_exhausted", "Quota")
    with pytest.raises(EmbeddingUnavailable):
        service.ingest(make_pdf(["New candidate text."]), "new.pdf", "application/pdf")
    assert count(db_connection, Document) == 1
    assert count(db_connection, Chunk) == 1
    assert db_connection.scalar(select(Document.id)) == first.id


def test_chunk_insert_failure_rolls_back_new_document(db_connection):
    service, _, factory = service_for(db_connection)
    first = service.ingest(make_pdf(["Existing text."]), "first.pdf", "application/pdf")
    # Fail only the chunk statement, after the new document row has been flushed.
    def fail_chunk_write(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO chunks"):
            from sqlalchemy.exc import OperationalError
            raise OperationalError("forced test write failure", {}, Exception("synthetic"))

    event.listen(db_connection, "before_cursor_execute", fail_chunk_write)
    try:
        with pytest.raises(IngestionError) as caught:
            service.ingest(make_pdf(["New content."]), "new.pdf", "application/pdf")
        assert caught.value.code == "storage_failure"
    finally:
        event.remove(db_connection, "before_cursor_execute", fail_chunk_write)
    assert count(db_connection, Document) == 1
    assert count(db_connection, Chunk) == 1
    assert db_connection.scalar(select(Document.id)) == first.id


def test_chunk_cap_does_not_consume_quota_or_write(db_connection):
    service, provider, _ = service_for(db_connection)
    with pytest.raises(PdfValidationError) as error:
        service.ingest(make_pdf(["word " * 6000]), "big.pdf", "application/pdf")
    assert error.value.code == "chunk_limit"
    provider.embed_documents.assert_not_called()
    assert count(db_connection, Document) == 0


def test_missing_or_invalid_vectors_are_not_stored(db_connection):
    service, provider, _ = service_for(db_connection)
    provider.embed_documents.side_effect = None
    provider.embed_documents.return_value = []
    with pytest.raises(IngestionError):
        service.ingest(make_pdf(["Some content."]), "a.pdf", "application/pdf")
    assert count(db_connection, Document) == 0


def test_concurrent_duplicate_constraint_maps_to_conflict(db_connection):
    from hashlib import sha256

    service, provider, factory = service_for(db_connection)
    data = make_pdf(["Concurrent public sample."])

    def competing_upload(passages):
        # Emulate another worker committing after our duplicate precheck.
        with factory() as session:
            with session.begin():
                session.add(Document(
                    filename="other-worker.pdf", content_type="application/pdf",
                    content_hash=sha256(data).hexdigest(), page_count=1,
                    embedding_model="gemini-embedding-2", embedding_dimensions=768,
                    embedding_input_version="gemini2-retrieval-v1", chunking_version="test",
                ))
        return [[1.0] + [0.0] * 767]

    provider.embed_documents.side_effect = competing_upload
    with pytest.raises(IngestionError) as caught:
        service.ingest(data, "a.pdf", "application/pdf")
    assert caught.value.code == "duplicate_document"
    assert count(db_connection, Document) == 1
    assert count(db_connection, Chunk) == 0
