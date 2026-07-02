import json
from pathlib import Path

from ai4research.indexing_pipeline.scripts_py.summarize_retrieval_suite import build_summary


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_build_summary_from_suite_manifest(tmp_path: Path) -> None:
    repo_root = tmp_path

    metrics_a = {
        "case_id": "case-a",
        "query": "agent memory",
        "candidate_count": 3,
        "judged_count": 3,
        "relevant_count": 2,
        "retrieved_count": 3,
        "minimum_relevance": 2,
        "reciprocal_rank": 1.0,
        "average_precision": 0.75,
        "metrics_at_k": [
            {"k": 1, "precision": 1.0, "recall": 0.5, "ndcg": 1.0},
            {"k": 5, "precision": 0.4, "recall": 1.0, "ndcg": 0.9},
        ],
        "ranked_paper_ids": ["a", "b", "c"],
    }
    metrics_b = {
        "case_id": "case-b",
        "query": "failure attribution",
        "candidate_count": 4,
        "judged_count": 4,
        "relevant_count": 1,
        "retrieved_count": 4,
        "minimum_relevance": 2,
        "reciprocal_rank": 0.5,
        "average_precision": 0.5,
        "metrics_at_k": [
            {"k": 1, "precision": 0.0, "recall": 0.0, "ndcg": 0.0},
            {"k": 5, "precision": 0.2, "recall": 1.0, "ndcg": 0.5},
        ],
        "ranked_paper_ids": ["x", "y", "z", "w"],
    }

    metrics_a_path = repo_root / "metrics_a.json"
    metrics_b_path = repo_root / "metrics_b.json"
    _write_json(metrics_a_path, metrics_a)
    _write_json(metrics_b_path, metrics_b)

    suite = {
        "name": "test-suite",
        "version": "1",
        "baseline": {"name": "bm25-test"},
        "cases": [
            {
                "case_id": "case-a",
                "dataset_path": "dataset_a.json",
                "search_result_path": "search_a.json",
                "metrics_path": "metrics_a.json",
            },
            {
                "case_id": "case-b",
                "dataset_path": "dataset_b.json",
                "search_result_path": "search_b.json",
                "metrics_path": "metrics_b.json",
            },
        ],
    }
    suite_path = repo_root / "suite.json"
    _write_json(suite_path, suite)

    summary = build_summary(
        suite_path=suite_path,
        repo_root=repo_root,
        baseline_name="bm25-test",
    )

    assert summary["name"] == "ai4research-retrieval-suite-bm25-test-summary"
    assert summary["case_count"] == 2
    assert summary["macro"]["macro_mrr"] == 0.75
    assert summary["macro"]["macro_ap"] == 0.625
    assert summary["macro"]["macro_precision_at_5"] == 0.30000000000000004
    assert summary["macro"]["macro_recall_at_5"] == 1.0
    assert summary["macro"]["macro_ndcg_at_5"] == 0.7
    assert summary["weakest"]["weakest_ap_case"] == "case-b"
    assert summary["weakest"]["weakest_ndcg_at_5_case"] == "case-b"
    assert summary["cases"][0]["precision_at_5"] == 0.4
    assert summary["cases"][1]["precision_at_5"] == 0.2
