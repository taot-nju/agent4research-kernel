import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from ai4research.indexing_pipeline.scripts_py.run_rerank_suite import (
    _build_suite_summary,
)


def test_run_rerank_suite_cli_help() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py."
            "run_rerank_suite",
            "--help",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "run_rerank_suite.py" in completed.stdout
    assert "--hybrid-result-dir" in completed.stdout
    assert "--hybrid-run-name" in completed.stdout
    assert "--rerank-batch-size" in completed.stdout
    assert "--save-json" not in completed.stdout
    assert "--case-id" in completed.stdout


def test_build_suite_summary_calculates_macro_metrics() -> None:
    args = Namespace(
        model="bge-m3",
        candidate_paper_k=10,
        final_paper_k=5,
        subchunk_max_chars=3200,
        subchunk_overlap_chars=200,
        top_source_chunks_for_score=3,
        rerank_batch_size=16,
    )
    case_summaries = [
        {
            "case_id": "case-a",
            "reciprocal_rank": 1.0,
            "average_precision": 0.8,
            "precision_at_5": 0.6,
            "recall_at_5": 0.5,
            "ndcg_at_5": 0.9,
        },
        {
            "case_id": "case-b",
            "reciprocal_rank": 0.5,
            "average_precision": 0.4,
            "precision_at_5": 0.2,
            "recall_at_5": 1.0,
            "ndcg_at_5": 0.3,
        },
    ]

    summary = _build_suite_summary(
        suite_path=Path("/tmp/suite.json"),
        output_dir=Path("/tmp/output"),
        run_name="bge_m3_rerank",
        args=args,
        case_summaries=case_summaries,
    )

    assert summary["case_count"] == 2
    assert summary["macro"] == {
        "macro_mrr": 0.75,
        "macro_ap": 0.6000000000000001,
        "macro_precision_at_5": 0.4,
        "macro_recall_at_5": 0.75,
        "macro_ndcg_at_5": 0.6,
    }
    assert summary["weakest"]["weakest_ap_case"] == "case-b"
    assert (
        summary["weakest"]["weakest_ndcg_at_5_case"]
        == "case-b"
    )
