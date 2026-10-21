from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from app.routes.questions import get_rag_service
from app.schemas.questions import QuestionResponse
from app.services.answers import AnswerError


@pytest.fixture
def api():
    app = create_app(Settings(_env_file=None, environment="test"))
    rag = MagicMock()
    rag.ask.return_value = QuestionResponse(status="no_evidence", answer="No documents.")
    app.dependency_overrides[get_rag_service] = lambda: rag
    with TestClient(app) as client:
        yield client, rag


def test_question_response_contract(api):
    client, rag = api
    response = client.post("/questions", json={"question": "TTL?"})
    assert response.status_code == 200
    assert response.json()["mode"] == "rag"
    assert response.json()["status"] == "no_evidence"


@pytest.mark.parametrize("body", [{}, {"question": " "}, {"question": "x" * 1501},
    {"question": "TTL?", "document_ids": []}, {"question": "TTL?", "document_ids": ["bad"]},
    {"question": "TTL?", "history": []}])
def test_invalid_questions_are_rejected(api, body):
    client, rag = api
    assert client.post("/questions", json=body).status_code == 422
    rag.ask.assert_not_called()


def test_question_body_is_bounded_before_json_parsing(api):
    client, rag = api
    assert client.post("/questions", content=b"x" * 16001).status_code == 413
    rag.ask.assert_not_called()


def test_provider_failure_is_503_not_abstention(api):
    client, rag = api
    rag.ask.side_effect = AnswerError("answer_quota_exhausted", "Try later")
    response = client.post("/questions", json={"question": "TTL?"})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "60"


def test_production_queries_are_disabled():
    with TestClient(create_app(Settings(_env_file=None, environment="production"))) as client:
        response = client.post("/questions", json={"question": "TTL?"})
    assert response.status_code == 503
