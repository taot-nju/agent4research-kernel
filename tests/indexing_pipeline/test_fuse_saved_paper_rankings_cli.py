import json
import subprocess
import sys
from pathlib import Path


def _search_result(hits):
    return {
        "success": True,
        "status": "complete",
        "query": "agent memory",
        "requested_paper_ids": ["a", "b"],
        "loaded_paper_ids": ["a", "b"],
        "missing_paper_ids": [],
        "paper_search_result": {
            "query": "agent memory",
            "hits": hits,
        },
        "errors": {},
    }


def test_fuse_saved_paper_rankings_cli_help() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py.fuse_saved_paper_rankings",
            "--help",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "fuse_saved_paper_rankings.py" in completed.stdout
    assert "--primary-result" in completed.stdout
    assert "--secondary-result" in completed.stdout
    assert "--save-json" in completed.stdout


def test_fuse_saved_paper_rankings_cli_minimal_demo(tmp_path: Path) -> None:
    primary_path = tmp_path / "primary.json"
    secondary_path = tmp_path / "secondary.json"
    output_path = tmp_path / "hybrid.json"

    primary_path.write_text(
        json.dumps(
            _search_result(
                [
                    {"rank": 1, "paper_id": "a", "score": 10.0, "evidence": []},
                    {"rank": 2, "paper_id": "b", "score": 5.0, "evidence": []},
                ]
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    secondary_path.write_text(
        json.dumps(
            _search_result(
                [
                    {"rank": 1, "paper_id": "b", "score": 0.9, "evidence": []},
                    {"rank": 2, "paper_id": "a", "score": 0.1, "evidence": []},
                ]
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py.fuse_saved_paper_rankings",
            "--primary-result",
            str(primary_path),
            "--secondary-result",
            str(secondary_path),
            "--primary-name",
            "bm25",
            "--secondary-name",
            "vector",
            "--primary-weight",
            "0.5",
            "--secondary-weight",
            "0.5",
            "--final-paper-k",
            "2",
            "--save-json",
            str(output_path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "Hybrid paper ranking" in completed.stdout
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    hits = payload["paper_search_result"]["hits"]
    assert len(hits) == 2
    assert {hit["paper_id"] for hit in hits} == {"a", "b"}
    assert hits[0]["score_components"]["primary_weight"] == 0.5
    assert hits[0]["score_components"]["secondary_weight"] == 0.5
