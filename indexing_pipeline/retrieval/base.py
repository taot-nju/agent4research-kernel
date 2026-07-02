"""全文 chunk 检索的统一接口与结果结构。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ai4research.indexing_pipeline.schemas.document_chunk import (
    DocumentChunk,
)


@dataclass(frozen=True)
class ChunkSearchHit:
    """一个带原文和页码证据的 chunk 命中。"""

    rank: int
    score: float
    chunk: DocumentChunk
    matched_terms: tuple[str, ...] = ()
    score_components: Mapping[
        str,
        float,
    ] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.rank <= 0:
            raise ValueError(
                "rank 必须是正整数"
            )

        if self.score < 0:
            raise ValueError(
                "score 不能小于 0"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "score": self.score,
            "matched_terms": list(
                self.matched_terms
            ),
            "score_components": dict(
                self.score_components
            ),
            "chunk": self.chunk.to_dict(),
        }


@dataclass(frozen=True)
class ChunkSearchResult:
    """一次候选论文集合内的全文检索结果。"""

    query: str
    retriever_name: str
    retriever_version: str

    corpus_paper_count: int
    corpus_chunk_count: int
    query_terms: tuple[str, ...]
    hits: tuple[ChunkSearchHit, ...]

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query 不能为空")

        if not self.retriever_name.strip():
            raise ValueError(
                "retriever_name 不能为空"
            )

        if not self.retriever_version.strip():
            raise ValueError(
                "retriever_version 不能为空"
            )

        if self.corpus_paper_count < 0:
            raise ValueError(
                "corpus_paper_count 不能小于 0"
            )

        if self.corpus_chunk_count < 0:
            raise ValueError(
                "corpus_chunk_count 不能小于 0"
            )

        for expected_rank, hit in enumerate(
            self.hits,
            start=1,
        ):
            if hit.rank != expected_rank:
                raise ValueError(
                    "hit rank 必须从 1 连续递增"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "retriever_name": (
                self.retriever_name
            ),
            "retriever_version": (
                self.retriever_version
            ),
            "corpus_paper_count": (
                self.corpus_paper_count
            ),
            "corpus_chunk_count": (
                self.corpus_chunk_count
            ),
            "query_terms": list(
                self.query_terms
            ),
            "hits": [
                hit.to_dict()
                for hit in self.hits
            ],
            "metadata": dict(self.metadata),
        }


class ChunkRetriever(ABC):
    """所有全文 chunk 检索器必须实现的接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """返回检索器稳定名称。"""

        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        """返回影响排名语义的版本号。"""

        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        *,
        query: str,
        chunks: Sequence[DocumentChunk],
        limit: int,
    ) -> ChunkSearchResult:
        """在给定候选 chunks 中执行全文检索。"""

        raise NotImplementedError
