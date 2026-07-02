"""候选论文集合内的全文二次检索流程。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ai4research.indexing_pipeline.repositories.reader import (
    ChunkCorpusReader,
    ChunkCorpusReadRequest,
)
from ai4research.indexing_pipeline.retrieval.base import (
    ChunkRetriever,
    ChunkSearchResult,
)
from ai4research.indexing_pipeline.retrieval.paper_aggregation import (
    PaperScoreAggregator,
    PaperSearchResult,
)


RAW_SCORE_SEMANTICS = (
    "BM25 派生的原始排序分，无固定上限，"
    "不能跨查询或候选集合直接比较。"
)

RELATIVE_SCORE_SEMANTICS = (
    "仅在本次查询与候选集合内计算；"
    "最高论文为 100，其余为 raw_score / top_raw_score × 100；"
    "不是概率。"
)


@dataclass(frozen=True)
class CandidateFullTextSearchRequest:
    """候选论文集合内全文检索的标准输入。"""

    query: str
    candidate_paper_ids: tuple[str, ...]

    splitter_name: str
    splitter_version: str
    splitter_options: Mapping[str, Any]

    chunk_recall_limit: int = 300
    final_paper_limit: int = 5

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query 不能为空")

        if not self.candidate_paper_ids:
            raise ValueError(
                "candidate_paper_ids 不能为空"
            )

        if len(
            set(self.candidate_paper_ids)
        ) != len(self.candidate_paper_ids):
            raise ValueError(
                "candidate_paper_ids 不能重复"
            )

        if not self.splitter_name.strip():
            raise ValueError(
                "splitter_name 不能为空"
            )

        if not self.splitter_version.strip():
            raise ValueError(
                "splitter_version 不能为空"
            )

        if self.chunk_recall_limit <= 0:
            raise ValueError(
                "chunk_recall_limit 必须大于 0"
            )

        if self.final_paper_limit <= 0:
            raise ValueError(
                "final_paper_limit 必须大于 0"
            )


@dataclass(frozen=True)
class CandidateFullTextSearchResult:
    """候选论文集合内全文检索的标准结果。"""

    success: bool
    status: str
    query: str

    requested_paper_ids: tuple[str, ...]
    loaded_paper_ids: tuple[str, ...]
    missing_paper_ids: tuple[str, ...]

    chunk_search_result: (
        ChunkSearchResult | None
    ) = None
    paper_search_result: (
        PaperSearchResult | None
    ) = None

    relative_scores: Mapping[
        str,
        float,
    ] = field(default_factory=dict)
    manifest_relative_paths: Mapping[
        str,
        str,
    ] = field(default_factory=dict)
    errors: Mapping[
        str,
        str,
    ] = field(default_factory=dict)

    error: str = ""

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query 不能为空")

        if self.success and self.error:
            raise ValueError(
                "成功结果的 error 必须为空"
            )

        if not self.success and not self.error:
            raise ValueError(
                "失败结果必须提供 error"
            )

        if self.success:
            if self.chunk_search_result is None:
                raise ValueError(
                    "成功结果缺少 chunk 检索结果"
                )

            if self.paper_search_result is None:
                raise ValueError(
                    "成功结果缺少论文聚合结果"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "query": self.query,
            "requested_paper_ids": list(
                self.requested_paper_ids
            ),
            "loaded_paper_ids": list(
                self.loaded_paper_ids
            ),
            "missing_paper_ids": list(
                self.missing_paper_ids
            ),
            "chunk_search_result": (
                self.chunk_search_result.to_dict()
                if self.chunk_search_result
                else None
            ),
            "paper_search_result": (
                self.paper_search_result.to_dict()
                if self.paper_search_result
                else None
            ),
            "relative_scores": dict(
                self.relative_scores
            ),
            "score_semantics": {
                "raw_score": (
                    RAW_SCORE_SEMANTICS
                ),
                "relative_score": (
                    RELATIVE_SCORE_SEMANTICS
                ),
            },
            "manifest_relative_paths": dict(
                self.manifest_relative_paths
            ),
            "errors": dict(self.errors),
            "error": self.error,
        }


def _build_relative_scores(
    paper_result: PaperSearchResult,
) -> dict[str, float]:
    if not paper_result.hits:
        return {}

    top_score = paper_result.hits[0].score

    if top_score <= 0:
        return {
            hit.paper_id: 0.0
            for hit in paper_result.hits
        }

    return {
        hit.paper_id: (
            hit.score / top_score * 100.0
        )
        for hit in paper_result.hits
    }


def search_candidate_fulltext(
    *,
    request: CandidateFullTextSearchRequest,
    corpus_reader: ChunkCorpusReader,
    chunk_retriever: ChunkRetriever,
    paper_aggregator: PaperScoreAggregator,
) -> CandidateFullTextSearchResult:
    """加载候选 chunk、执行 BM25 并聚合论文。"""

    try:
        corpus = corpus_reader.read(
            ChunkCorpusReadRequest(
                paper_ids=(
                    request.candidate_paper_ids
                ),
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
        )

        if not corpus.chunks:
            return CandidateFullTextSearchResult(
                success=False,
                status="no_ready_chunks",
                query=request.query,
                requested_paper_ids=(
                    request.candidate_paper_ids
                ),
                loaded_paper_ids=(
                    corpus.loaded_paper_ids
                ),
                missing_paper_ids=(
                    corpus.missing_paper_ids
                ),
                manifest_relative_paths=(
                    corpus.manifest_relative_paths
                ),
                errors=corpus.errors,
                error=(
                    "候选论文中没有可用 chunk 资产"
                ),
            )

        effective_chunk_limit = min(
            request.chunk_recall_limit,
            corpus.chunk_count,
        )

        chunk_result = (
            chunk_retriever.search(
                query=request.query,
                chunks=corpus.chunks,
                limit=effective_chunk_limit,
            )
        )

        paper_result = (
            paper_aggregator.aggregate(
                chunk_result=chunk_result,
                limit=request.final_paper_limit,
            )
        )

        status = (
            "complete"
            if corpus.complete
            else "partial"
        )

        return CandidateFullTextSearchResult(
            success=True,
            status=status,
            query=request.query,
            requested_paper_ids=(
                request.candidate_paper_ids
            ),
            loaded_paper_ids=(
                corpus.loaded_paper_ids
            ),
            missing_paper_ids=(
                corpus.missing_paper_ids
            ),
            chunk_search_result=chunk_result,
            paper_search_result=paper_result,
            relative_scores=(
                _build_relative_scores(
                    paper_result
                )
            ),
            manifest_relative_paths=(
                corpus.manifest_relative_paths
            ),
            errors=corpus.errors,
        )

    except Exception as error:
        return CandidateFullTextSearchResult(
            success=False,
            status="failed",
            query=request.query,
            requested_paper_ids=(
                request.candidate_paper_ids
            ),
            loaded_paper_ids=(),
            missing_paper_ids=(
                request.candidate_paper_ids
            ),
            error=(
                f"{type(error).__name__}: "
                f"{error}"
            )[:4000],
        )
