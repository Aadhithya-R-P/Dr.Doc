"""Preview a local text PDF; no database, provider calls or retained PDF copy."""

import argparse
from pathlib import Path

from app.services.pdf_extraction import PdfLimits, PdfValidationError
from app.services.pdf_preparation import prepare_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    limits = PdfLimits()
    try:
        with args.path.open("rb") as file:
            # Read at most max+1, so even an oversized local input stays bounded.
            data = file.read(limits.max_bytes + 1)
        prepared = prepare_pdf(data, args.path.name, limits=limits)
    except OSError:
        print("Could not read the local PDF file.")
        return 1
    except PdfValidationError as exc:
        print(f"Rejected [{exc.code}]: {exc}")
        return 1
    doc = prepared.document
    print(f"Pages: {doc.page_count}; extracted characters: {doc.extracted_characters}; chunks: {len(prepared.chunks)}")
    print(f"Chunking: {prepared.chunking_version}; token counts are estimates.")
    for warning in doc.warnings:
        print(f"Warning: {warning}")
    for chunk in prepared.chunks:
        print(f"Chunk {chunk.chunk_index}: pages {chunk.page_start}-{chunk.page_end}, ~{chunk.token_count} tokens")
    print("No original copy, embeddings or database rows were stored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
