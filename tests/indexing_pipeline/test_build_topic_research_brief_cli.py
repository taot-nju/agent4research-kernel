import subprocess
import sys


def test_build_topic_research_brief_cli_help() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py.build_topic_research_brief",
            "--help",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "build_topic_research_brief.py" in completed.stdout
    assert "--topic-workflow-json" in completed.stdout
    assert "--evidence-dossier-md" in completed.stdout
    assert "--output-md" in completed.stdout
    assert "--top-papers" in completed.stdout
    assert "evidence-backed research brief" in completed.stdout
