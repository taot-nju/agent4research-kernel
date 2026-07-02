import subprocess
import sys


def test_run_hybrid_suite_cli_help() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py.run_hybrid_suite",
            "--help",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "run_hybrid_suite.py" in completed.stdout
    assert "--secondary-result-dir" in completed.stdout
    assert "--primary-result-dir" in completed.stdout
    assert "--primary-weight" in completed.stdout
    assert "--secondary-weight" in completed.stdout
    assert "--case-id" in completed.stdout
    assert "--output-dir" in completed.stdout
