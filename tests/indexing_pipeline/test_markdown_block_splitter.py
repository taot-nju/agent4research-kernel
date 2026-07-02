"""DocumentChunk 与 MarkdownBlockSplitter 测试。"""

import json

from ai4research.indexing_pipeline.schemas.document_chunk import (
    DocumentChunk,
    compute_text_sha256,
)
from ai4research.indexing_pipeline.splitters.base import (
    SplitRequest,
)
from ai4research.indexing_pipeline.splitters.markdown_block_splitter import (
    MarkdownBlockSplitter,
    MarkdownBlockSplitterConfig,
)
from ai4research.indexing_pipeline.splitters.markdown_blocks import (
    parse_markdown_blocks,
)


def _build_request(
    markdown: str,
) -> SplitRequest:
    paper_id = "a" * 40

    return SplitRequest(
        paper_id=paper_id,
        markdown_text=markdown,
        source_markdown_relative_path=(
            f"documents/aa/aa/{paper_id}/document.md"
        ),
        source_markdown_sha256=(
            compute_text_sha256(markdown)
        ),
        source_pdf_sha256="b" * 64,
        source_parser_name="ocr-document-parser",
        source_parser_version="1:glm-ocr",
        title="Example Paper",
    )


def test_document_chunk_id_is_stable_and_versioned():
    common = {
        "paper_id": "a" * 40,
        "chunk_index": 0,
        "text": "Stable chunk content.",
        "page_start": 1,
        "page_end": 2,
        "section_path": ("1 Introduction",),
        "source_markdown_relative_path": (
            "documents/aa/aa/"
            + "a" * 40
            + "/document.md"
        ),
        "source_markdown_sha256": "b" * 64,
        "source_pdf_sha256": "c" * 64,
        "source_parser_name": (
            "ocr-document-parser"
        ),
        "source_parser_version": "1:glm-ocr",
        "splitter_name": (
            "markdown-block-splitter"
        ),
    }

    first = DocumentChunk.create(
        **common,
        splitter_version="1",
        splitter_options={
            "target_chars": 2400,
            "max_chars": 3200,
        },
    )
    second = DocumentChunk.create(
        **common,
        splitter_version="1",
        splitter_options={
            "max_chars": 3200,
            "target_chars": 2400,
        },
    )
    changed = DocumentChunk.create(
        **common,
        splitter_version="2",
        splitter_options={
            "target_chars": 2400,
            "max_chars": 3200,
        },
    )

    assert first.chunk_id == second.chunk_id
    assert first.chunk_id != changed.chunk_id
    assert first.char_count == len(first.text)

    json.dumps(
        first.to_dict(),
        ensure_ascii=False,
    )


def test_markdown_blocks_preserve_page_and_atomic_content():
    markdown = """<!-- page: 1 -->

1 Introduction

First-page text.

<!-- page: 2 -->

Second-page text.

2.1 Retrieval

| Method | Score |
| :--- | ---: |
| Ours | 90 |

S ← LIBRARYSUMMARIES(D)

$$x = y + 1$$

### C.3 MEMORY TRIGGER TRAINING DETAILS
"""

    result = parse_markdown_blocks(markdown)

    assert result.page_numbers == (1, 2)
    assert not result.warnings

    table = next(
        block
        for block in result.blocks
        if block.kind == "table"
    )
    assert table.page_start == 2
    assert table.text.count("\n") == 2

    pseudocode = next(
        block
        for block in result.blocks
        if block.text
        == "S ← LIBRARYSUMMARIES(D)"
    )
    assert pseudocode.kind == "paragraph"

    formula = next(
        block
        for block in result.blocks
        if block.text == "$$x = y + 1$$"
    )
    assert formula.kind == "formula"

    appendix_heading = result.blocks[-1]
    assert appendix_heading.kind == "heading"
    assert appendix_heading.section_path == (
        "C.3 MEMORY TRIGGER TRAINING DETAILS",
    )


def test_markdown_splitter_is_stable_and_page_aware():
    intro = (
        "Agent memory supports long-horizon reasoning. "
        * 12
    )
    method = (
        "The system retrieves grounded evidence. "
        * 12
    )

    markdown = f"""<!-- page: 1 -->

1 Introduction

{intro}

<!-- page: 2 -->

This sentence continues from the previous page.

2 Method

{method}

| Method | Score |
| :--- | ---: |
| Baseline | 80 |
| Ours | 90 |

<!-- page: 3 -->

3 Conclusion

Evidence-grounded reasoning improves.
"""

    request = _build_request(markdown)

    config = MarkdownBlockSplitterConfig(
        target_chars=220,
        max_chars=300,
        overlap_chars=40,
        min_chars_before_heading_break=100,
    )
    splitter = MarkdownBlockSplitter(config)

    first = splitter.split(request)
    second = splitter.split(request)

    assert first.success, first.error
    assert second.success, second.error
    assert len(first.chunks) >= 3

    assert [
        chunk.chunk_id
        for chunk in first.chunks
    ] == [
        chunk.chunk_id
        for chunk in second.chunks
    ]

    for index, chunk in enumerate(first.chunks):
        assert chunk.chunk_index == index
        assert chunk.page_start > 0
        assert chunk.page_end >= chunk.page_start
        assert chunk.char_count <= config.max_chars
        assert "<!-- page:" not in chunk.text
        assert chunk.text not in {
            "1 Introduction",
            "2 Method",
            "3 Conclusion",
        }

    table_chunk = next(
        chunk
        for chunk in first.chunks
        if "| Method | Score |" in chunk.text
    )

    assert "| Baseline | 80 |" in table_chunk.text
    assert "| Ours | 90 |" in table_chunk.text


def test_missing_page_marker_produces_warning():
    result = parse_markdown_blocks(
        "1 Introduction\n\nText without marker."
    )

    assert result.page_numbers == ()
    assert result.warnings == (
        "missing_page_markers_assumed_page_1",
    )
    assert all(
        block.page_start == 1
        for block in result.blocks
    )
