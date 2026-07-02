import subprocess
import sys


def test_run_token_hash_vector_suite_cli_help() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py.run_token_hash_vector_suite",
            "--help",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "run_token_hash_vector_suite.py" in completed.stdout
    assert "--suite" in completed.stdout
    assert "--case-id" in completed.stdout
    assert "--output-dir" in completed.stdout
    assert "token-hash demo vector search" in completed.stdout
