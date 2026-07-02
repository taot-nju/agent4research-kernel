import pytest

from ai4research.indexing_pipeline.retrieval.vector import VectorChunkHit
from ai4research.indexing_pipeline.retrieval.vector_paper_aggregation import (
    VectorPaperAggregationConfig,
    VectorPaperAggregator,
)
from ai4research.indexing_pipeline.schemas.chunk_embedding import ChunkEmbedding


def _embedding(
    *,
    chunk_id: str,
    paper_id: str,
) -> ChunkEmbedding:
    return ChunkEmbedding(
        chunk_id=chunk_id,
        paper_id=paper_id,
        embedding_model="test-model",
        embedding_model_version="v1",
        embedding_dimension=2,
        vector=(1.0, 0.0),
        source_chunk_sha256="a" * 64,
    )


def _hit(
    *,
    rank: int,
    score: float,
    paper_id: str,
    chunk_id: str,
) -> VectorChunkHit:
    return VectorChunkHit(
        rank=rank,
        score=score,
        embedding=_embedding(
            chunk_id=chunk_id,
            paper_id=paper_id,
        ),
    )


def test_vector_paper_aggregator_ranks_papers_and_keeps_evidence() -> None:
    aggregator = VectorPaperAggregator()
    chunk_hits = (
        _hit(rank=1, score=0.90, paper_id="paper-a", chunk_id="a-1"),
        _hit(rank=2, score=0.80, paper_id="paper-b", chunk_id="b-1"),
        _hit(rank=3, score=0.70, paper_id="paper-a", chunk_id="a-2"),
        _hit(rank=4, score=0.60, paper_id="paper-c", chunk_id="c-1"),
    )

    result = aggregator.aggregate(
        query_vector_dimension=2,
        chunk_hits=chunk_hits,
        config=VectorPaperAggregationConfig(
            final_paper_k=2,
            evidence_chunks_per_paper=2,
            top_chunks_for_score=2,
            best_chunk_weight=0.5,
            mean_top_chunk_weight=0.5,
        ),
    )

    assert result.query_vector_dimension == 2
    assert result.chunk_hit_count == 4
    assert result.matched_paper_count == 3
    assert [hit.paper_id for hit in result.hits] == ["paper-a", "paper-b"]

    paper_a = result.hits[0]
    assert paper_a.rank == 1
    assert paper_a.score == pytest.approx(0.85)
    assert paper_a.score_components["best_chunk_score"] == pytest.approx(0.90)
    assert paper_a.score_components["mean_top_chunk_score"] == pytest.approx(0.80)
    assert [hit.embedding.chunk_id for hit in paper_a.evidence] == ["a-1", "a-2"]


def test_vector_paper_aggregator_validates_config() -> None:
    config = VectorPaperAggregationConfig(final_paper_k=0)

    with pytest.raises(ValueError, match="final_paper_k must be positive"):
        config.validate()
