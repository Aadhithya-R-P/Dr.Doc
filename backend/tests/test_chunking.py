import pytest

from app.schemas.pdf import ExtractedPage
from app.services.chunking import ChunkingOptions, chunk_pages, estimate_tokens


def page(number, text):
    return ExtractedPage(page_number=number, text=text)


def test_short_text_stays_in_one_chunk():
    chunks = chunk_pages((page(1, "Redis stores cached values."),))
    assert len(chunks) == 1
    assert chunks[0].text == "Redis stores cached values."
    assert chunks[0].page_start == chunks[0].page_end == 1
    assert chunks[0].token_count == estimate_tokens(chunks[0].text)
    assert chunks[0].token_count_method == "characters-divided-by-4-v1"


def test_chunk_can_cross_pages_and_skip_blank_page():
    chunks = chunk_pages((page(1, "First page."), page(2, ""), page(3, "Third page.")))
    assert len(chunks) == 1
    assert chunks[0].text == "First page.\n\nThird page."
    assert (chunks[0].page_start, chunks[0].page_end) == (1, 3)


def test_boundary_whitespace_does_not_falsely_include_next_page():
    chunks = chunk_pages((page(1, "a" * 40), page(2, "b" * 40)), ChunkingOptions(10, 0))
    assert chunks[0].page_start == chunks[0].page_end == 1
    assert chunks[-1].page_start == chunks[-1].page_end == 2


def test_long_unbroken_text_has_exact_overlap_and_no_lost_characters():
    text = "".join(chr(0x400 + index) for index in range(5000))
    chunks = chunk_pages((page(1, text),))
    assert len(chunks) == 3
    reconstructed = chunks[0].text
    for previous, current in zip(chunks, chunks[1:]):
        assert previous.text[-300:] == current.text[:300]
        reconstructed += current.text[300:]
    assert reconstructed == text
    assert all(chunk.token_count <= 500 for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_prefers_paragraph_boundary_over_cutting_next_paragraph():
    first = "a" * 1300
    chunks = chunk_pages((page(1, first + "\n\n" + "b" * 1000),))
    assert chunks[0].text == first
    assert "b" not in chunks[0].text


def test_provenance_tracks_page_two_in_later_chunks():
    chunks = chunk_pages((page(1, "a" * 2000), page(2, "b" * 2500)))
    assert chunks[0].page_end == 1
    assert any((chunk.page_start, chunk.page_end) == (1, 2) for chunk in chunks)
    assert chunks[-1].page_start == chunks[-1].page_end == 2


@pytest.mark.parametrize("target,overlap", [(0, 0), (10, -1), (10, 10), (10, 11)])
def test_invalid_chunk_configuration_is_rejected(target, overlap):
    with pytest.raises(ValueError):
        ChunkingOptions(target, overlap)


def test_empty_input_and_whitespace_produce_no_chunks():
    assert chunk_pages(()) == ()
    assert chunk_pages((page(1, " \n "),)) == ()


def test_page_order_must_be_increasing():
    with pytest.raises(ValueError):
        chunk_pages((page(2, "text"), page(1, "text")))
