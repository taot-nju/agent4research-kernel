"""候选论文 chunk 语料读取接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ai4research.indexing_pipeline.schemas.document_chunk import (
    DocumentChunk,
)


@dataclass(frozen=True)
class ChunkCorpusReadRequest:
    """读取一组候选论文的指定切分版本。"""

    paper_ids: tuple[str, ...]

    splitter_name: str
    splitter_version: str
    splitter_options: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.paper_ids:
            raise ValueError(
                "paper_ids 不能为空"
            )

        normalized_ids = [
            paper_id.strip()
            for paper_id in self.paper_ids
        ]

        if any(
            not paper_id
            for paper_id in normalized_ids
        ):
            raise ValueError(
                "paper_ids 不能包含空值"
            )

        if len(set(normalized_ids)) != len(
            normalized_ids
        ):
            raise ValueError(
                "paper_ids 不能重复"
            )

        if not self.splitter_name.strip():
            raise ValueError(
                "splitter_name 不能为空"
            )

        if not self.splitter_version.strip():
            raise ValueError(
                "splitter_version 不能为空"
            )


@dataclass(frozen=True)
class ChunkCorpusReadResult:
    """候选论文 chunk 语料加载结果。"""

    requested_paper_ids: tuple[str, ...]
    loaded_paper_ids: tuple[str, ...]
    missing_paper_ids: tuple[str, ...]

    chunks: tuple[DocumentChunk, ...]

    manifest_relative_paths: Mapping[
        str,
        str,
    ] = field(default_factory=dict)
    errors: Mapping[
        str,
        str,
    ] = field(default_factory=dict)

    def __post_init__(self) -> None:
        requested = set(
            self.requested_paper_ids
        )
        loaded = set(self.loaded_paper_ids)
        missing = set(self.missing_paper_ids)

        if loaded & missing:
            raise ValueError(
                "loaded 与 missing 不能重叠"
            )

        if not loaded.issubset(requested):
            raise ValueError(
                "loaded_paper_ids 必须来自请求"
            )

        if not missing.issubset(requested):
            raise ValueError(
                "missing_paper_ids 必须来自请求"
            )

        if loaded | missing != requested:
            raise ValueError(
                "每个请求 paper ID 必须归入 "
                "loaded 或 missing"
            )

        chunk_ids: set[str] = set()

        for chunk in self.chunks:
            if chunk.paper_id not in loaded:
                raise ValueError(
                    "chunk.paper_id 不属于已加载论文"
                )

            if chunk.chunk_id in chunk_ids:
                raise ValueError(
                    "语料中存在重复 chunk_id"
                )

            chunk_ids.add(chunk.chunk_id)

    @property
    def complete(self) -> bool:
        return not self.missing_paper_ids

    @property
    def paper_count(self) -> int:
        return len(self.loaded_paper_ids)

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)


class ChunkCorpusReader(ABC):
    """所有 chunk 语料读取实现必须遵循的接口。"""

    @abstractmethod
    def read(
        self,
        request: ChunkCorpusReadRequest,
    ) -> ChunkCorpusReadResult:
        """读取指定论文和切分版本的 chunk。"""

        raise NotImplementedError
