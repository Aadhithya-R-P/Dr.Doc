"""Local-development upload endpoint; public operator access is not configured yet."""

from collections.abc import Iterator
from functools import partial
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, Response

from app.database import create_database_engine, create_session
from app.schemas.documents import DocumentCreated, DocumentList
from app.services.documents import DocumentCatalog
from app.services.embeddings import EmbeddingUnavailable, GeminiEmbedder
from app.services.ingestion import IngestionError, IngestionService
from app.services.pdf_extraction import PdfLimits, PdfValidationError

router = APIRouter(prefix="/documents", tags=["documents"])


def get_ingestion_service(request: Request) -> Iterator[IngestionService]:
    settings = request.app.state.settings
    if settings.environment == "production":
        raise HTTPException(503, detail={"code": "upload_not_enabled", "message": "Public uploads need operator protection before deployment."})
    try:
        engine = create_database_engine(settings)
    except ValueError:
        raise HTTPException(503, detail={"code": "database_not_configured", "message": "Database is not configured."}) from None
    try:
        yield IngestionService(partial(create_session, engine), GeminiEmbedder(settings))
    finally:
        engine.dispose()


@router.post("", response_model=DocumentCreated, status_code=201)
def upload_document(
    file: Annotated[UploadFile, File()],
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> DocumentCreated:
    try:
        data = file.file.read(PdfLimits().max_bytes + 1)
        return service.ingest(data, file.filename or "", file.content_type or "")
    except PdfValidationError as exc:
        status = 413 if exc.code == "file_too_large" else 422
        raise HTTPException(status, detail={"code": exc.code, "message": str(exc)}) from None
    except (IngestionError, EmbeddingUnavailable) as exc:
        headers = {"Retry-After": "60"} if exc.code == "embedding_quota_exhausted" else None
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": str(exc)}, headers=headers) from None
    finally:
        file.file.close()


@router.get("", response_model=DocumentList)
def list_documents(service: Annotated[IngestionService, Depends(get_ingestion_service)]):
    try:
        return DocumentCatalog(service.session_factory).list()
    except IngestionError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": str(exc)}) from None


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: UUID, service: Annotated[IngestionService, Depends(get_ingestion_service)]):
    try:
        DocumentCatalog(service.session_factory).delete(document_id)
        return Response(status_code=204)
    except IngestionError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": str(exc)}) from None
