import subprocess
import sys


def test_build_topic_evidence_dossier_cli_help() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py.build_topic_evidence_dossier",
            "--help",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "build_topic_evidence_dossier.py" in completed.stdout
    assert "--topic-workflow-json" in completed.stdout
    assert "--hybrid-result-json" in completed.stdout
    assert "--output-md" in completed.stdout
    assert "--top-papers" in completed.stdout
    assert "--evidence-per-source" in completed.stdout
    assert "--preview-chars" in completed.stdout
    assert "Markdown dossier" in completed.stdout
