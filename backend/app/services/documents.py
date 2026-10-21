"""Document listing and atomic cascade deletion; no provider calls."""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.models import Chunk, Document
from app.services.ingestion import IngestionError


class DocumentCatalog:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def list(self):
        try:
            with self.session_factory() as session:
                rows = session.execute(
                    select(Document, func.count(Chunk.id))
                    .outerjoin(Chunk, Chunk.document_id == Document.id)
                    .group_by(Document.id).order_by(Document.created_at.desc(), Document.id).limit(51)
                ).all()
                return {"items": [{
                    "id": doc.id, "filename": doc.filename, "page_count": doc.page_count,
                    "chunk_count": count, "embedding_input_version": doc.embedding_input_version,
                    "created_at": doc.created_at,
                } for doc, count in rows[:50]], "truncated": len(rows) > 50}
        except SQLAlchemyError:
            raise IngestionError("catalog_unavailable", "Document listing is temporarily unavailable.") from None

    def delete(self, document_id: UUID):
        try:
            with self.session_factory() as session:
                with session.begin():
                    deleted = session.scalar(delete(Document).where(Document.id == document_id).returning(Document.id))
                    if deleted is None:
                        raise IngestionError("document_not_found", "Document was not found.", 404)
        except SQLAlchemyError:
            raise IngestionError("deletion_unavailable", "Document deletion could not be confirmed.") from None
