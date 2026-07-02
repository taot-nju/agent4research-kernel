import subprocess
import sys

from ai4research.indexing_pipeline.scripts_py.rerank_texts import (
    _normalized_results,
)


def test_rerank_texts_cli_help() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py.rerank_texts",
            "--help",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "rerank_texts.py" in completed.stdout
    assert "--query" in completed.stdout
    assert "--document" in completed.stdout
    assert "--base-url" in completed.stdout
    assert "--save-json" in completed.stdout
    assert "/v1/rerank" in completed.stdout


def test_normalized_results_sorts_by_score_descending() -> None:
    response = {
        "results": [
            {
                "index": 1,
                "document": {"text": "lower relevance"},
                "relevance_score": 0.2,
            },
            {
                "index": 0,
                "document": {"text": "higher relevance"},
                "relevance_score": 0.8,
            },
        ]
    }

    results = _normalized_results(response)

    assert results == [
        {
            "original_index": 0,
            "relevance_score": 0.8,
            "text": "higher relevance",
        },
        {
            "original_index": 1,
            "relevance_score": 0.2,
            "text": "lower relevance",
        },
    ]
