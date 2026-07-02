import pytest

from ai4research.indexing_pipeline.schemas.chunk_embedding import ChunkEmbedding


def test_chunk_embedding_roundtrip_json_dict():
    record = ChunkEmbedding(
        chunk_id="paper-001::chunk-0001",
        paper_id="paper-001",
        embedding=[0.1, 0.2, 0.3],
        embedding_model="demo-model",
        embedding_dim=3,
        text_hash="hash-001",
        source_path="chunks.jsonl",
        metadata={"page_start": 1, "section": "Introduction"},
    )

    data = record.to_json_dict()
    restored = ChunkEmbedding.from_json_dict(data)

    assert restored == record
    assert restored.to_json_dict() == data


def test_chunk_embedding_rejects_dimension_mismatch():
    with pytest.raises(ValueError, match="does not match embedding_dim"):
        ChunkEmbedding(
            chunk_id="paper-001::chunk-0001",
            paper_id="paper-001",
            embedding=[0.1, 0.2],
            embedding_model="demo-model",
            embedding_dim=3,
        )


def test_chunk_embedding_requires_core_ids_and_model():
    with pytest.raises(ValueError, match="chunk_id"):
        ChunkEmbedding(
            chunk_id="",
            paper_id="paper-001",
            embedding=[0.1],
            embedding_model="demo-model",
            embedding_dim=1,
        )

    with pytest.raises(ValueError, match="paper_id"):
        ChunkEmbedding(
            chunk_id="chunk-001",
            paper_id="",
            embedding=[0.1],
            embedding_model="demo-model",
            embedding_dim=1,
        )

    with pytest.raises(ValueError, match="embedding_model"):
        ChunkEmbedding(
            chunk_id="chunk-001",
            paper_id="paper-001",
            embedding=[0.1],
            embedding_model="",
            embedding_dim=1,
        )
