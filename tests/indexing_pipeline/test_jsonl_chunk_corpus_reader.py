"""JSONL 候选论文 chunk 语料读取测试。"""

import hashlib

from ai4research.indexing_pipeline.repositories.base import (
    ChunkWriteRequest,
)
from ai4research.indexing_pipeline.repositories.jsonl import (
    JsonlChunkRepository,
)
from ai4research.indexing_pipeline.repositories.jsonl_reader import (
    JsonlChunkCorpusReader,
)
from ai4research.indexing_pipeline.repositories.reader import (
    ChunkCorpusReadRequest,
)
from ai4research.indexing_pipeline.schemas.document_chunk import (
    DocumentChunk,
)


SPLITTER_NAME = "test-splitter"
SPLITTER_VERSION = "1"
SPLITTER_OPTIONS = {
    "target_chars": 100,
}


def _sha256(text: str) -> str:
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def _write_paper(
    *,
    paper_id: str,
):
    markdown_sha256 = _sha256(
        f"markdown-{paper_id}"
    )
    pdf_sha256 = _sha256(
        f"pdf-{paper_id}"
    )

    chunk = DocumentChunk.create(
        paper_id=paper_id,
        chunk_index=0,
        text=f"Agent memory for {paper_id}.",
        page_start=1,
        page_end=1,
        section_path=("Introduction",),
        source_markdown_relative_path=(
            f"documents/{paper_id[:2]}/"
            f"{paper_id[2:4]}/{paper_id}/"
            "document.md"
        ),
        source_markdown_sha256=(
            markdown_sha256
        ),
        source_pdf_sha256=pdf_sha256,
        source_parser_name="test-parser",
        source_parser_version="1",
        splitter_name=SPLITTER_NAME,
        splitter_version=SPLITTER_VERSION,
        splitter_options=SPLITTER_OPTIONS,
    )

    request = ChunkWriteRequest(
        paper_id=paper_id,
        chunks=(chunk,),
        source_markdown_relative_path=(
            chunk.source_markdown_relative_path
        ),
        source_markdown_sha256=(
            markdown_sha256
        ),
        source_pdf_sha256=pdf_sha256,
        source_parser_name="test-parser",
        source_parser_version="1",
        splitter_name=SPLITTER_NAME,
        splitter_version=SPLITTER_VERSION,
        splitter_options=SPLITTER_OPTIONS,
    )

    result = JsonlChunkRepository().write(
        request
    )

    assert result.success, result.error

    return result


def test_reader_loads_ready_and_reports_missing(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AI4RESEARCH_DATA_ROOT",
        str(tmp_path),
    )

    paper_a = "a" * 40
    paper_b = "b" * 40
    paper_c = "c" * 40

    _write_paper(paper_id=paper_a)
    _write_paper(paper_id=paper_b)

    result = JsonlChunkCorpusReader().read(
        ChunkCorpusReadRequest(
            paper_ids=(
                paper_a,
                paper_b,
                paper_c,
            ),
            splitter_name=SPLITTER_NAME,
            splitter_version=SPLITTER_VERSION,
            splitter_options=SPLITTER_OPTIONS,
        )
    )

    assert result.loaded_paper_ids == (
        paper_a,
        paper_b,
    )
    assert result.missing_paper_ids == (
        paper_c,
    )
    assert result.paper_count == 2
    assert result.chunk_count == 2
    assert not result.complete
    assert paper_c in result.errors


def test_corrupt_paper_does_not_block_other_papers(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AI4RESEARCH_DATA_ROOT",
        str(tmp_path),
    )

    paper_a = "a" * 40
    paper_b = "b" * 40

    result_a = _write_paper(
        paper_id=paper_a
    )
    _write_paper(paper_id=paper_b)

    corrupt_path = (
        tmp_path
        / result_a.chunks_relative_path
    )
    corrupt_path.write_text(
        "corrupted\n",
        encoding="utf-8",
    )

    result = JsonlChunkCorpusReader().read(
        ChunkCorpusReadRequest(
            paper_ids=(
                paper_a,
                paper_b,
            ),
            splitter_name=SPLITTER_NAME,
            splitter_version=SPLITTER_VERSION,
            splitter_options=SPLITTER_OPTIONS,
        )
    )

    assert result.loaded_paper_ids == (
        paper_b,
    )
    assert result.missing_paper_ids == (
        paper_a,
    )
    assert result.paper_count == 1
    assert result.chunk_count == 1
    assert paper_a in result.errors
