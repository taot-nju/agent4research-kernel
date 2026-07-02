"""文档切分器的统一输入、输出与抽象接口。"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ai4research.indexing_pipeline.schemas.document_chunk import (
    DocumentChunk,
    compute_text_sha256,
)


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _validate_sha256(
    field_name: str,
    value: str,
) -> None:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(
            f"{field_name} 必须是 64 位 SHA256"
        )


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
class SplitRequest:
    """一次 Markdown 切分任务的标准输入。"""

    paper_id: str
    markdown_text: str

    source_markdown_relative_path: str
    source_markdown_sha256: str
    source_pdf_sha256: str
    source_parser_name: str
    source_parser_version: str

    title: str = ""

    def __post_init__(self) -> None:
        if not self.paper_id.strip():
            raise ValueError("paper_id 不能为空")

        if "/" in self.paper_id or "\\" in self.paper_id:
            raise ValueError(
                "paper_id 不能包含路径分隔符"
            )

        if not self.markdown_text.strip():
            raise ValueError(
                "markdown_text 不能为空"
            )

        if not self.source_markdown_relative_path.strip():
            raise ValueError(
                "source_markdown_relative_path 不能为空"
            )

        _validate_sha256(
            "source_markdown_sha256",
            self.source_markdown_sha256,
        )
        _validate_sha256(
            "source_pdf_sha256",
            self.source_pdf_sha256,
        )

        actual_markdown_sha256 = (
            compute_text_sha256(
                self.markdown_text
            )
        )

        if (
            actual_markdown_sha256
            != self.source_markdown_sha256
        ):
            raise ValueError(
                "source_markdown_sha256 "
                "与 markdown_text 不一致"
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
class SplitResult:
    """一次文档切分调用的标准结果。"""

    success: bool
    paper_id: str

    splitter_name: str
    splitter_version: str
    splitter_options: Mapping[str, Any]

    chunks: tuple[DocumentChunk, ...] = ()
    warnings: tuple[str, ...] = ()
    error: str = ""
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not self.paper_id.strip():
            raise ValueError("paper_id 不能为空")

        if not self.splitter_name.strip():
            raise ValueError(
                "splitter_name 不能为空"
            )

        if not self.splitter_version.strip():
            raise ValueError(
                "splitter_version 不能为空"
            )

        normalized_options = _normalize_options(
            self.splitter_options
        )

        if self.success and self.error:
            raise ValueError(
                "切分成功时 error 必须为空"
            )

        if not self.success and not self.error.strip():
            raise ValueError(
                "切分失败时必须提供 error"
            )

        if not self.success and self.chunks:
            raise ValueError(
                "切分失败时不能返回 chunks"
            )

        chunk_ids: set[str] = set()

        for expected_index, chunk in enumerate(
            self.chunks
        ):
            if chunk.paper_id != self.paper_id:
                raise ValueError(
                    "chunk.paper_id 与结果不一致"
                )

            if chunk.chunk_index != expected_index:
                raise ValueError(
                    "chunk_index 必须从 0 连续递增"
                )

            if (
                chunk.splitter_name
                != self.splitter_name
            ):
                raise ValueError(
                    "chunk 的 splitter_name 不一致"
                )

            if (
                chunk.splitter_version
                != self.splitter_version
            ):
                raise ValueError(
                    "chunk 的 splitter_version 不一致"
                )

            if (
                _normalize_options(
                    chunk.splitter_options
                )
                != normalized_options
            ):
                raise ValueError(
                    "chunk 的 splitter_options 不一致"
                )

            if chunk.chunk_id in chunk_ids:
                raise ValueError(
                    "同一结果中出现重复 chunk_id"
                )

            chunk_ids.add(chunk.chunk_id)


class DocumentSplitter(ABC):
    """所有 Markdown 切分器必须实现的接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """返回切分器的稳定名称."""

        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        """返回影响切分语义的版本号。"""

        raise NotImplementedError

    @property
    @abstractmethod
    def options(self) -> Mapping[str, Any]:
        """返回实际生效的可序列化配置。"""

        raise NotImplementedError

    @abstractmethod
    def split(
        self,
        request: SplitRequest,
    ) -> SplitResult:
        """切分一篇 Markdown 文档。"""

        raise NotImplementedError
