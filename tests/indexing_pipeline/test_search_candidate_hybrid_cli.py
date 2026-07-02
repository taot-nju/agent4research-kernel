import subprocess
import sys
from argparse import Namespace

from ai4research.indexing_pipeline.scripts_py import (
    search_candidate_hybrid,
)


def _args() -> Namespace:
    return Namespace(
        query="agent memory trajectory",
        paper_id=["paper-001", "paper-002", "paper-001"],
        data_root="/data/ai4research_assets",
        target_chars=2400,
        max_chars=3200,
        overlap_chars=300,
        min_chars_before_heading_break=800,
        chunk_recall_k=300,
        final_paper_k=5,
        evidence_chunks_per_paper=3,
        top_chunks_for_score=3,
        bm25_k1=1.5,
        bm25_b=0.75,
        section_term_multiplier=2,
        embedding_dim=1024,
        embedding_cache_dir="/tmp/test-hybrid-embeddings",
        reuse_embeddings=True,
        subchunk_max_chars=3200,
        subchunk_overlap_chars=200,
        bm25_weight=0.7,
        vector_weight=0.3,
        preview_chars=220,
    )


def _source_result() -> dict:
    return {
        "success": True,
        "status": "complete",
        "query": "agent memory trajectory",
        "requested_paper_ids": ["paper-001", "paper-002"],
        "loaded_paper_ids": ["paper-001", "paper-002"],
        "missing_paper_ids": [],
        "paper_search_result": {"hits": []},
    }


def test_search_candidate_hybrid_cli_help() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py."
            "search_candidate_hybrid",
            "--help",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "search_candidate_hybrid.py" in completed.stdout
    assert "--query" in completed.stdout
    assert "--paper-id" in completed.stdout
    assert "--bm25-weight" in completed.stdout
    assert "--vector-weight" in completed.stdout
    assert "--subchunk-max-chars" in completed.stdout
    assert "--save-json" in completed.stdout


def test_build_result_uses_recommended_hybrid_weights(
    monkeypatch,
) -> None:
    captured = {}

    def fake_bm25_result(*, args, paper_ids):
        captured["bm25_paper_ids"] = paper_ids
        return _source_result()

    def fake_vector_result(*, args):
        captured["vector_args"] = args
        result = _source_result()
        result["embedding_provider"] = {
            "embedding_model": "bge-m3",
            "embedding_dimension": 1024,
        }
        return result

    def fake_hybrid_result(**kwargs):
        captured["fusion"] = kwargs
        return {
            "success": True,
            "status": "complete",
            "query": "agent memory trajectory",
            "requested_paper_ids": [
                "paper-001",
                "paper-002",
            ],
            "loaded_paper_ids": [
                "paper-001",
                "paper-002",
            ],
            "missing_paper_ids": [],
            "paper_search_result": {"hits": []},
            "errors": {},
        }

    monkeypatch.setattr(
        search_candidate_hybrid,
        "_build_bm25_result",
        fake_bm25_result,
    )
    monkeypatch.setattr(
        search_candidate_hybrid,
        "build_vector_result",
        fake_vector_result,
    )
    monkeypatch.setattr(
        search_candidate_hybrid,
        "build_hybrid_result",
        fake_hybrid_result,
    )

    result = search_candidate_hybrid.build_result(
        args=_args()
    )

    assert captured["bm25_paper_ids"] == (
        "paper-001",
        "paper-002",
    )
    assert captured["vector_args"].provider == (
        "openai-compatible"
    )
    assert captured["vector_args"].subchunk_max_chars == 3200
    assert captured["fusion"]["primary_name"] == "bm25"
    assert captured["fusion"]["secondary_name"] == "bge-m3"
    assert captured["fusion"]["primary_weight"] == 0.7
    assert captured["fusion"]["secondary_weight"] == 0.3
    assert result["hybrid_execution"]["strategy"] == (
        "bm25_bge_m3_subchunk_hybrid"
    )
