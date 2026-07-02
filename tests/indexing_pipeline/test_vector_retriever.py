import pytest

from ai4research.indexing_pipeline.retrieval.vector import (
    CosineVectorRetriever,
    cosine_similarity,
)
from ai4research.indexing_pipeline.schemas.chunk_embedding import ChunkEmbedding


def _embedding(chunk_id: str, vector: tuple[float, ...]) -> ChunkEmbedding:
    return ChunkEmbedding(
        chunk_id=chunk_id,
        paper_id="paper-1",
        embedding_model="test-model",
        embedding_model_version="v1",
        embedding_dimension=len(vector),
        vector=vector,
        source_chunk_sha256="a" * 64,
    )


def test_cosine_similarity_known_values() -> None:
    assert cosine_similarity((1.0, 0.0), (1.0, 0.0)) == pytest.approx(1.0)
    assert cosine_similarity((1.0, 0.0), (0.0, 1.0)) == pytest.approx(0.0)
    assert cosine_similarity((1.0, 0.0), (-1.0, 0.0)) == pytest.approx(-1.0)


def test_vector_retriever_ranks_by_cosine_similarity() -> None:
    retriever = CosineVectorRetriever()
    embeddings = [
        _embedding("chunk-orthogonal", (0.0, 1.0)),
        _embedding("chunk-best", (1.0, 0.0)),
        _embedding("chunk-diagonal", (0.8, 0.2)),
    ]

    result = retriever.search(
        query_vector=(1.0, 0.0),
        embeddings=embeddings,
        top_k=2,
    )

    assert result.retriever_name == "cosine-vector-retriever"
    assert result.query_vector_dimension == 2
    assert result.corpus_embedding_count == 3
    assert [hit.embedding.chunk_id for hit in result.hits] == [
        "chunk-best",
        "chunk-diagonal",
    ]
    assert result.hits[0].rank == 1
    assert result.hits[0].score == pytest.approx(1.0)


def test_vector_retriever_rejects_dimension_mismatch() -> None:
    retriever = CosineVectorRetriever()

    with pytest.raises(ValueError, match="query vector dimension does not match"):
        retriever.search(
            query_vector=(1.0, 0.0),
            embeddings=[_embedding("chunk-1", (1.0, 0.0, 0.0))],
        )


def test_vector_retriever_rejects_non_positive_top_k() -> None:
    retriever = CosineVectorRetriever()

    with pytest.raises(ValueError, match="top_k must be positive"):
        retriever.search(
            query_vector=(1.0, 0.0),
            embeddings=[_embedding("chunk-1", (1.0, 0.0))],
            top_k=0,
        )
