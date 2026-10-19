"""Import all models so Alembic can inspect their table metadata."""

from app.models.base import Base
from app.models.chunk import Chunk
from app.models.document import Document

__all__ = ["Base", "Chunk", "Document"]
