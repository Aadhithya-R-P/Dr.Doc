"""Bounded retrieve-then-generate orchestration with backend citation mapping."""

import re

from sqlalchemy.exc import SQLAlchemyError

from app.schemas.questions import GeneratedAnswer, QuestionRequest, QuestionResponse, Source
from app.services.answers import AnswerError, GeminiAnswerer
from app.services.embeddings import GeminiEmbedder
from app.services.retrieval import Retriever


def map_answer(generated: GeneratedAnswer, sources: list[Source]) -> QuestionResponse:
    if generated.status == "insufficient_evidence":
        if generated.claims:
            raise AnswerError("invalid_answer", "Abstention response contained unsupported claims.", 502)
        return QuestionResponse(
            status="insufficient_evidence", answer="The retrieved passages do not provide enough information to answer this question.",
            sources=sources,
        )
    if not generated.claims:
        raise AnswerError("invalid_answer", "Model returned no supported claims.", 502)
    allowed = {source.source_id: source for source in sources}
    used = []
    lines = []
    for claim in generated.claims:
        if not claim.text.strip() or re.search(r"\[[^\]]*\]|https?://", claim.text):
            raise AnswerError("invalid_citations", "Model inserted unvalidated citation text or links.", 502)
        ids = list(dict.fromkeys(claim.source_ids))
        if not ids or any(source_id not in allowed for source_id in ids):
            raise AnswerError("invalid_citations", "Model cited an unknown source. No answer is confirmed.", 502)
        lines.append(claim.text.strip() + " " + " ".join(f"[{source_id}]" for source_id in ids))
        used.extend(source_id for source_id in ids if source_id not in used)
    return QuestionResponse(status="answered", answer="\n\n".join(lines), sources=[allowed[source_id] for source_id in used])


class RagService:
    def __init__(self, retriever: Retriever, embedder: GeminiEmbedder, answerer: GeminiAnswerer):
        self.retriever, self.embedder, self.answerer = retriever, embedder, answerer

    def ask(self, request: QuestionRequest) -> QuestionResponse:
        try:
            if not self.retriever.has_documents(request.document_ids):
                return QuestionResponse(status="no_evidence", answer="No compatible indexed documents match this selection.")
        except SQLAlchemyError:
            raise AnswerError("retrieval_unavailable", "Document retrieval is temporarily unavailable.") from None
        vector = self.embedder.embed_query(request.question)
        try:
            sources = self.retriever.retrieve(vector, request.document_ids)
        except SQLAlchemyError:
            raise AnswerError("retrieval_unavailable", "Document retrieval is temporarily unavailable.") from None
        if not sources:
            return QuestionResponse(status="no_evidence", answer="No passages met the current retrieval threshold. Try a more specific question or another document.")
        generated = self.answerer.generate(request.question, sources)
        return map_answer(generated, sources)
