from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.schemas.questions import Claim, GeneratedAnswer, QuestionRequest
from app.services.answers import AnswerError
from app.services.rag import RagService, map_answer
from rag_helpers import source, vector


def test_backend_maps_valid_ids_to_original_metadata():
    evidence = source()
    answer = map_answer(GeneratedAnswer(status="answered", claims=[
        Claim(text="The TTL is 45 seconds.", source_ids=["D1"])
    ]), [evidence])
    assert answer.answer == "The TTL is 45 seconds. [D1]"
    assert answer.sources == [evidence]


@pytest.mark.parametrize("text,ids", [("Claim", ["D99"]), ("Claim [D99]", ["D1"]),
    ("https://invented.example", ["D1"]), ("   ", ["D1"])])
def test_fabricated_citation_ids_or_inline_links_rejected(text, ids):
    with pytest.raises(AnswerError):
        map_answer(GeneratedAnswer(status="answered", claims=[Claim(text=text, source_ids=ids)]), [source()])


def test_empty_answer_and_inconsistent_abstention_rejected():
    with pytest.raises(AnswerError):
        map_answer(GeneratedAnswer(status="answered", claims=[]), [source()])
    with pytest.raises(AnswerError):
        map_answer(GeneratedAnswer(status="insufficient_evidence", claims=[Claim(text="x", source_ids=["D1"])]), [source()])


def test_retrieved_but_unanswerable_returns_distinct_status():
    response = map_answer(GeneratedAnswer(status="insufficient_evidence", claims=[]), [source()])
    assert response.status == "insufficient_evidence"
    assert response.sources


def service():
    retriever, embedder, answerer = MagicMock(), MagicMock(), MagicMock()
    retriever.has_documents.return_value = True
    retriever.retrieve.return_value = [source()]
    embedder.embed_query.return_value = vector()
    answerer.generate.return_value = GeneratedAnswer(status="answered", claims=[Claim(text="45 seconds.", source_ids=["D1"])])
    return RagService(retriever, embedder, answerer)


def test_empty_corpus_uses_no_model_quota():
    rag = service()
    rag.retriever.has_documents.return_value = False
    assert rag.ask(QuestionRequest(question="TTL?")).status == "no_evidence"
    rag.embedder.embed_query.assert_not_called()
    rag.answerer.generate.assert_not_called()


def test_no_nearby_chunks_does_not_generate():
    rag = service()
    rag.retriever.retrieve.return_value = []
    assert rag.ask(QuestionRequest(question="TTL?")).status == "no_evidence"
    rag.answerer.generate.assert_not_called()


def test_question_filter_and_evidence_are_forwarded():
    rag = service()
    ids = [source().document_id]
    result = rag.ask(QuestionRequest(question="TTL?", document_ids=ids))
    assert result.status == "answered"
    rag.retriever.retrieve.assert_called_once_with(vector(), ids)
    rag.answerer.generate.assert_called_once_with("TTL?", rag.retriever.retrieve.return_value)


def test_database_failure_is_not_misreported_as_no_evidence():
    rag = service()
    rag.retriever.has_documents.side_effect = OperationalError("private", {}, Exception())
    with pytest.raises(AnswerError) as caught:
        rag.ask(QuestionRequest(question="TTL?"))
    assert caught.value.code == "retrieval_unavailable"


def test_model_failure_propagates_instead_of_becoming_an_answer():
    rag = service()
    rag.answerer.generate.side_effect = AnswerError("answer_quota_exhausted", "Try later")
    with pytest.raises(AnswerError):
        rag.ask(QuestionRequest(question="TTL?"))
