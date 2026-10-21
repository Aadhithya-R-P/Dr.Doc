from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from app.routes.documents import get_ingestion_service
from app.schemas.documents import DocumentCreated
from app.services.embeddings import EmbeddingUnavailable
from app.services.ingestion import IngestionError
from app.services.pdf_extraction import PdfValidationError
from app.upload_limits import UploadLimitsMiddleware


@pytest.fixture
def api():
    service = MagicMock()
    app = create_app(Settings(_env_file=None, environment="test"))
    app.dependency_overrides[get_ingestion_service] = lambda: service
    with TestClient(app) as client:
        yield client, service


def test_upload_contract_returns_201_ready(api):
    client, service = api
    service.ingest.return_value = DocumentCreated(
        id=uuid4(), filename="a.pdf", page_count=1, chunk_count=1,
        embedding_model="gemini-embedding-2", embedding_dimensions=768,
        embedding_input_version="gemini2-retrieval-v1", chunking_version="test",
        created_at=datetime.now(UTC),
    )
    response = client.post("/documents", files={"file": ("a.pdf", b"sample", "application/pdf")})
    assert response.status_code == 201
    assert response.json()["status"] == "ready"
    service.ingest.assert_called_once_with(b"sample", "a.pdf", "application/pdf")


@pytest.mark.parametrize("error,status,code", [
    (PdfValidationError("invalid_pdf", "Invalid PDF"), 422, "invalid_pdf"),
    (PdfValidationError("file_too_large", "Too large"), 413, "file_too_large"),
    (IngestionError("duplicate_document", "Duplicate", 409), 409, "duplicate_document"),
    (IngestionError("storage_failure", "Not stored"), 503, "storage_failure"),
    (EmbeddingUnavailable("embedding_quota_exhausted", "Try later"), 503, "embedding_quota_exhausted"),
])
def test_errors_are_explicit(api, error, status, code):
    client, service = api
    service.ingest.side_effect = error
    response = client.post("/documents", files={"file": ("a.pdf", b"sample", "application/pdf")})
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    if code == "embedding_quota_exhausted":
        assert response.headers["retry-after"] == "60"


def test_missing_file_is_422(api):
    client, service = api
    assert client.post("/documents").status_code == 422
    service.ingest.assert_not_called()


def test_encoded_body_limit_precedes_service(api):
    client, service = api
    body_limit = UploadLimitsMiddleware(None).body_limit
    response = client.post("/documents", content=b"x" * (body_limit + 1))
    assert response.status_code == 413
    service.ingest.assert_not_called()


def test_production_upload_is_disabled_without_new_auth_design():
    app = create_app(Settings(_env_file=None, environment="production"))
    with TestClient(app) as client:
        response = client.post("/documents", files={"file": ("a.pdf", b"sample", "application/pdf")})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "upload_not_enabled"
