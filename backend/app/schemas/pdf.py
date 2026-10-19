"""In-memory PDF preparation contracts; these are not database rows."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExtractedPage(BaseModel):
    model_config = ConfigDict(frozen=True)
    page_number: int = Field(ge=1)
    text: str


class ExtractedPdf(BaseModel):
    model_config = ConfigDict(frozen=True)
    filename: str
    content_type: Literal["application/pdf"] = "application/pdf"
    content_hash: str
    page_count: int = Field(ge=1)
    extracted_characters: int = Field(ge=1)
    pages: tuple[ExtractedPage, ...]
    warnings: tuple[str, ...] = ()


class TextChunk(BaseModel):
    model_config = ConfigDict(frozen=True)
    chunk_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    token_count: int = Field(ge=1)
    token_count_method: Literal["characters-divided-by-4-v1"] = "characters-divided-by-4-v1"


class PreparedPdf(BaseModel):
    model_config = ConfigDict(frozen=True)
    document: ExtractedPdf
    chunks: tuple[TextChunk, ...]
    chunking_version: str
