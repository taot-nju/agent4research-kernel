import json
from pathlib import Path

import pytest

from ai4research.indexing_pipeline.repositories.jsonl_embedding import (
    JsonlChunkEmbeddingRepository,
)
from ai4research.indexing_pipeline.schemas.chunk_embedding import ChunkEmbedding


def _embedding(index: int) -> ChunkEmbedding:
    return ChunkEmbedding(
        chunk_id=f"chunk-{index}",
        paper_id="paper-1",
        embedding_model="test-model",
        embedding_model_version="v1",
        embedding_dimension=3,
        vector=(float(index), float(index + 1), float(index + 2)),
        source_chunk_sha256=f"{index}" * 64,
        metadata={"index": index},
    )


def test_jsonl_embedding_repository_roundtrip(tmp_path: Path) -> None:
    repository = JsonlChunkEmbeddingRepository()
    path = tmp_path / "embeddings" / "chunks.jsonl"

    write_result = repository.write_embeddings(
        path=path,
        embeddings=[_embedding(1), _embedding(2)],
    )

    assert write_result.path == path
    assert write_result.embedding_count == 2
    assert path.exists()

    read_result = repository.read_embeddings(path=path)

    assert read_result.embedding_count == 2
    assert read_result.embeddings[0] == _embedding(1)
    assert read_result.embeddings[1] == _embedding(2)


def test_jsonl_embedding_repository_skips_blank_lines(tmp_path: Path) -> None:
    repository = JsonlChunkEmbeddingRepository()
    path = tmp_path / "chunks.jsonl"

    path.write_text(
        json.dumps(_embedding(1).to_dict(), ensure_ascii=False) + "\n\n",
        encoding="utf-8",
    )

    result = repository.read_embeddings(path=path)

    assert result.embedding_count == 1
    assert result.embeddings[0] == _embedding(1)


def test_jsonl_embedding_repository_reports_bad_line_number(tmp_path: Path) -> None:
    repository = JsonlChunkEmbeddingRepository()
    path = tmp_path / "bad.jsonl"
    path.write_text("{}\nnot-json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid embedding jsonl line 1"):
        repository.read_embeddings(path=path)
