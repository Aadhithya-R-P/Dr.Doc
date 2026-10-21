"""Public ingestion response; never includes secrets or full document text."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class DocumentCreated(BaseModel):
    id: UUID
    filename: str
    status: Literal["ready"] = "ready"
    page_count: int
    chunk_count: int
    embedding_model: str
    embedding_dimensions: int
    embedding_input_version: str
    chunking_version: str
    created_at: datetime
    warnings: tuple[str, ...] = ()
