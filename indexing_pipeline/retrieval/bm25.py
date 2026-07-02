"""候选论文集合内的 chunk BM25 全文检索。"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from ai4research.indexing_pipeline.retrieval.base import (
    ChunkRetriever,
    ChunkSearchHit,
    ChunkSearchResult,
)
from ai4research.indexing_pipeline.schemas.document_chunk import (
    DocumentChunk,
)


RETRIEVER_NAME = "bm25-chunk-retriever"
RETRIEVER_VERSION = "1"

_TOKEN_PATTERN = re.compile(
    r"[a-z0-9]+(?:'[a-z0-9]+)?",
    re.IGNORECASE,
)

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
}


@dataclass(frozen=True)
class BM25ChunkRetrieverConfig:
    """BM25 参数与章节词增强配置。"""

    k1: float = 1.5
    b: float = 0.75
    section_term_multiplier: int = 2

    def __post_init__(self) -> None:
        if self.k1 <= 0:
            raise ValueError("k1 必须大于 0")

        if not 0 <= self.b <= 1:
            raise ValueError(
                "b 必须位于 [0, 1]"
            )

        if self.section_term_multiplier < 0:
            raise ValueError(
                "section_term_multiplier "
                "不能小于 0"
            )

    def to_dict(self) -> dict:
        return {
            "k1": self.k1,
            "b": self.b,
            "section_term_multiplier": (
                self.section_term_multiplier
            ),
        }


def tokenize_for_retrieval(
    text: str,
) -> tuple[str, ...]:
    """提取英文和数字检索词项。"""

    if not isinstance(text, str):
        raise TypeError("text 必须是字符串")

    tokens = [
        match.group(0).lower()
        for match in _TOKEN_PATTERN.finditer(
            text
        )
    ]

    meaningful_tokens = [
        token
        for token in tokens
        if token not in STOPWORDS
        and len(token) >= 2
    ]

    return tuple(
        meaningful_tokens
        if meaningful_tokens
        else tokens
    )


def _chunk_tokens(
    *,
    chunk: DocumentChunk,
    section_term_multiplier: int,
) -> tuple[str, ...]:
    tokens = list(
        tokenize_for_retrieval(
            chunk.text
        )
    )

    if section_term_multiplier > 0:
        section_tokens = (
            tokenize_for_retrieval(
                " ".join(
                    chunk.section_path
                )
            )
        )
        tokens.extend(
            section_tokens
            * section_term_multiplier
        )

    return tuple(tokens)


class BM25ChunkRetriever(ChunkRetriever):
    """对传入的候选 chunks 即时计算 BM25。"""

    def __init__(
        self,
        config: (
            BM25ChunkRetrieverConfig | None
        ) = None,
    ) -> None:
        self._config = (
            config
            or BM25ChunkRetrieverConfig()
        )

    @property
    def name(self) -> str:
        return RETRIEVER_NAME

    @property
    def version(self) -> str:
        return RETRIEVER_VERSION

    @property
    def config(self) -> (
        BM25ChunkRetrieverConfig
    ):
        return self._config

    def search(
        self,
        *,
        query: str,
        chunks: Sequence[DocumentChunk],
        limit: int,
    ) -> ChunkSearchResult:
        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError("query 不能为空")

        if limit <= 0:
            raise ValueError(
                "limit 必须大于 0"
            )

        query_terms = tuple(
            dict.fromkeys(
                tokenize_for_retrieval(
                    normalized_query
                )
            )
        )

        if not query_terms:
            raise ValueError(
                "query 不包含可检索词项"
            )

        corpus_chunks = tuple(chunks)
        paper_count = len(
            {
                chunk.paper_id
                for chunk in corpus_chunks
            }
        )

        if not corpus_chunks:
            return ChunkSearchResult(
                query=normalized_query,
                retriever_name=self.name,
                retriever_version=self.version,
                corpus_paper_count=0,
                corpus_chunk_count=0,
                query_terms=query_terms,
                hits=(),
                metadata={
                    **self._config.to_dict(),
                    "average_document_length": 0.0,
                },
            )

        tokenized_documents = [
            _chunk_tokens(
                chunk=chunk,
                section_term_multiplier=(
                    self._config
                    .section_term_multiplier
                ),
            )
            for chunk in corpus_chunks
        ]

        document_lengths = [
            len(tokens)
            for tokens in tokenized_documents
        ]
        average_document_length = (
            sum(document_lengths)
            / len(document_lengths)
        )

        document_frequencies = {
            term: sum(
                term in set(tokens)
                for tokens
                in tokenized_documents
            )
            for term in query_terms
        }

        corpus_size = len(corpus_chunks)

        inverse_document_frequencies = {
            term: math.log(
                1.0
                + (
                    corpus_size
                    - document_frequencies[term]
                    + 0.5
                )
                / (
                    document_frequencies[term]
                    + 0.5
                )
            )
            for term in query_terms
        }

        scored_chunks = []

        for chunk, tokens, document_length in zip(
            corpus_chunks,
            tokenized_documents,
            document_lengths,
        ):
            term_frequencies = Counter(tokens)
            score = 0.0
            matched_terms = []

            length_normalization = (
                1.0
                - self._config.b
                + self._config.b
                * document_length
                / average_document_length
            )

            for term in query_terms:
                term_frequency = (
                    term_frequencies.get(
                        term,
                        0,
                    )
                )

                if term_frequency <= 0:
                    continue

                matched_terms.append(term)

                numerator = (
                    term_frequency
                    * (self._config.k1 + 1.0)
                )
                denominator = (
                    term_frequency
                    + self._config.k1
                    * length_normalization
                )

                score += (
                    inverse_document_frequencies[
                        term
                    ]
                    * numerator
                    / denominator
                )

            if score <= 0:
                continue

            coverage = (
                len(matched_terms)
                / len(query_terms)
            )

            scored_chunks.append(
                (
                    score,
                    coverage,
                    chunk,
                    tuple(matched_terms),
                )
            )

        scored_chunks.sort(
            key=lambda item: (
                -item[0],
                -item[1],
                item[2].paper_id,
                item[2].chunk_index,
                item[2].chunk_id,
            )
        )

        hits = tuple(
            ChunkSearchHit(
                rank=rank,
                score=score,
                chunk=chunk,
                matched_terms=matched_terms,
                score_components={
                    "bm25": score,
                    "term_coverage": coverage,
                    "matched_term_count": float(
                        len(matched_terms)
                    ),
                },
            )
            for rank, (
                score,
                coverage,
                chunk,
                matched_terms,
            ) in enumerate(
                scored_chunks[:limit],
                start=1,
            )
        )

        return ChunkSearchResult(
            query=normalized_query,
            retriever_name=self.name,
            retriever_version=self.version,
            corpus_paper_count=paper_count,
            corpus_chunk_count=corpus_size,
            query_terms=query_terms,
            hits=hits,
            metadata={
                **self._config.to_dict(),
                "average_document_length": (
                    average_document_length
                ),
                "document_frequencies": (
                    document_frequencies
                ),
                "inverse_document_frequencies": (
                    inverse_document_frequencies
                ),
            },
        )
