"""chunk 资产存储层的统一请求、结果与接口。"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ai4research.indexing_pipeline.schemas.document_chunk import (
    DocumentChunk,
)


CHUNK_WRITE_STATUSES = {
    "written",
    "reused",
    "failed",
}


def _normalize_options(
    options: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(options, Mapping):
        raise TypeError(
            "splitter_options 必须是 Mapping"
        )

    try:
        encoded = json.dumps(
            dict(options),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "splitter_options 必须可序列化为 JSON"
        ) from error

    decoded = json.loads(encoded)

    if not isinstance(decoded, dict):
        raise TypeError(
            "splitter_options 必须是 JSON object"
        )

    return decoded


@dataclass(frozen=True)
class ChunkWriteRequest:
    """一次 chunk 资产持久化请求。"""

    paper_id: str
    chunks: tuple[DocumentChunk, ...]

    source_markdown_relative_path: str
    source_markdown_sha256: str
    source_pdf_sha256: str
    source_parser_name: str
    source_parser_version: str

    splitter_name: str
    splitter_version: str
    splitter_options: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.paper_id.strip():
            raise ValueError("paper_id 不能为空")

        if not self.chunks:
            raise ValueError(
                "chunks 不能为空"
            )

        if not self.source_markdown_relative_path.strip():
            raise ValueError(
                "source_markdown_relative_path 不能为空"
            )

        normalized_options = _normalize_options(
            self.splitter_options
        )
        chunk_ids: set[str] = set()

        for expected_index, chunk in enumerate(
            self.chunks
        ):
            if chunk.paper_id != self.paper_id:
                raise ValueError(
                    "chunk.paper_id 与请求不一致"
                )

            if chunk.chunk_index != expected_index:
                raise ValueError(
                    "chunk_index 必须从 0 连续递增"
                )

            if (
                chunk.source_markdown_relative_path
                != self.source_markdown_relative_path
            ):
                raise ValueError(
                    "chunk 的 Markdown 路径不一致"
                )

            if (
                chunk.source_markdown_sha256
                != self.source_markdown_sha256
            ):
                raise ValueError(
                    "chunk 的 Markdown SHA256 不一致"
                )

            if (
                chunk.source_pdf_sha256
                != self.source_pdf_sha256
            ):
                raise ValueError(
                    "chunk 的 PDF SHA256 不一致"
                )

            if (
                chunk.source_parser_name
                != self.source_parser_name
                or chunk.source_parser_version
                != self.source_parser_version
            ):
                raise ValueError(
                    "chunk 的解析器信息不一致"
                )

            if (
                chunk.splitter_name
                != self.splitter_name
                or chunk.splitter_version
                != self.splitter_version
            ):
                raise ValueError(
                    "chunk 的切分器信息不一致"
                )

            if (
                _normalize_options(
                    chunk.splitter_options
                )
                != normalized_options
            ):
                raise ValueError(
                    "chunk 的切分配置不一致"
                )

            if chunk.chunk_id in chunk_ids:
                raise ValueError(
                    "请求中存在重复 chunk_id"
                )

            chunk_ids.add(chunk.chunk_id)


@dataclass(frozen=True)
class ChunkWriteResult:
    """一次 chunk 资产持久化结果。"""

    success: bool
    status: str
    paper_id: str

    chunk_count: int = 0
    chunks_relative_path: str = ""
    manifest_relative_path: str = ""
    error: str = ""

    def __post_init__(self) -> None:
        if self.status not in CHUNK_WRITE_STATUSES:
            raise ValueError(
                f"不支持的写入状态：{self.status}"
            )

        if not self.paper_id.strip():
            raise ValueError("paper_id 不能为空")

        if self.chunk_count < 0:
            raise ValueError(
                "chunk_count 不能小于 0"
            )

        if self.success:
            if self.status not in {
                "written",
                "reused",
            }:
                raise ValueError(
                    "成功结果的状态必须是 "
                    "written 或 reused"
                )

            if self.error:
                raise ValueError(
                    "成功结果的 error 必须为空"
                )

            if not self.chunks_relative_path:
                raise ValueError(
                    "成功结果缺少 chunks 路径"
                )

            if not self.manifest_relative_path:
                raise ValueError(
                    "成功结果缺少 manifest 路径"
                )

        else:
            if self.status != "failed":
                raise ValueError(
                    "失败结果的状态必须是 failed"
                )

            if not self.error.strip():
                raise ValueError(
                    "失败结果必须提供 error"
                )


class ChunkRepository(ABC):
    """所有 chunk 存储实现必须遵循的接口。"""

    @abstractmethod
    def write(
        self,
        request: ChunkWriteRequest,
    ) -> ChunkWriteResult:
        """幂等写入一篇论文的 chunk 资产。"""

        raise NotImplementedError
