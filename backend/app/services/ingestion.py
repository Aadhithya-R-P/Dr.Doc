"""Prepare, embed outside database transactions, then atomically store the result."""

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Chunk, Document
from app.schemas.documents import DocumentCreated
from app.services.embeddings import (
    DIMENSIONS, INPUT_VERSION, MAX_CHUNKS, MODEL, GeminiEmbedder, validate_vector,
)
from app.services.pdf_extraction import PdfValidationError
from app.services.pdf_preparation import prepare_pdf


class IngestionError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 503):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class IngestionService:
    def __init__(self, session_factory: Callable[[], Session], embedder: GeminiEmbedder):
        self.session_factory = session_factory
        self.embedder = embedder

    def ingest(self, data: bytes, filename: str, content_type: str) -> DocumentCreated:
        prepared = prepare_pdf(data, filename, content_type)
        if not 1 <= len(prepared.chunks) <= MAX_CHUNKS:
            raise PdfValidationError("chunk_limit", "This synchronous upload supports at most 12 chunks. Upload a smaller PDF.")
        source = prepared.document
        try:
            # Close the duplicate-check session before any external call.
            with self.session_factory() as session:
                existing = session.scalar(select(Document.id).where(Document.content_hash == source.content_hash))
            if existing is not None:
                raise IngestionError("duplicate_document", "This PDF is already indexed, even if its filename differs.", 409)
        except SQLAlchemyError:
            raise IngestionError("database_unavailable", "Database is unavailable. No embedding requests were made.") from None

        vectors = self.embedder.embed_documents([chunk.text for chunk in prepared.chunks])
        if len(vectors) != len(prepared.chunks):
            raise IngestionError("invalid_embedding_count", "Expected one embedding per chunk. Nothing was indexed.", 502)
        vectors = [validate_vector(vector) for vector in vectors]
        # Validate provenance before writes; PDF extraction isn't a model's job.
        if any(not 1 <= chunk.page_start <= chunk.page_end <= source.page_count for chunk in prepared.chunks):
            raise IngestionError("invalid_provenance", "Invalid page provenance. Nothing was indexed.", 500)
        try:
            with self.session_factory() as session:
                with session.begin():
                    document = Document(
                        filename=source.filename, content_type=source.content_type,
                        content_hash=source.content_hash, page_count=source.page_count,
                        embedding_model=MODEL, embedding_dimensions=DIMENSIONS,
                        embedding_input_version=INPUT_VERSION,
                        chunking_version=prepared.chunking_version,
                    )
                    session.add(document)
                    session.flush()
                    for chunk, vector in zip(prepared.chunks, vectors, strict=True):
                        session.add(Chunk(
                            document_id=document.id, chunk_index=chunk.chunk_index,
                            text=chunk.text, page_start=chunk.page_start, page_end=chunk.page_end,
                            token_count=chunk.token_count, embedding=vector,
                        ))
                    session.flush()
                    response = DocumentCreated(
                        id=document.id, filename=document.filename, page_count=document.page_count,
                        chunk_count=len(prepared.chunks), embedding_model=MODEL,
                        embedding_dimensions=DIMENSIONS, embedding_input_version=INPUT_VERSION,
                        chunking_version=prepared.chunking_version, created_at=document.created_at,
                        warnings=source.warnings,
                    )
                # Ready is returned only after a successful transaction commit.
                return response
        except IntegrityError as exc:
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint == "uq_documents_content_hash":
                raise IngestionError("duplicate_document", "This PDF was indexed by another request.", 409) from None
            raise IngestionError("storage_failure", "Document storage failed. The write transaction was rolled back.") from None
        except SQLAlchemyError:
            raise IngestionError("storage_failure", "Document storage failed. No successful indexing is confirmed.") from None
