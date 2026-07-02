import pytest

from ai4research.indexing_pipeline.schemas.chunk_embedding import (
    ChunkEmbedding,
    compute_embedding_record_id,
    normalize_embedding_vector,
)


def test_normalize_embedding_vector_returns_float_tuple() -> None:
    vector = normalize_embedding_vector([1, 2.5, -3])

    assert vector == (1.0, 2.5, -3.0)


def test_chunk_embedding_roundtrip_and_stable_id() -> None:
    source_sha = "a" * 64

    embedding = ChunkEmbedding(
        chunk_id=" chunk-1 ",
        paper_id=" paper-1 ",
        embedding_model=" test-embedding-model ",
        embedding_model_version=" v1 ",
        embedding_dimension=3,
        vector=(0.1, 0.2, 0.3),
        source_chunk_sha256=source_sha,
        metadata={"source": "unit-test"},
    )

    expected_id = compute_embedding_record_id(
        chunk_id="chunk-1",
        embedding_model="test-embedding-model",
        embedding_model_version="v1",
        embedding_dimension=3,
        source_chunk_sha256=source_sha,
    )

    assert embedding.embedding_id == expected_id
    assert embedding.chunk_id == "chunk-1"
    assert embedding.paper_id == "paper-1"
    assert embedding.vector == (0.1, 0.2, 0.3)

    restored = ChunkEmbedding.from_dict(embedding.to_dict())

    assert restored == embedding
    assert restored.to_dict()["vector"] == [0.1, 0.2, 0.3]


def test_chunk_embedding_rejects_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="embedding_dimension must match vector length"):
        ChunkEmbedding(
            chunk_id="chunk-1",
            paper_id="paper-1",
            embedding_model="test-model",
            embedding_model_version="v1",
            embedding_dimension=2,
            vector=(0.1, 0.2, 0.3),
            source_chunk_sha256="a" * 64,
        )


def test_chunk_embedding_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="embedding vector values must be finite"):
        ChunkEmbedding(
            chunk_id="chunk-1",
            paper_id="paper-1",
            embedding_model="test-model",
            embedding_model_version="v1",
            embedding_dimension=1,
            vector=(float("nan"),),
            source_chunk_sha256="a" * 64,
        )


def test_chunk_embedding_rejects_invalid_source_sha() -> None:
    with pytest.raises(ValueError, match="source_chunk_sha256 must be a sha256 hex digest"):
        ChunkEmbedding(
            chunk_id="chunk-1",
            paper_id="paper-1",
            embedding_model="test-model",
            embedding_model_version="v1",
            embedding_dimension=1,
            vector=(0.1,),
            source_chunk_sha256="not-a-sha",
        )


class _LengthEmbeddingProvider:
    embedding_model = "length-model"
    embedding_model_version = "test"
    embedding_dimension = 2

    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed_text(self, text: str) -> tuple[float, ...]:
        self.texts.append(text)
        return (float(len(text)), 1.0)


def _document_chunk_for_embedding_test(*, text: str):
    from ai4research.indexing_pipeline.schemas.document_chunk import (
        DocumentChunk,
        build_chunk_id,
        compute_text_sha256,
    )

    paper_id = "paper-001"
    chunk_index = 0
    page_start = 1
    page_end = 2
    section_path = ("Intro",)
    content_sha256 = compute_text_sha256(text)
    source_markdown_sha256 = "c" * 64
    source_pdf_sha256 = "d" * 64
    source_parser_name = "test-parser"
    source_parser_version = "1"
    splitter_name = "test-splitter"
    splitter_version = "1"
    splitter_options = {}

    chunk_id = build_chunk_id(
        paper_id=paper_id,
        chunk_index=chunk_index,
        content_sha256=content_sha256,
        page_start=page_start,
        page_end=page_end,
        section_path=section_path,
        source_markdown_sha256=source_markdown_sha256,
        source_pdf_sha256=source_pdf_sha256,
        source_parser_name=source_parser_name,
        source_parser_version=source_parser_version,
        splitter_name=splitter_name,
        splitter_version=splitter_version,
        splitter_options=splitter_options,
    )

    return DocumentChunk(
        chunk_id=chunk_id,
        paper_id=paper_id,
        chunk_index=chunk_index,
        text=text,
        char_count=len(text),
        page_start=page_start,
        page_end=page_end,
        section_path=section_path,
        content_sha256=content_sha256,
        source_markdown_relative_path="documents/paper-001/document.md",
        source_markdown_sha256=source_markdown_sha256,
        source_pdf_sha256=source_pdf_sha256,
        source_parser_name=source_parser_name,
        source_parser_version=source_parser_version,
        splitter_name=splitter_name,
        splitter_version=splitter_version,
        splitter_options=splitter_options,
    )


def test_chunk_embedding_pipeline_keeps_short_chunk_as_single_embedding():
    from ai4research.indexing_pipeline.pipelines.chunk_embedding_pipeline import (
        ChunkEmbeddingPipeline,
    )

    provider = _LengthEmbeddingProvider()
    pipeline = ChunkEmbeddingPipeline(
        embedding_provider=provider,
        subchunk_max_chars=10,
    )

    source_chunk = _document_chunk_for_embedding_test(text="short")
    embeddings = pipeline.embed_chunks(
        chunks=(source_chunk,)
    )

    assert len(embeddings) == 1
    assert embeddings[0].chunk_id == source_chunk.chunk_id
    assert embeddings[0].metadata["source_chunk_id"] == source_chunk.chunk_id
    assert embeddings[0].metadata["subchunk_index"] == 0
    assert embeddings[0].metadata["subchunk_count"] == 1
    assert embeddings[0].metadata["char_start"] == 0
    assert embeddings[0].metadata["char_end"] == 5
    assert embeddings[0].metadata["is_subchunk"] is False
    assert provider.texts == ["short"]


def test_chunk_embedding_pipeline_splits_long_chunk_into_subchunks():
    from ai4research.indexing_pipeline.pipelines.chunk_embedding_pipeline import (
        ChunkEmbeddingPipeline,
    )

    provider = _LengthEmbeddingProvider()
    pipeline = ChunkEmbeddingPipeline(
        embedding_provider=provider,
        subchunk_max_chars=4,
    )

    source_chunk = _document_chunk_for_embedding_test(text="abcdefghij")
    embeddings = pipeline.embed_chunks(
        chunks=(source_chunk,)
    )

    assert [embedding.chunk_id for embedding in embeddings] == [
        f"{source_chunk.chunk_id}::subchunk-0000",
        f"{source_chunk.chunk_id}::subchunk-0001",
        f"{source_chunk.chunk_id}::subchunk-0002",
    ]
    assert provider.texts == ["abcd", "efgh", "ij"]

    assert embeddings[0].metadata["source_chunk_id"] == source_chunk.chunk_id
    assert embeddings[0].metadata["subchunk_index"] == 0
    assert embeddings[0].metadata["subchunk_count"] == 3
    assert embeddings[0].metadata["char_start"] == 0
    assert embeddings[0].metadata["char_end"] == 4
    assert embeddings[0].metadata["is_subchunk"] is True

    assert embeddings[2].metadata["subchunk_index"] == 2
    assert embeddings[2].metadata["char_start"] == 8
    assert embeddings[2].metadata["char_end"] == 10


def test_chunk_embedding_pipeline_supports_subchunk_overlap():
    from ai4research.indexing_pipeline.pipelines.chunk_embedding_pipeline import (
        ChunkEmbeddingPipeline,
    )

    provider = _LengthEmbeddingProvider()
    pipeline = ChunkEmbeddingPipeline(
        embedding_provider=provider,
        subchunk_max_chars=4,
        subchunk_overlap_chars=1,
    )

    pipeline.embed_chunks(
        chunks=(
            _document_chunk_for_embedding_test(text="abcdefghij"),
        )
    )

    assert provider.texts == ["abcd", "defg", "ghij"]


def test_chunk_embedding_pipeline_rejects_invalid_subchunk_config():
    from ai4research.indexing_pipeline.pipelines.chunk_embedding_pipeline import (
        ChunkEmbeddingPipeline,
    )

    provider = _LengthEmbeddingProvider()

    with pytest.raises(ValueError, match="subchunk_max_chars"):
        ChunkEmbeddingPipeline(
            embedding_provider=provider,
            subchunk_max_chars=0,
        )

    with pytest.raises(ValueError, match="subchunk_overlap_chars"):
        ChunkEmbeddingPipeline(
            embedding_provider=provider,
            subchunk_max_chars=4,
            subchunk_overlap_chars=4,
        )
