from ai4research.indexing_pipeline.reranking import (
    ScoredRerankSegment,
    aggregate_reranked_segments,
    build_rerank_segments,
)


def _chunk(chunk_id: str, text: str) -> dict[str, str]:
    return {
        "chunk_id": chunk_id,
        "paper_id": "paper-001",
        "text": text,
    }


def _hybrid_result() -> dict:
    repeated_chunk = _chunk("chunk-a", "abc")
    long_chunk = _chunk("chunk-b", "abcdefghij")

    return {
        "paper_search_result": {
            "hits": [
                {
                    "paper_id": "paper-001",
                    "evidence": [
                        {
                            "source": "bm25",
                            "hit": {
                                "evidence": [
                                    {"chunk": repeated_chunk},
                                    {"chunk": long_chunk},
                                ]
                            },
                        },
                        {
                            "source": "bge-m3",
                            "hit": {
                                "evidence": [
                                    {"chunk": repeated_chunk},
                                ]
                            },
                        },
                    ],
                }
            ]
        }
    }


def test_build_rerank_segments_deduplicates_and_splits() -> None:
    segments = build_rerank_segments(
        hybrid_result=_hybrid_result(),
        candidate_paper_k=1,
        subchunk_max_chars=4,
        subchunk_overlap_chars=1,
    )

    assert [segment.segment_id for segment in segments] == [
        "chunk-a",
        "chunk-b::rerank-segment-0000",
        "chunk-b::rerank-segment-0001",
        "chunk-b::rerank-segment-0002",
    ]
    assert segments[0].sources == ("bm25", "bge-m3")
    assert [
        (segment.char_start, segment.char_end, segment.text)
        for segment in segments[1:]
    ] == [
        (0, 4, "abcd"),
        (3, 7, "defg"),
        (6, 10, "ghij"),
    ]


def test_aggregate_reranked_segments_uses_best_segment_per_chunk() -> None:
    segments = build_rerank_segments(
        hybrid_result=_hybrid_result(),
        candidate_paper_k=1,
        subchunk_max_chars=4,
        subchunk_overlap_chars=1,
    )
    by_id = {
        segment.segment_id: segment
        for segment in segments
    }

    papers = aggregate_reranked_segments(
        scored_segments=[
            ScoredRerankSegment(
                segment=by_id["chunk-a"],
                relevance_score=0.7,
            ),
            ScoredRerankSegment(
                segment=by_id[
                    "chunk-b::rerank-segment-0000"
                ],
                relevance_score=0.1,
            ),
            ScoredRerankSegment(
                segment=by_id[
                    "chunk-b::rerank-segment-0001"
                ],
                relevance_score=0.9,
            ),
            ScoredRerankSegment(
                segment=by_id[
                    "chunk-b::rerank-segment-0002"
                ],
                relevance_score=0.8,
            ),
        ],
        top_source_chunks_for_score=2,
    )

    assert len(papers) == 1
    assert papers[0].paper_id == "paper-001"
    assert papers[0].score == 0.8
    assert [
        item.segment.source_chunk_id
        for item in papers[0].evidence
    ] == ["chunk-b", "chunk-a"]
