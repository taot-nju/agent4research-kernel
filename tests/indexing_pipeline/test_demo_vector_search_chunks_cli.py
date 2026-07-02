import json
import subprocess
import sys
from pathlib import Path

from ai4research.indexing_pipeline.schemas.document_chunk import DocumentChunk


def _chunk(*, paper_id: str, index: int, text: str) -> DocumentChunk:
    return DocumentChunk.create(
        paper_id=paper_id,
        chunk_index=index,
        text=text,
        page_start=index + 1,
        page_end=index + 1,
        section_path=("demo",),
        source_markdown_relative_path=(
            f"documents/{paper_id[:2]}/{paper_id[2:4]}/{paper_id}/document.md"
        ),
        source_markdown_sha256="b" * 64,
        source_pdf_sha256="c" * 64,
        source_parser_name="demo-parser",
        source_parser_version="1",
        splitter_name="demo-splitter",
        splitter_version="1",
        splitter_options={"target_chars": 100},
    )


def _write_fake_chunks(path: Path) -> tuple[str, str]:
    paper_agent_memory = "a" * 40
    paper_multi_agent = "b" * 40

    chunks = [
        _chunk(
            paper_id=paper_agent_memory,
            index=0,
            text="Agent memory trajectory clustering organizes reusable experiences.",
        ),
        _chunk(
            paper_id=paper_multi_agent,
            index=0,
            text="Multi-agent collaboration needs planning and role assignment.",
        ),
    ]

    path.write_text(
        "".join(
            json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n"
            for chunk in chunks
        ),
        encoding="utf-8",
    )

    return paper_agent_memory, paper_multi_agent


def test_demo_vector_search_chunks_cli_runs_on_fake_chunks(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    embeddings_path = tmp_path / "embeddings.jsonl"
    paper_agent_memory, _ = _write_fake_chunks(chunks_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py.demo_vector_search_chunks",
            "--chunks-jsonl",
            str(chunks_path),
            "--query",
            "agent memory trajectory clustering",
            "--embeddings-jsonl",
            str(embeddings_path),
            "--chunk-top-k",
            "2",
            "--final-paper-k",
            "2",
            "--preview-chars",
            "80",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "Token-hash vector search demo" in completed.stdout
    assert "embedding_status:   written" in completed.stdout
    assert "PAPER RANKING" in completed.stdout
    assert f"paper_id: {paper_agent_memory}" in completed.stdout
    assert embeddings_path.exists()


def test_demo_vector_search_chunks_cli_default_embeddings_path_uses_tmp(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    _write_fake_chunks(chunks_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py.demo_vector_search_chunks",
            "--chunks-jsonl",
            str(chunks_path),
            "--query",
            "agent memory trajectory clustering",
            "--chunk-top-k",
            "2",
            "--final-paper-k",
            "2",
            "--preview-chars",
            "80",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "embeddings_jsonl:   /tmp/ai4research_demo_embeddings/chunks/token_hash_embeddings.jsonl" in completed.stdout
    assert "embedding_status:   written" in completed.stdout
