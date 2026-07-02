"""单篇 Markdown 的切分与持久化编排流程。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai4research.indexing_pipeline.repositories.base import (
    ChunkRepository,
    ChunkWriteRequest,
)
from ai4research.indexing_pipeline.schemas.document_chunk import (
    compute_text_sha256,
)
from ai4research.indexing_pipeline.splitters.base import (
    DocumentSplitter,
    SplitRequest,
)


@dataclass(frozen=True)
class DocumentChunkPipelineRequest:
    """单篇文档 chunk 流程的标准输入。"""

    paper_id: str
    markdown_path: Path
    source_markdown_relative_path: str

    source_pdf_sha256: str
    source_parser_name: str
    source_parser_version: str

    title: str = ""

    def __post_init__(self) -> None:
        if not self.paper_id.strip():
            raise ValueError("paper_id 不能为空")

        if not isinstance(
            self.markdown_path,
            Path,
        ):
            raise TypeError(
                "markdown_path 必须是 pathlib.Path"
            )

        if not self.source_markdown_relative_path.strip():
            raise ValueError(
                "source_markdown_relative_path 不能为空"
            )

        if not self.source_pdf_sha256.strip():
            raise ValueError(
                "source_pdf_sha256 不能为空"
            )

        if not self.source_parser_name.strip():
            raise ValueError(
                "source_parser_name 不能为空"
            )

        if not self.source_parser_version.strip():
            raise ValueError(
                "source_parser_version 不能为空"
            )


@dataclass(frozen=True)
class DocumentChunkPipelineResult:
    """单篇文档 chunk 流程的标准结果。"""

    success: bool
    status: str
    paper_id: str

    chunk_count: int = 0
    source_markdown_sha256: str = ""

    splitter_name: str = ""
    splitter_version: str = ""
    splitter_options: Mapping[str, Any] = field(
        default_factory=dict
    )

    chunks_relative_path: str = ""
    manifest_relative_path: str = ""

    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )
    error: str = ""

    def __post_init__(self) -> None:
        if not self.paper_id.strip():
            raise ValueError("paper_id 不能为空")

        if self.chunk_count < 0:
            raise ValueError(
                "chunk_count 不能小于 0"
            )

        if self.success and self.error:
            raise ValueError(
                "成功结果的 error 必须为空"
            )

        if not self.success and not self.error.strip():
            raise ValueError(
                "失败结果必须提供 error"
            )


def _failure_result(
    *,
    paper_id: str,
    status: str,
    error: str,
    splitter: DocumentSplitter,
    warnings: tuple[str, ...] = (),
    metadata: Mapping[str, Any] | None = None,
) -> DocumentChunkPipelineResult:
    return DocumentChunkPipelineResult(
        success=False,
        status=status,
        paper_id=paper_id,
        splitter_name=splitter.name,
        splitter_version=splitter.version,
        splitter_options=splitter.options,
        warnings=warnings,
        metadata=metadata or {},
        error=error[:4000],
    )


def process_document_chunks(
    *,
    request: DocumentChunkPipelineRequest,
    splitter: DocumentSplitter,
    repository: ChunkRepository,
) -> DocumentChunkPipelineResult:
    """读取 Markdown、切分并幂等写入 chunk 资产。"""

    try:
        markdown_path = request.markdown_path

        if not markdown_path.is_file():
            raise FileNotFoundError(
                f"Markdown 文件不存在：{markdown_path}"
            )

        markdown_text = markdown_path.read_text(
            encoding="utf-8"
        )
        source_markdown_sha256 = (
            compute_text_sha256(
                markdown_text
            )
        )

        split_request = SplitRequest(
            paper_id=request.paper_id,
            markdown_text=markdown_text,
            source_markdown_relative_path=(
                request
                .source_markdown_relative_path
            ),
            source_markdown_sha256=(
                source_markdown_sha256
            ),
            source_pdf_sha256=(
                request.source_pdf_sha256
            ),
            source_parser_name=(
                request.source_parser_name
            ),
            source_parser_version=(
                request.source_parser_version
            ),
            title=request.title,
        )

        split_result = splitter.split(
            split_request
        )

        if not split_result.success:
            return _failure_result(
                paper_id=request.paper_id,
                status="split_failed",
                error=split_result.error,
                splitter=splitter,
                warnings=split_result.warnings,
                metadata=split_result.metadata,
            )

        if not split_result.chunks:
            return _failure_result(
                paper_id=request.paper_id,
                status="split_failed",
                error=(
                    "切分器成功返回但没有生成 chunk"
                ),
                splitter=splitter,
                warnings=split_result.warnings,
                metadata=split_result.metadata,
            )

        write_request = ChunkWriteRequest(
            paper_id=request.paper_id,
            chunks=split_result.chunks,
            source_markdown_relative_path=(
                request
                .source_markdown_relative_path
            ),
            source_markdown_sha256=(
                source_markdown_sha256
            ),
            source_pdf_sha256=(
                request.source_pdf_sha256
            ),
            source_parser_name=(
                request.source_parser_name
            ),
            source_parser_version=(
                request.source_parser_version
            ),
            splitter_name=(
                split_result.splitter_name
            ),
            splitter_version=(
                split_result.splitter_version
            ),
            splitter_options=(
                split_result.splitter_options
            ),
        )

        write_result = repository.write(
            write_request
        )

        if not write_result.success:
            return _failure_result(
                paper_id=request.paper_id,
                status="write_failed",
                error=write_result.error,
                splitter=splitter,
                warnings=split_result.warnings,
                metadata=split_result.metadata,
            )

        return DocumentChunkPipelineResult(
            success=True,
            status=write_result.status,
            paper_id=request.paper_id,
            chunk_count=write_result.chunk_count,
            source_markdown_sha256=(
                source_markdown_sha256
            ),
            splitter_name=(
                split_result.splitter_name
            ),
            splitter_version=(
                split_result.splitter_version
            ),
            splitter_options=(
                split_result.splitter_options
            ),
            chunks_relative_path=(
                write_result.chunks_relative_path
            ),
            manifest_relative_path=(
                write_result.manifest_relative_path
            ),
            warnings=split_result.warnings,
            metadata=split_result.metadata,
        )

    except Exception as error:
        return _failure_result(
            paper_id=request.paper_id,
            status="pipeline_failed",
            error=(
                f"{type(error).__name__}: {error}"
            ),
            splitter=splitter,
        )
