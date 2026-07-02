import subprocess
import sys
from argparse import Namespace

from ai4research.indexing_pipeline.reranking import (
    ScoredRerankSegment,
)
from ai4research.indexing_pipeline.scripts_py import (
    rerank_hybrid_candidates,
)


def _hybrid_result() -> dict:
    return {
        "query": "agent memory trajectory",
        "requested_paper_ids": ["paper-001", "paper-002"],
        "loaded_paper_ids": ["paper-001", "paper-002"],
        "missing_paper_ids": [],
        "paper_search_result": {
            "hits": [
                {
                    "rank": 1,
                    "paper_id": "paper-001",
                    "evidence": [
                        {
                            "source": "bm25",
                            "hit": {
                                "evidence": [
                                    {
                                        "chunk": {
                                            "chunk_id": "chunk-001",
                                            "paper_id": "paper-001",
                                            "text": "agent memory trajectory",
                                        }
                                    }
                                ]
                            },
                        }
                    ],
                },
                {
                    "rank": 2,
                    "paper_id": "paper-002",
                    "evidence": [
                        {
                            "source": "bm25",
                            "hit": {
                                "evidence": [
                                    {
                                        "chunk": {
                                            "chunk_id": "chunk-002",
                                            "paper_id": "paper-002",
                                            "text": "image compression",
                                        }
                                    }
                                ]
                            },
                        }
                    ],
                },
            ]
        },
    }


def _args() -> Namespace:
    return Namespace(
        base_url="http://127.0.0.1:7000/v1",
        api_key="EMPTY",
        model="bge-m3",
        candidate_paper_k=2,
        final_paper_k=2,
        subchunk_max_chars=3200,
        subchunk_overlap_chars=200,
        top_source_chunks_for_score=1,
        rerank_batch_size=16,
        timeout_seconds=60,
        preview_chars=80,
    )


def test_rerank_hybrid_candidates_cli_help() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py."
            "rerank_hybrid_candidates",
            "--help",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "rerank_hybrid_candidates.py" in completed.stdout
    assert "--hybrid-result" in completed.stdout
    assert "--subchunk-max-chars" in completed.stdout
    assert "--rerank-batch-size" in completed.stdout
    assert "--save-json" in completed.stdout


def test_build_result_returns_paper_ranking(
    monkeypatch,
) -> None:
    def fake_score_segments(**kwargs):
        scores = {
            "paper-001": 0.9,
            "paper-002": 0.2,
        }
        return tuple(
            ScoredRerankSegment(
                segment=segment,
                relevance_score=scores[segment.paper_id],
            )
            for segment in kwargs["segments"]
        )

    monkeypatch.setattr(
        rerank_hybrid_candidates,
        "_score_segments",
        fake_score_segments,
    )

    result = rerank_hybrid_candidates.build_result(
        hybrid_result=_hybrid_result(),
        args=_args(),
    )

    paper_result = result["paper_search_result"]

    assert result["success"] is True
    assert result["query"] == "agent memory trajectory"
    assert paper_result["chunk_retriever_name"] == (
        "openai-compatible-rerank"
    )
    assert [
        hit["paper_id"]
        for hit in paper_result["hits"]
    ] == ["paper-001", "paper-002"]
    assert paper_result["hits"][0]["evidence"][0][
        "rerank"
    ]["source_chunk_id"] == "chunk-001"
