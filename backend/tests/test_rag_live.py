"""Explicit opt-in, bounded live evaluation on two synthetic public PDFs."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.routes.documents import get_ingestion_service
from app.routes.questions import get_rag_service
from app.services.answers import ANSWER_MODEL, GeminiAnswerer
from app.services.documents import DocumentCatalog
from app.services.embeddings import GeminiEmbedder
from app.services.ingestion import IngestionService
from app.services.rag import RagService
from app.services.retrieval import Retriever
from pdf_fixtures import make_pdf
from rag_helpers import factory


def test_live_rag_evaluation(request):
    import pytest

    if not request.config.getoption("--run-live-rag"):
        pytest.skip("Live RAG evaluation requires --run-live-rag; normal tests use no model quota.")
    connection = request.getfixturevalue("db_connection")
    sessions = factory(connection)
    settings = Settings()
    embedder = GeminiEmbedder(settings)
    ingestion = IngestionService(sessions, embedder)
    rag = RagService(Retriever(sessions), embedder, GeminiAnswerer(settings))
    app = create_app(Settings(_env_file=None, environment="test"))
    app.dependency_overrides[get_ingestion_service] = lambda: ingestion
    app.dependency_overrides[get_rag_service] = lambda: rag
    records = []
    report = Path(__file__).resolve().parents[1] / "evaluation" / "rag_results.json"
    with TestClient(app) as client:
        redis = client.post("/documents", files={"file": ("public-architecture.pdf", make_pdf([
            "Public synthetic architecture example: Redis caches database reads.",
            "The Redis cache TTL is 45 seconds. If Redis is unavailable, requests fall back to PostgreSQL.",
        ]), "application/pdf")})
        assert redis.status_code == 201, redis.text
        releases = client.post("/documents", files={"file": ("public-release-policy.pdf", make_pdf([
            "Public synthetic release policy. Every release requires approval from two maintainers.",
        ]), "application/pdf")})
        assert releases.status_code == 201, releases.text
        redis_id, release_id = redis.json()["id"], releases.json()["id"]
        cases = [
            ("answerable", "What is the Redis cache TTL and what happens if Redis is unavailable?", redis_id),
            ("unsupported", "What is the CEO's date of birth?", redis_id),
            ("filtered", "How many maintainers must approve a release?", release_id),
        ]
        for name, question, doc_id in cases:
            response = client.post("/questions", json={"question": question, "document_ids": [doc_id]})
            body = response.json()
            record = {"case": name, "question": question, "http_status": response.status_code, "response": body}
            records.append(record)
            report.parent.mkdir(exist_ok=True)
            report.write_text(json.dumps({"model": ANSWER_MODEL, "cases": records}, indent=2), encoding="utf-8")
            assert response.status_code == 200, response.text
            if name == "unsupported":
                assert body["status"] in {"no_evidence", "insufficient_evidence"}
                record["abstention_check"] = "passed"
            else:
                assert body["status"] == "answered", body
                assert body["sources"]
                assert all(s["document_id"] == doc_id for s in body["sources"])
                assert all(f'[{s["source_id"]}]' in body["answer"] for s in body["sources"])
                if name == "answerable":
                    assert "45" in body["answer"]
                    assert "postgres" in body["answer"].lower()
                else:
                    assert "two" in body["answer"].lower() or "2" in body["answer"]
                record["citation_mapping_check"] = "passed"
                record["expected_fact_check"] = "passed"
        deleted = client.delete(f"/documents/{redis_id}")
        assert deleted.status_code == 204
        after = client.post("/questions", json={"question": "What is the Redis TTL?", "document_ids": [redis_id]})
        assert after.status_code == 200 and after.json()["status"] == "no_evidence"
        assert len(DocumentCatalog(sessions).list()["items"]) == 1
        records.append({"case": "deleted_document", "response": after.json(), "check": "passed"})
    report.write_text(json.dumps({
        "model": ANSWER_MODEL, "corpus": "two generated synthetic public PDFs",
        "cases": records, "limits": "Small smoke evaluation, not a benchmark. Temporary database rows are rolled back.",
    }, indent=2), encoding="utf-8")
