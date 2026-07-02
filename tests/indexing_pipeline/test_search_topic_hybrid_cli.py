import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from ai4research.indexing_pipeline.scripts_py import (
    search_topic_hybrid,
)


def _args(workflow_path: Path) -> Namespace:
    return Namespace(
        topic_workflow_json=str(workflow_path),
        query=None,
        data_root="/data/ai4research_assets",
        chunk_recall_k=300,
        final_paper_k=5,
        evidence_chunks_per_paper=3,
        top_chunks_for_score=3,
        embedding_dim=1024,
        embedding_cache_dir="/tmp/test-topic-hybrid",
        reuse_embeddings=True,
        subchunk_max_chars=3200,
        subchunk_overlap_chars=200,
        preview_chars=220,
    )


def _write_workflow(path: Path) -> None:
    payload = {
        "topic": "agent memory",
        "outcomes": [
            {
                "paper_id": "paper-001",
                "ready": True,
            },
            {
                "paper_id": "paper-002",
                "ready": False,
            },
            {
                "paper_id": "paper-001",
                "ready": True,
            },
        ],
    }
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_search_topic_hybrid_cli_help() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py."
            "search_topic_hybrid",
            "--help",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "search_topic_hybrid.py" in completed.stdout
    assert "--topic-workflow-json" in completed.stdout
    assert "--query" in completed.stdout
    assert "ready=True" in completed.stdout
    assert "--save-json" in completed.stdout


def test_build_result_uses_only_ready_topic_outcomes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workflow_path = tmp_path / "workflow.json"
    _write_workflow(workflow_path)

    captured = {}

    def fake_hybrid_result(*, args):
        captured["args"] = args
        return {
            "success": True,
            "status": "complete",
            "query": args.query,
            "requested_paper_ids": args.paper_id,
            "loaded_paper_ids": args.paper_id,
            "missing_paper_ids": [],
            "paper_search_result": {"hits": []},
        }

    monkeypatch.setattr(
        search_topic_hybrid,
        "build_hybrid_result",
        fake_hybrid_result,
    )

    result = search_topic_hybrid.build_result(
        args=_args(workflow_path)
    )

    assert captured["args"].query == "agent memory"
    assert captured["args"].paper_id == ["paper-001"]
    assert result["topic_workflow"] == {
        "source_path": str(workflow_path.resolve()),
        "topic": "agent memory",
        "query": "agent memory",
        "outcome_count": 3,
        "ready_outcome_count": 1,
        "ready_paper_ids": ["paper-001"],
        "selection_rule": "outcome.ready == true",
    }
