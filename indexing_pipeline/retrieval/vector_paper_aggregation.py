"""把 vector chunk hits 聚合成论文级排序。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai4research.indexing_pipeline.retrieval.vector import VectorChunkHit


@dataclass(frozen=True)
class VectorPaperHit:
    rank: int
    paper_id: str
    score: float
    evidence: tuple[VectorChunkHit, ...]
    score_components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "paper_id": self.paper_id,
            "score": self.score,
            "score_components": self.score_components,
            "evidence": [hit.to_dict() for hit in self.evidence],
        }


@dataclass(frozen=True)
class VectorPaperSearchResult:
    query_vector_dimension: int
    chunk_hit_count: int
    matched_paper_count: int
    hits: tuple[VectorPaperHit, ...]
    aggregation_name: str = "vector-paper-aggregation"
    aggregation_version: str = "1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "aggregation_name": self.aggregation_name,
            "aggregation_version": self.aggregation_version,
            "query_vector_dimension": self.query_vector_dimension,
            "chunk_hit_count": self.chunk_hit_count,
            "matched_paper_count": self.matched_paper_count,
            "hits": [hit.to_dict() for hit in self.hits],
        }


@dataclass(frozen=True)
class VectorPaperAggregationConfig:
    final_paper_k: int = 5
    evidence_chunks_per_paper: int = 3
    top_chunks_for_score: int = 3
    best_chunk_weight: float = 0.7
    mean_top_chunk_weight: float = 0.3

    def validate(self) -> None:
        if self.final_paper_k <= 0:
            raise ValueError("final_paper_k must be positive")
        if self.evidence_chunks_per_paper <= 0:
            raise ValueError("evidence_chunks_per_paper must be positive")
        if self.top_chunks_for_score <= 0:
            raise ValueError("top_chunks_for_score must be positive")
        if self.best_chunk_weight < 0 or self.mean_top_chunk_weight < 0:
            raise ValueError("aggregation weights must be non-negative")
        if self.best_chunk_weight + self.mean_top_chunk_weight <= 0:
            raise ValueError("at least one aggregation weight must be positive")


class VectorPaperAggregator:
    """把 chunk 级 vector hit 聚合为 paper hit。"""

    def aggregate(
        self,
        *,
        query_vector_dimension: int,
        chunk_hits: tuple[VectorChunkHit, ...],
        config: VectorPaperAggregationConfig | None = None,
    ) -> VectorPaperSearchResult:
        effective_config = config or VectorPaperAggregationConfig()
        effective_config.validate()

        hits_by_paper: dict[str, list[VectorChunkHit]] = {}
        for hit in chunk_hits:
            paper_id = hit.embedding.paper_id
            hits_by_paper.setdefault(paper_id, []).append(hit)

        paper_items: list[tuple[float, str, tuple[VectorChunkHit, ...], dict[str, float]]] = []

        for paper_id, hits in hits_by_paper.items():
            sorted_hits = sorted(
                hits,
                key=lambda hit: (hit.score, -hit.rank),
                reverse=True,
            )
            scoring_hits = sorted_hits[: effective_config.top_chunks_for_score]
            evidence = tuple(sorted_hits[: effective_config.evidence_chunks_per_paper])

            best_chunk_score = scoring_hits[0].score
            mean_top_chunk_score = sum(hit.score for hit in scoring_hits) / len(scoring_hits)
            score = (
                effective_config.best_chunk_weight * best_chunk_score
                + effective_config.mean_top_chunk_weight * mean_top_chunk_score
            )

            components = {
                "best_chunk_score": best_chunk_score,
                "mean_top_chunk_score": mean_top_chunk_score,
                "scoring_chunk_count": float(len(scoring_hits)),
            }

            paper_items.append((score, paper_id, evidence, components))

        paper_items.sort(
            key=lambda item: (
                item[0],
                item[1],
            ),
            reverse=True,
        )

        paper_hits = tuple(
            VectorPaperHit(
                rank=index,
                paper_id=paper_id,
                score=score,
                evidence=evidence,
                score_components=components,
            )
            for index, (score, paper_id, evidence, components) in enumerate(
                paper_items[: effective_config.final_paper_k],
                start=1,
            )
        )

        return VectorPaperSearchResult(
            query_vector_dimension=query_vector_dimension,
            chunk_hit_count=len(chunk_hits),
            matched_paper_count=len(hits_by_paper),
            hits=paper_hits,
        )
