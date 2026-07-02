import subprocess
import sys
from pathlib import Path

from ai4research.indexing_pipeline.repositories.jsonl_embedding import (
    JsonlChunkEmbeddingRepository,
)
from ai4research.indexing_pipeline.schemas.chunk_embedding import ChunkEmbedding
from ai4research.indexing_pipeline.scripts_py.audit_embedding_run import (
    audit_embedding_root,
)


def _embedding(
    *,
    chunk_id: str,
    paper_id: str = "paper-001",
    metadata: dict | None = None,
) -> ChunkEmbedding:
    return ChunkEmbedding(
        chunk_id=chunk_id,
        paper_id=paper_id,
        embedding_model="demo-model",
        embedding_model_version="test",
        embedding_dimension=2,
        vector=[1.0, 0.0],
        source_chunk_sha256="a" * 64,
        metadata=metadata or {},
    )


def test_audit_embedding_run_cli_help() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.indexing_pipeline.scripts_py.audit_embedding_run",
            "--help",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "audit_embedding_run.py" in completed.stdout
    assert "--embedding-root" in completed.stdout
    assert "--save-json" in completed.stdout
    assert "--show-examples" in completed.stdout


def test_audit_embedding_root_counts_subchunks(tmp_path: Path) -> None:
    embedding_path = (
        tmp_path
        / "aa"
        / "bb"
        / "paper-001"
        / "demo-model"
        / "demo-2"
        / "embeddings.jsonl"
    )

    repository = JsonlChunkEmbeddingRepository()
    repository.write_embeddings(
        path=embedding_path,
        embeddings=[
            _embedding(chunk_id="b" * 64),
            _embedding(
                chunk_id=("c" * 64) + "::subchunk-0000",
                metadata={
                    "is_subchunk": True,
                    "source_chunk_id": "c" * 64,
                    "subchunk_index": 0,
                    "subchunk_count": 2,
                    "char_start": 0,
                    "char_end": 3200,
                },
            ),
            _embedding(
                chunk_id=("c" * 64) + "::subchunk-0001",
                metadata={
                    "is_subchunk": True,
                    "source_chunk_id": "c" * 64,
                    "subchunk_index": 1,
                    "subchunk_count": 2,
                    "char_start": 3000,
                    "char_end": 5000,
                },
            ),
        ],
    )

    report = audit_embedding_root(
        embedding_root=tmp_path,
        show_examples=1,
    )

    assert report["embedding_files"] == 1
    assert report["readable_embedding_files"] == 1
    assert report["read_error_count"] == 0
    assert report["total_embeddings"] == 3
    assert report["paper_count"] == 1
    assert report["model_distribution"] == {"demo-model@test": 3}
    assert report["dimension_distribution"] == {"2": 3}
    assert report["subchunk_embeddings"] == 2
    assert report["source_chunks_with_subchunks"] == 1
    assert report["papers_with_subchunks"] == 1
    assert report["max_subchunk_count"] == 2
    assert report["max_char_end"] == 5000
    assert report["duplicate_embedding_id_count"] == 0
    assert len(report["subchunk_examples"]) == 1
