import json
import subprocess
import sys
from pathlib import Path


def test_embed_text_cli_help() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py.embed_text",
            "--help",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "embed_text.py" in completed.stdout
    assert "--text" in completed.stdout
    assert "--provider" in completed.stdout
    assert "--save-json" in completed.stdout
    assert "openai-compatible" in completed.stdout


def test_embed_text_cli_token_hash_demo(tmp_path: Path) -> None:
    output_path = tmp_path / "embedding.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py.embed_text",
            "--text",
            "agent memory trajectory",
            "--provider",
            "token-hash",
            "--embedding-dim",
            "16",
            "--preview-values",
            "4",
            "--save-json",
            str(output_path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "Embedding text result" in completed.stdout
    assert "provider:                token-hash" in completed.stdout
    assert "embedding_dimension:     16" in completed.stdout
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["success"] is True
    assert payload["provider"] == "token-hash"
    assert payload["embedding_dimension"] == 16
    assert len(payload["vector"]) == 16
