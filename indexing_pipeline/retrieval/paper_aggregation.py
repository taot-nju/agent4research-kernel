"""将 chunk 检索结果聚合为论文级排名。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from ai4research.indexing_pipeline.retrieval.base import (
    ChunkSearchHit,
    ChunkSearchResult,
)


@dataclass(frozen=True)
class PaperAggregationConfig:
    """论文级评分与证据数量配置。"""

    top_chunks_for_score: int = 3
    evidence_chunks_per_paper: int = 3

    mean_score_weight: float = 0.5
    coverage_weight: float = 0.5

    def __post_init__(self) -> None:
        if self.top_chunks_for_score <= 0:
            raise ValueError(
                "top_chunks_for_score 必须大于 0"
            )

        if self.evidence_chunks_per_paper <= 0:
            raise ValueError(
                "evidence_chunks_per_paper "
                "必须大于 0"
            )

        if self.mean_score_weight < 0:
            raise ValueError(
                "mean_score_weight 不能小于 0"
            )

        if self.coverage_weight < 0:
            raise ValueError(
                "coverage_weight 不能小于 0"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "top_chunks_for_score": (
                self.top_chunks_for_score
            ),
            "evidence_chunks_per_paper": (
                self.evidence_chunks_per_paper
            ),
            "mean_score_weight": (
                self.mean_score_weight
            ),
            "coverage_weight": (
                self.coverage_weight
            ),
        }


@dataclass(frozen=True)
class PaperSearchHit:
    """论文级命中及其最佳原文证据。"""

    rank: int
    paper_id: str
    score: float

    evidence: tuple[ChunkSearchHit, ...]
    matched_terms: tuple[str, ...]

    score_components: Mapping[
        str,
        float,
    ] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.rank <= 0:
            raise ValueError(
                "rank 必须是正整数"
            )

        if not self.paper_id.strip():
            raise ValueError(
                "paper_id 不能为空"
            )

        if self.score < 0:
            raise ValueError(
                "score 不能小于 0"
            )

        if not self.evidence:
            raise ValueError(
                "evidence 不能为空"
            )

        if any(
            hit.chunk.paper_id
            != self.paper_id
            for hit in self.evidence
        ):
            raise ValueError(
                "证据 chunk 必须属于当前论文"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "paper_id": self.paper_id,
            "score": self.score,
            "matched_terms": list(
                self.matched_terms
            ),
            "score_components": dict(
                self.score_components
            ),
            "evidence": [
                hit.to_dict()
                for hit in self.evidence
            ],
        }


@dataclass(frozen=True)
class PaperSearchResult:
    """论文级全文检索结果。"""

    query: str
    chunk_retriever_name: str
    chunk_retriever_version: str

    corpus_paper_count: int
    corpus_chunk_count: int
    matched_paper_count: int

    query_terms: tuple[str, ...]
    hits: tuple[PaperSearchHit, ...]

    aggregation_config: Mapping[
        str,
        Any,
    ] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError(
                "query 不能为空"
            )

        if self.matched_paper_count < 0:
            raise ValueError(
                "matched_paper_count 不能小于 0"
            )

        for expected_rank, hit in enumerate(
            self.hits,
            start=1,
        ):
            if hit.rank != expected_rank:
                raise ValueError(
                    "paper rank 必须从 1 连续递增"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "chunk_retriever_name": (
                self.chunk_retriever_name
            ),
            "chunk_retriever_version": (
                self.chunk_retriever_version
            ),
            "corpus_paper_count": (
                self.corpus_paper_count
            ),
            "corpus_chunk_count": (
                self.corpus_chunk_count
            ),
            "matched_paper_count": (
                self.matched_paper_count
            ),
            "query_terms": list(
                self.query_terms
            ),
            "hits": [
                hit.to_dict()
                for hit in self.hits
            ],
            "aggregation_config": dict(
                self.aggregation_config
            ),
        }


class PaperScoreAggregator:
    """用最佳 chunk、Top-K 均值和词项覆盖率聚合论文。"""

    def __init__(
        self,
        config: (
            PaperAggregationConfig | None
        ) = None,
    ) -> None:
        self._config = (
            config
            or PaperAggregationConfig()
        )

    @property
    def config(self) -> (
        PaperAggregationConfig
    ):
        return self._config

    def aggregate(
        self,
        *,
        chunk_result: ChunkSearchResult,
        limit: int,
    ) -> PaperSearchResult:
        if limit <= 0:
            raise ValueError(
                "limit 必须大于 0"
            )

        grouped_hits: dict[
            str,
            list[ChunkSearchHit],
        ] = defaultdict(list)

        for hit in chunk_result.hits:
            grouped_hits[
                hit.chunk.paper_id
            ].append(hit)

        scored_papers = []

        for paper_id, paper_hits in (
            grouped_hits.items()
        ):
            ordered_hits = sorted(
                paper_hits,
                key=lambda hit: (
                    -hit.score,
                    hit.rank,
                    hit.chunk.chunk_index,
                ),
            )

            scoring_hits = ordered_hits[
                :self._config
                .top_chunks_for_score
            ]
            evidence_hits = ordered_hits[
                :self._config
                .evidence_chunks_per_paper
            ]

            best_chunk_score = (
                scoring_hits[0].score
            )
            mean_top_chunk_score = mean(
                hit.score
                for hit in scoring_hits
            )

            matched_term_set = {
                term
                for hit in scoring_hits
                for term in hit.matched_terms
            }

            query_term_count = len(
                chunk_result.query_terms
            )
            query_coverage = (
                len(matched_term_set)
                / query_term_count
                if query_term_count
                else 0.0
            )

            paper_score = (
                best_chunk_score
                + self._config
                .mean_score_weight
                * mean_top_chunk_score
                + self._config
                .coverage_weight
                * query_coverage
            )

            scored_papers.append(
                {
                    "paper_id": paper_id,
                    "score": paper_score,
                    "evidence": tuple(
                        evidence_hits
                    ),
                    "matched_terms": tuple(
                        term
                        for term
                        in chunk_result.query_terms
                        if term
                        in matched_term_set
                    ),
                    "score_components": {
                        "best_chunk_score": (
                            best_chunk_score
                        ),
                        "mean_top_chunk_score": (
                            mean_top_chunk_score
                        ),
                        "query_coverage": (
                            query_coverage
                        ),
                        "scoring_chunk_count": (
                            float(
                                len(scoring_hits)
                            )
                        ),
                    },
                }
            )

        scored_papers.sort(
            key=lambda item: (
                -item["score"],
                item["paper_id"],
            )
        )

        paper_hits = tuple(
            PaperSearchHit(
                rank=rank,
                paper_id=item["paper_id"],
                score=item["score"],
                evidence=item["evidence"],
                matched_terms=(
                    item["matched_terms"]
                ),
                score_components=(
                    item["score_components"]
                ),
            )
            for rank, item in enumerate(
                scored_papers[:limit],
                start=1,
            )
        )

        return PaperSearchResult(
            query=chunk_result.query,
            chunk_retriever_name=(
                chunk_result.retriever_name
            ),
            chunk_retriever_version=(
                chunk_result.retriever_version
            ),
            corpus_paper_count=(
                chunk_result.corpus_paper_count
            ),
            corpus_chunk_count=(
                chunk_result.corpus_chunk_count
            ),
            matched_paper_count=len(
                grouped_hits
            ),
            query_terms=(
                chunk_result.query_terms
            ),
            hits=paper_hits,
            aggregation_config=(
                self._config.to_dict()
            ),
        )
