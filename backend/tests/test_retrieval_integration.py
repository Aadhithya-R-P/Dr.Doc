from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select

from app.models import Chunk
from app.schemas.questions import Claim, GeneratedAnswer, QuestionRequest
from app.services.documents import DocumentCatalog
from app.services.ingestion import IngestionError
from app.services.rag import RagService
from app.services.retrieval import Retriever
from rag_helpers import factory, seed, vector

pytestmark = pytest.mark.integration


def test_nearest_order_filter_threshold_and_legacy_exclusion(db_connection):
    sessions = factory(db_connection)
    first, first_chunk = seed(sessions, axis=0)
    second, _ = seed(sessions, text="Other content", axis=1)
    seed(sessions, text="Legacy should not be used", axis=0, version="legacy-unversioned")
    retriever = Retriever(sessions)
    result = retriever.retrieve(vector(0), None)
    assert len(result) == 1
    assert result[0].chunk_id == first_chunk
    assert result[0].cosine_distance == pytest.approx(0)
    assert retriever.retrieve(vector(0), [second]) == []
    assert retriever.retrieve(vector(0), [first])[0].document_id == first


def test_context_budget_and_source_count(db_connection):
    sessions = factory(db_connection)
    for index in range(5):
        seed(sessions, text=str(index) + "x" * 2499)
    sources = Retriever(sessions).retrieve(vector(), None)
    assert len(sources) == 4
    assert sum(len(source.excerpt) for source in sources) == 8000


def test_list_delete_and_future_rag_abstention(db_connection):
    sessions = factory(db_connection)
    doc_id, _ = seed(sessions)
    catalog = DocumentCatalog(sessions)
    assert catalog.list()["items"][0]["id"] == doc_id
    catalog.delete(doc_id)
    assert db_connection.scalar(select(func.count()).select_from(Chunk)) == 0
    retriever = Retriever(sessions)
    assert retriever.retrieve(vector(), None) == []
    embedder, answerer = MagicMock(), MagicMock()
    assert RagService(retriever, embedder, answerer).ask(QuestionRequest(question="TTL?")).status == "no_evidence"
    embedder.embed_query.assert_not_called()
    with pytest.raises(IngestionError) as caught:
        catalog.delete(doc_id)
    assert caught.value.status_code == 404


def test_real_retrieval_and_mock_generation_have_no_application_transaction_during_calls(db_connection):
    sessions = factory(db_connection)
    seed(sessions)
    opened = []

    def tracked_sessions():
        session = sessions()
        opened.append(session)
        return session

    embedder, answerer = MagicMock(), MagicMock()

    def embed(question):
        assert all(not session.in_transaction() for session in opened)
        return vector()

    def generate(question, sources):
        assert all(not session.in_transaction() for session in opened)
        return GeneratedAnswer(status="answered", claims=[Claim(text="45 seconds.", source_ids=["D1"])])

    embedder.embed_query.side_effect = embed
    answerer.generate.side_effect = generate
    result = RagService(Retriever(tracked_sessions), embedder, answerer).ask(QuestionRequest(question="TTL?"))
    assert result.status == "answered"
    assert result.sources[0].excerpt == "The Redis cache TTL is 45 seconds."
