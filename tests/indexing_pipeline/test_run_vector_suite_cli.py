import subprocess
import sys


def test_run_vector_suite_cli_help() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py.run_vector_suite",
            "--help",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "run_vector_suite.py" in completed.stdout
    assert "--provider" in completed.stdout
    assert "openai-compatible" in completed.stdout
    assert "--case-id" in completed.stdout
    assert "--output-dir" in completed.stdout
    assert "--reuse-embeddings" in completed.stdout
    assert "--embedding-input-max-chars" in completed.stdout
    assert "--subchunk-max-chars" in completed.stdout
    assert "--subchunk-overlap-chars" in completed.stdout
