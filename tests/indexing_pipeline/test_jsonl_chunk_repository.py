"""JSONL chunk 存储层测试。"""

import hashlib
import json
from pathlib import Path

from ai4research.indexing_pipeline.repositories.base import (
    ChunkWriteRequest,
)
from ai4research.indexing_pipeline.repositories.jsonl import (
    JsonlChunkRepository,
)
from ai4research.indexing_pipeline.schemas.document_chunk import (
    compute_text_sha256,
)
from ai4research.indexing_pipeline.splitters.base import (
    SplitRequest,
)
from ai4research.indexing_pipeline.splitters.markdown_block_splitter import (
    MarkdownBlockSplitter,
)
from ai4research.indexing_pipeline.utils.storage_paths import (
    build_chunk_asset_paths,
)


def _build_write_request(
    markdown: str,
) -> ChunkWriteRequest:
    paper_id = "a" * 40

    split_request = SplitRequest(
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
    )

    split_result = MarkdownBlockSplitter().split(
        split_request
    )

    assert split_result.success, (
        split_result.error
    )

    return ChunkWriteRequest(
        paper_id=paper_id,
        chunks=split_result.chunks,
        source_markdown_relative_path=(
            split_request
            .source_markdown_relative_path
        ),
        source_markdown_sha256=(
            split_request
            .source_markdown_sha256
        ),
        source_pdf_sha256=(
            split_request.source_pdf_sha256
        ),
        source_parser_name=(
            split_request.source_parser_name
        ),
        source_parser_version=(
            split_request.source_parser_version
        ),
        splitter_name=split_result.splitter_name,
        splitter_version=(
            split_result.splitter_version
        ),
        splitter_options=(
            split_result.splitter_options
        ),
    )


def test_jsonl_repository_is_idempotent_and_repairs(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AI4RESEARCH_DATA_ROOT",
        str(tmp_path),
    )

    markdown = """<!-- page: 1 -->

1 Introduction

Agent memory supports grounded reasoning.

<!-- page: 2 -->

2 Method

The method retrieves evidence before answering.
"""

    request = _build_write_request(markdown)
    repository = JsonlChunkRepository()

    first = repository.write(request)
    second = repository.write(request)

    assert first.success, first.error
    assert first.status == "written"
    assert second.success, second.error
    assert second.status == "reused"

    chunks_path = (
        tmp_path / first.chunks_relative_path
    )
    manifest_path = (
        tmp_path / first.manifest_relative_path
    )

    assert chunks_path.is_file()
    assert manifest_path.is_file()

    chunks_path.write_text(
        "corrupted\n",
        encoding="utf-8",
    )

    repaired = repository.write(request)
    reused = repository.write(request)

    assert repaired.success, repaired.error
    assert repaired.status == "written"
    assert reused.status == "reused"

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )
    chunks_sha256 = hashlib.sha256(
        chunks_path.read_bytes()
    ).hexdigest()

    assert (
        chunks_sha256
        == manifest["chunks_sha256"]
    )
    assert manifest["chunk_ids"] == [
        chunk.chunk_id
        for chunk in request.chunks
    ]


def test_source_change_replaces_stale_assets(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AI4RESEARCH_DATA_ROOT",
        str(tmp_path),
    )

    original = _build_write_request(
        "<!-- page: 1 -->\n\n"
        "1 Introduction\n\nOriginal text.\n"
    )
    changed = _build_write_request(
        "<!-- page: 1 -->\n\n"
        "1 Introduction\n\nChanged text.\n"
    )

    repository = JsonlChunkRepository()

    first = repository.write(original)
    updated = repository.write(changed)

    assert first.success, first.error
    assert updated.success, updated.error
    assert first.status == "written"
    assert updated.status == "written"

    assert (
        first.chunks_relative_path
        == updated.chunks_relative_path
    )

    manifest_path = (
        tmp_path / updated.manifest_relative_path
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
    assert manifest["chunk_ids"] == [
        chunk.chunk_id
        for chunk in changed.chunks
    ]


def test_chunk_asset_path_is_config_order_stable(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AI4RESEARCH_DATA_ROOT",
        str(tmp_path),
    )

    paper_id = "a" * 40

    first = build_chunk_asset_paths(
        paper_id=paper_id,
        splitter_name="markdown-block-splitter",
        splitter_version="1",
        splitter_options={
            "target_chars": 2400,
            "max_chars": 3200,
        },
    )
    second = build_chunk_asset_paths(
        paper_id=paper_id,
        splitter_name="markdown-block-splitter",
        splitter_version="1",
        splitter_options={
            "max_chars": 3200,
            "target_chars": 2400,
        },
    )
    changed = build_chunk_asset_paths(
        paper_id=paper_id,
        splitter_name="markdown-block-splitter",
        splitter_version="1",
        splitter_options={
            "target_chars": 2600,
            "max_chars": 3200,
        },
    )

    assert first == second
    assert first != changed
    assert first.absolute_directory == (
        Path(tmp_path)
        / first.relative_directory
    )
