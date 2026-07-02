"""Hybrid evidence 的 rerank 候选构造与论文级聚合。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RerankSegment:
    """一条可提交给 rerank 服务的文本片段。"""

    paper_id: str
    source_chunk_id: str
    segment_id: str
    segment_index: int
    segment_count: int
    char_start: int
    char_end: int
    text: str
    chunk: Mapping[str, Any]
    sources: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.paper_id:
            raise ValueError("paper_id 不能为空")

        if not self.source_chunk_id:
            raise ValueError(
                "source_chunk_id 不能为空"
            )

        if not self.segment_id:
            raise ValueError(
                "segment_id 不能为空"
            )

        if self.segment_index < 0:
            raise ValueError(
                "segment_index 不能小于 0"
            )

        if self.segment_count <= 0:
            raise ValueError(
                "segment_count 必须大于 0"
            )

        if (
            self.char_start < 0
            or self.char_end <= self.char_start
        ):
            raise ValueError(
                "char_start / char_end 不合法"
            )

        if not self.text:
            raise ValueError("text 不能为空")

        if not self.sources:
            raise ValueError("sources 不能为空")


@dataclass(frozen=True)
class ScoredRerankSegment:
    """带 rerank 相关性分数的片段。"""

    segment: RerankSegment
    relevance_score: float


@dataclass(frozen=True)
class RerankedPaper:
    """由最高分的不同原始 chunk 聚合出的论文结果。"""

    paper_id: str
    score: float
    evidence: tuple[ScoredRerankSegment, ...]


def split_text_into_segments(
    *,
    text: str,
    max_chars: int,
    overlap_chars: int,
) -> tuple[tuple[int, int, str], ...]:
    """按字符切分文本，确保超长文本不会被截断丢弃。"""

    if not text:
        raise ValueError("text 不能为空")

    if max_chars <= 0:
        raise ValueError(
            "max_chars 必须大于 0"
        )

    if overlap_chars < 0:
        raise ValueError(
            "overlap_chars 不能小于 0"
        )

    if overlap_chars >= max_chars:
        raise ValueError(
            "overlap_chars 必须小于 max_chars"
        )

    segments: list[tuple[int, int, str]] = []
    start = 0
    step = max_chars - overlap_chars

    while start < len(text):
        end = min(
            start + max_chars,
            len(text),
        )
        segments.append(
            (start, end, text[start:end])
        )

        if end == len(text):
            break

        start += step

    return tuple(segments)


def _segment_id(
    *,
    source_chunk_id: str,
    segment_index: int,
    segment_count: int,
) -> str:
    if segment_count == 1:
        return source_chunk_id

    return (
        f"{source_chunk_id}"
        f"::rerank-segment-{segment_index:04d}"
    )


def build_rerank_segments(
    *,
    hybrid_result: Mapping[str, Any],
    candidate_paper_k: int,
    subchunk_max_chars: int,
    subchunk_overlap_chars: int,
) -> tuple[RerankSegment, ...]:
    """从 hybrid paper ranking 展开、去重并构造 rerank 片段。"""

    if candidate_paper_k <= 0:
        raise ValueError(
            "candidate_paper_k 必须大于 0"
        )

    paper_result = hybrid_result.get(
        "paper_search_result"
    )

    if not isinstance(paper_result, Mapping):
        raise ValueError(
            "hybrid result 缺少 paper_search_result"
        )

    paper_hits = paper_result.get("hits")

    if not isinstance(paper_hits, list):
        raise ValueError(
            "paper_search_result.hits 必须是 list"
        )

    segments: list[RerankSegment] = []

    for paper_hit in paper_hits[
        :candidate_paper_k
    ]:
        if not isinstance(paper_hit, Mapping):
            raise ValueError(
                "hybrid paper hit 必须是 object"
            )

        paper_id = str(
            paper_hit.get("paper_id", "")
        ).strip()

        if not paper_id:
            raise ValueError(
                "hybrid paper hit 缺少 paper_id"
            )

        wrappers = paper_hit.get("evidence")

        if not isinstance(wrappers, list):
            raise ValueError(
                "hybrid paper hit 缺少 evidence list"
            )

        chunks: dict[
            str,
            dict[str, Any],
        ] = {}

        for wrapper in wrappers:
            if not isinstance(wrapper, Mapping):
                raise ValueError(
                    "hybrid evidence wrapper 必须是 object"
                )

            source = str(
                wrapper.get("source", "")
            ).strip()

            if not source:
                raise ValueError(
                    "hybrid evidence wrapper 缺少 source"
                )

            source_hit = wrapper.get("hit")

            if not isinstance(source_hit, Mapping):
                raise ValueError(
                    "hybrid evidence wrapper 缺少 hit"
                )

            source_evidence = source_hit.get(
                "evidence"
            )

            if not isinstance(
                source_evidence,
                list,
            ):
                raise ValueError(
                    "source paper hit 缺少 evidence list"
                )

            for evidence in source_evidence:
                if not isinstance(
                    evidence,
                    Mapping,
                ):
                    raise ValueError(
                        "source evidence 必须是 object"
                    )

                chunk = evidence.get("chunk")

                if not isinstance(chunk, Mapping):
                    raise ValueError(
                        "source evidence 缺少 chunk"
                    )

                chunk_id = str(
                    chunk.get("chunk_id", "")
                ).strip()
                text = str(
                    chunk.get("text", "")
                )

                if not chunk_id or not text:
                    raise ValueError(
                        "source chunk 必须包含 "
                        "chunk_id 与 text"
                    )

                existing = chunks.get(chunk_id)

                if existing is None:
                    chunks[chunk_id] = {
                        "chunk": dict(chunk),
                        "sources": [source],
                    }
                    continue

                existing_text = str(
                    existing["chunk"].get("text", "")
                )

                if existing_text != text:
                    raise ValueError(
                        "相同 chunk_id 的文本不一致"
                    )

                if source not in existing["sources"]:
                    existing["sources"].append(source)

        for source_chunk_id, item in chunks.items():
            chunk = item["chunk"]
            text = str(chunk["text"])
            text_segments = split_text_into_segments(
                text=text,
                max_chars=subchunk_max_chars,
                overlap_chars=subchunk_overlap_chars,
            )
            segment_count = len(text_segments)

            for (
                segment_index,
                (char_start, char_end, segment_text),
            ) in enumerate(text_segments):
                segments.append(
                    RerankSegment(
                        paper_id=paper_id,
                        source_chunk_id=source_chunk_id,
                        segment_id=_segment_id(
                            source_chunk_id=(
                                source_chunk_id
                            ),
                            segment_index=segment_index,
                            segment_count=segment_count,
                        ),
                        segment_index=segment_index,
                        segment_count=segment_count,
                        char_start=char_start,
                        char_end=char_end,
                        text=segment_text,
                        chunk=chunk,
                        sources=tuple(item["sources"]),
                    )
                )

    return tuple(segments)


def aggregate_reranked_segments(
    *,
    scored_segments: Sequence[ScoredRerankSegment],
    top_source_chunks_for_score: int,
) -> tuple[RerankedPaper, ...]:
    """先取每个原始 chunk 的最佳片段，再聚合为论文级得分。"""

    if top_source_chunks_for_score <= 0:
        raise ValueError(
            "top_source_chunks_for_score "
            "必须大于 0"
        )

    best_by_paper_and_chunk: dict[
        str,
        dict[str, ScoredRerankSegment],
    ] = defaultdict(dict)

    for scored in scored_segments:
        paper_id = scored.segment.paper_id
        source_chunk_id = (
            scored.segment.source_chunk_id
        )
        existing = best_by_paper_and_chunk[
            paper_id
        ].get(source_chunk_id)

        if existing is None or (
            scored.relevance_score,
            scored.segment.segment_id,
        ) > (
            existing.relevance_score,
            existing.segment.segment_id,
        ):
            best_by_paper_and_chunk[
                paper_id
            ][source_chunk_id] = scored

    papers: list[RerankedPaper] = []

    for paper_id, by_chunk in (
        best_by_paper_and_chunk.items()
    ):
        evidence = sorted(
            by_chunk.values(),
            key=lambda item: (
                -item.relevance_score,
                item.segment.segment_id,
            ),
        )[:top_source_chunks_for_score]

        score = sum(
            item.relevance_score
            for item in evidence
        ) / len(evidence)

        papers.append(
            RerankedPaper(
                paper_id=paper_id,
                score=score,
                evidence=tuple(evidence),
            )
        )

    return tuple(
        sorted(
            papers,
            key=lambda item: (
                -item.score,
                item.paper_id,
            ),
        )
    )
