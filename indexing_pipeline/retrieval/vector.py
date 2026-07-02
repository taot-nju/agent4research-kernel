"""最小向量检索内核。

这个模块暂时不负责生成 embedding，只负责：

- 接收 query vector；
- 在 ChunkEmbedding corpus 中计算 cosine similarity；
- 返回 chunk 级排序结果。

这样我们可以先把 vector search 的检索/聚合/评估链路跑通，
后面再接真实 embedding 服务。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable

from ai4research.indexing_pipeline.schemas.chunk_embedding import (
    ChunkEmbedding,
    normalize_embedding_vector,
)


@dataclass(frozen=True)
class VectorChunkHit:
    rank: int
    score: float
    embedding: ChunkEmbedding
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "score": self.score,
            "embedding": self.embedding.to_dict(),
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class VectorChunkSearchResult:
    query_vector_dimension: int
    corpus_embedding_count: int
    hits: tuple[VectorChunkHit, ...]
    retriever_name: str = "cosine-vector-retriever"
    retriever_version: str = "1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "retriever_name": self.retriever_name,
            "retriever_version": self.retriever_version,
            "query_vector_dimension": self.query_vector_dimension,
            "corpus_embedding_count": self.corpus_embedding_count,
            "hits": [hit.to_dict() for hit in self.hits],
        }


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("cosine similarity requires vectors with the same dimension")

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))

    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0

    return dot / (left_norm * right_norm)


class CosineVectorRetriever:
    """基于 cosine similarity 的最小 chunk embedding retriever。"""

    retriever_name = "cosine-vector-retriever"
    retriever_version = "1"

    def search(
        self,
        *,
        query_vector: tuple[float, ...] | list[float],
        embeddings: Iterable[ChunkEmbedding],
        top_k: int = 10,
    ) -> VectorChunkSearchResult:
        normalized_query = normalize_embedding_vector(query_vector)

        if top_k <= 0:
            raise ValueError("top_k must be positive")

        scored: list[tuple[float, ChunkEmbedding]] = []
        embedding_count = 0

        for embedding in embeddings:
            embedding_count += 1
            if embedding.embedding_dimension != len(normalized_query):
                raise ValueError(
                    "query vector dimension does not match corpus embedding dimension"
                )

            scored.append(
                (
                    cosine_similarity(normalized_query, embedding.vector),
                    embedding,
                )
            )

        scored.sort(
            key=lambda item: (
                item[0],
                item[1].paper_id,
                item[1].chunk_id,
            ),
            reverse=True,
        )

        hits = tuple(
            VectorChunkHit(
                rank=index,
                score=score,
                embedding=embedding,
            )
            for index, (score, embedding) in enumerate(scored[:top_k], start=1)
        )

        return VectorChunkSearchResult(
            query_vector_dimension=len(normalized_query),
            corpus_embedding_count=embedding_count,
            hits=hits,
            retriever_name=self.retriever_name,
            retriever_version=self.retriever_version,
        )
