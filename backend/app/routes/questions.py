"""Local self-contained RAG questions; public query protection is deferred."""

from collections.abc import Iterator
from functools import partial

from fastapi import APIRouter, Depends, HTTPException, Request

from app.database import create_database_engine, create_session
from app.schemas.questions import QuestionRequest, QuestionResponse
from app.services.answers import AnswerError, GeminiAnswerer
from app.services.embeddings import EmbeddingUnavailable, GeminiEmbedder
from app.services.rag import RagService
from app.services.retrieval import Retriever

router = APIRouter(prefix="/questions", tags=["questions"])


def get_rag_service(request: Request) -> Iterator[RagService]:
    settings = request.app.state.settings
    if settings.environment == "production":
        raise HTTPException(503, detail={"code": "queries_not_enabled", "message": "Public queries need quota protection before deployment."})
    try:
        engine = create_database_engine(settings)
    except ValueError:
        raise HTTPException(503, detail={"code": "database_not_configured", "message": "Database is not configured."}) from None
    try:
        yield RagService(Retriever(partial(create_session, engine)), GeminiEmbedder(settings), GeminiAnswerer(settings))
    finally:
        engine.dispose()


@router.post("", response_model=QuestionResponse)
def ask_question(body: QuestionRequest, service: RagService = Depends(get_rag_service)) -> QuestionResponse:
    try:
        return service.ask(body)
    except (AnswerError, EmbeddingUnavailable) as exc:
        headers = {"Retry-After": "60"} if "quota_exhausted" in exc.code else None
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": str(exc)}, headers=headers) from None
