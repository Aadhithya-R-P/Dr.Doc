"""Exact cosine search over compatible vectors, with short database sessions."""

from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Document
from app.schemas.questions import Source
from app.services.embeddings import DIMENSIONS, INPUT_VERSION, MODEL, validate_vector

MAX_DISTANCE = 0.60  # Initial heuristic, not a calibrated probability of relevance.
MAX_SOURCES = 4
CONTEXT_CHARACTERS = 8000


class Retriever:
    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory

    def compatible_documents(self, document_ids: list[UUID] | None):
        conditions = [
            Document.embedding_model == MODEL,
            Document.embedding_dimensions == DIMENSIONS,
            Document.embedding_input_version == INPUT_VERSION,
        ]
        if document_ids is not None:
            conditions.append(Document.id.in_(document_ids))
        return conditions

    def has_documents(self, document_ids: list[UUID] | None) -> bool:
        with self.session_factory() as session:
            return session.scalar(
                select(Document.id).where(*self.compatible_documents(document_ids)).limit(1)
            ) is not None

    def retrieve(self, vector: list[float], document_ids: list[UUID] | None) -> list[Source]:
        distance = Chunk.embedding.cosine_distance(validate_vector(vector))
        statement = (
            select(Chunk, Document.filename, distance.label("distance"))
            .join(Document, Document.id == Chunk.document_id)
            .where(*self.compatible_documents(document_ids), distance <= MAX_DISTANCE)
            .order_by(distance, Chunk.id).limit(8)
        )
        with self.session_factory() as session:
            rows = session.execute(statement).all()
            sources = []
            remaining = CONTEXT_CHARACTERS
            seen_text = set()
            for chunk, filename, score in rows:
                if len(sources) >= MAX_SOURCES or remaining <= 0:
                    break
                if chunk.text in seen_text:
                    continue
                excerpt = chunk.text[:remaining]
                seen_text.add(chunk.text)
                sources.append(Source(
                    source_id=f"D{len(sources) + 1}", document_id=chunk.document_id,
                    chunk_id=chunk.id, filename=filename, page_start=chunk.page_start,
                    page_end=chunk.page_end, excerpt=excerpt, cosine_distance=float(score),
                ))
                remaining -= len(excerpt)
            return sources
