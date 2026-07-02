import subprocess
import sys


def test_search_candidate_vector_demo_cli_help() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py.search_candidate_vector_demo",
            "--help",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "search_candidate_vector_demo.py" in completed.stdout
    assert "--query" in completed.stdout
    assert "--paper-id" in completed.stdout
    assert "--save-json" in completed.stdout
    assert "vector search" in completed.stdout
    assert "openai-compatible" in completed.stdout
    assert "--embedding-input-max-chars" in completed.stdout
    assert "--subchunk-max-chars" in completed.stdout
    assert "--subchunk-overlap-chars" in completed.stdout
