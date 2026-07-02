"""单篇文档 chunk 编排流程测试。"""

import json
from pathlib import Path

from ai4research.indexing_pipeline.pipelines.document_chunk_pipeline import (
    DocumentChunkPipelineRequest,
    process_document_chunks,
)
from ai4research.indexing_pipeline.repositories.jsonl import (
    JsonlChunkRepository,
)
from ai4research.indexing_pipeline.splitters.markdown_block_splitter import (
    MarkdownBlockSplitter,
)


def _build_request(
    *,
    root: Path,
    paper_id: str,
) -> DocumentChunkPipelineRequest:
    relative_path = (
        Path("documents")
        / paper_id[:2]
        / paper_id[2:4]
        / paper_id
        / "document.md"
    )

    return DocumentChunkPipelineRequest(
        paper_id=paper_id,
        markdown_path=root / relative_path,
        source_markdown_relative_path=(
            relative_path.as_posix()
        ),
        source_pdf_sha256="b" * 64,
        source_parser_name="ocr-document-parser",
        source_parser_version="1:glm-ocr",
        title="Example Paper",
    )


def test_pipeline_writes_reuses_and_updates(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AI4RESEARCH_DATA_ROOT",
        str(tmp_path),
    )

    paper_id = "a" * 40
    request = _build_request(
        root=tmp_path,
        paper_id=paper_id,
    )

    request.markdown_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    original_markdown = """<!-- page: 1 -->

1 Introduction

Agent memory supports grounded reasoning.

<!-- page: 2 -->

2 Method

The method retrieves evidence before answering.
"""

    request.markdown_path.write_text(
        original_markdown,
        encoding="utf-8",
    )

    splitter = MarkdownBlockSplitter()
    repository = JsonlChunkRepository()

    first = process_document_chunks(
        request=request,
        splitter=splitter,
        repository=repository,
    )
    second = process_document_chunks(
        request=request,
        splitter=splitter,
        repository=repository,
    )

    assert first.success, first.error
    assert first.status == "written"
    assert second.success, second.error
    assert second.status == "reused"
    assert first.chunk_count > 0
    assert (
        first.chunks_relative_path
        == second.chunks_relative_path
    )

    original_sha256 = (
        first.source_markdown_sha256
    )

    request.markdown_path.write_text(
        original_markdown.replace(
            "grounded reasoning",
            "evidence-grounded reasoning",
        ),
        encoding="utf-8",
    )

    changed = process_document_chunks(
        request=request,
        splitter=splitter,
        repository=repository,
    )

    assert changed.success, changed.error
    assert changed.status == "written"
    assert (
        changed.source_markdown_sha256
        != original_sha256
    )

    manifest_path = (
        tmp_path
        / changed.manifest_relative_path
    )
    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        manifest["source_markdown_sha256"]
        == changed.source_markdown_sha256
    )
    assert (
        manifest["chunk_count"]
        == changed.chunk_count
    )


def test_pipeline_reports_missing_markdown(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AI4RESEARCH_DATA_ROOT",
        str(tmp_path),
    )

    request = _build_request(
        root=tmp_path,
        paper_id="c" * 40,
    )

    result = process_document_chunks(
        request=request,
        splitter=MarkdownBlockSplitter(),
        repository=JsonlChunkRepository(),
    )

    assert not result.success
    assert result.status == "pipeline_failed"
    assert "FileNotFoundError" in result.error
