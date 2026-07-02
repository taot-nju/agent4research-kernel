"""基于 JSONL 与 manifest 的 chunk 资产存储实现。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from ai4research.indexing_pipeline.repositories.base import (
    ChunkRepository,
    ChunkWriteRequest,
    ChunkWriteResult,
)
from ai4research.indexing_pipeline.schemas.document_chunk import (
    DOCUMENT_CHUNK_SCHEMA_VERSION,
)
from ai4research.indexing_pipeline.utils.storage_paths import (
    build_chunk_asset_paths,
    ensure_chunk_asset_directory,
    to_data_root_relative_path,
)


CHUNK_ASSET_SCHEMA_VERSION = 1


def _compute_sha256(content: str) -> str:
    return hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()


def _build_chunks_jsonl(
    request: ChunkWriteRequest,
) -> str:
    lines = [
        json.dumps(
            chunk.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        for chunk in request.chunks
    ]

    return "\n".join(lines) + "\n"


def _build_manifest(
    *,
    request: ChunkWriteRequest,
    chunks_relative_path: str,
    chunks_sha256: str,
) -> dict:
    return {
        "asset_schema_version": (
            CHUNK_ASSET_SCHEMA_VERSION
        ),
        "document_chunk_schema_version": (
            DOCUMENT_CHUNK_SCHEMA_VERSION
        ),
        "paper_id": request.paper_id,
        "chunk_count": len(request.chunks),
        "chunk_ids": [
            chunk.chunk_id
            for chunk in request.chunks
        ],
        "page_start": min(
            chunk.page_start
            for chunk in request.chunks
        ),
        "page_end": max(
            chunk.page_end
            for chunk in request.chunks
        ),
        "source_markdown_relative_path": (
            request.source_markdown_relative_path
        ),
        "source_markdown_sha256": (
            request.source_markdown_sha256
        ),
        "source_pdf_sha256": (
            request.source_pdf_sha256
        ),
        "source_parser_name": (
            request.source_parser_name
        ),
        "source_parser_version": (
            request.source_parser_version
        ),
        "splitter_name": request.splitter_name,
        "splitter_version": (
            request.splitter_version
        ),
        "splitter_options": dict(
            request.splitter_options
        ),
        "chunks_relative_path": (
            chunks_relative_path
        ),
        "chunks_sha256": chunks_sha256,
    }


def _serialize_manifest(
    manifest: dict,
) -> str:
    return (
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


def _file_matches(
    path: Path,
    expected_content: str,
) -> bool:
    if not path.is_file():
        return False

    try:
        actual_content = path.read_text(
            encoding="utf-8"
        )
    except OSError:
        return False

    return actual_content == expected_content


def _write_text_atomic(
    path: Path,
    content: str,
) -> None:
    """在同一目录创建临时文件并原子替换目标文件。"""

    temporary_path = path.with_name(
        f".{path.name}.{uuid4().hex}.tmp"
    )

    try:
        temporary_path.write_text(
            content,
            encoding="utf-8",
        )
        temporary_path.replace(path)
    finally:
        try:
            temporary_path.unlink(
                missing_ok=True
            )
        except OSError:
            pass


class JsonlChunkRepository(ChunkRepository):
    """将 chunk 写为确定性 JSONL 与 manifest。"""

    def write(
        self,
        request: ChunkWriteRequest,
    ) -> ChunkWriteResult:
        try:
            paths = build_chunk_asset_paths(
                paper_id=request.paper_id,
                splitter_name=(
                    request.splitter_name
                ),
                splitter_version=(
                    request.splitter_version
                ),
                splitter_options=(
                    request.splitter_options
                ),
            )

            chunks_relative_path = (
                to_data_root_relative_path(
                    paths.chunks_jsonl_path
                ).as_posix()
            )
            manifest_relative_path = (
                to_data_root_relative_path(
                    paths.manifest_path
                ).as_posix()
            )

            chunks_content = (
                _build_chunks_jsonl(request)
            )
            chunks_sha256 = _compute_sha256(
                chunks_content
            )

            manifest = _build_manifest(
                request=request,
                chunks_relative_path=(
                    chunks_relative_path
                ),
                chunks_sha256=chunks_sha256,
            )
            manifest_content = (
                _serialize_manifest(manifest)
            )

            chunks_match = _file_matches(
                paths.chunks_jsonl_path,
                chunks_content,
            )
            manifest_matches = _file_matches(
                paths.manifest_path,
                manifest_content,
            )

            if chunks_match and manifest_matches:
                return ChunkWriteResult(
                    success=True,
                    status="reused",
                    paper_id=request.paper_id,
                    chunk_count=len(
                        request.chunks
                    ),
                    chunks_relative_path=(
                        chunks_relative_path
                    ),
                    manifest_relative_path=(
                        manifest_relative_path
                    ),
                )

            ensure_chunk_asset_directory(
                paths
            )

            if not chunks_match:
                _write_text_atomic(
                    paths.chunks_jsonl_path,
                    chunks_content,
                )

            _write_text_atomic(
                paths.manifest_path,
                manifest_content,
            )

            return ChunkWriteResult(
                success=True,
                status="written",
                paper_id=request.paper_id,
                chunk_count=len(
                    request.chunks
                ),
                chunks_relative_path=(
                    chunks_relative_path
                ),
                manifest_relative_path=(
                    manifest_relative_path
                ),
            )

        except Exception as error:
            return ChunkWriteResult(
                success=False,
                status="failed",
                paper_id=request.paper_id,
                error=(
                    f"{type(error).__name__}: "
                    f"{error}"
                )[:4000],
            )
