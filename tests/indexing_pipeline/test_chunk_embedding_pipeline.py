from pathlib import Path

from ai4research.indexing_pipeline.embeddings import DeterministicHashEmbeddingProvider
from ai4research.indexing_pipeline.pipelines.chunk_embedding_pipeline import (
    ChunkEmbeddingPipeline,
)
from ai4research.indexing_pipeline.repositories.jsonl_embedding import (
    JsonlChunkEmbeddingRepository,
)
from ai4research.indexing_pipeline.schemas.document_chunk import DocumentChunk


def _chunk(index: int, text: str) -> DocumentChunk:
    return DocumentChunk.create(
        paper_id="a" * 40,
        chunk_index=index,
        text=text,
        page_start=1,
        page_end=1,
        section_path=("1 Introduction",),
        source_markdown_relative_path="documents/aa/aa/paper/document.md",
        source_markdown_sha256="b" * 64,
        source_pdf_sha256="c" * 64,
        source_parser_name="test-parser",
        source_parser_version="1",
        splitter_name="test-splitter",
        splitter_version="1",
        splitter_options={"target_chars": 100},
    )


def test_chunk_embedding_pipeline_embeds_chunks_and_writes_jsonl(tmp_path: Path) -> None:
    provider = DeterministicHashEmbeddingProvider(embedding_dimension=8)
    pipeline = ChunkEmbeddingPipeline(embedding_provider=provider)
    path = tmp_path / "embeddings.jsonl"

    result = pipeline.write_chunk_embeddings(
        path=path,
        chunks=[
            _chunk(0, "agent memory trajectory"),
            _chunk(1, "multi agent planning"),
        ],
    )

    assert result.path == path
    assert result.embedding_count == 2
    assert result.embedding_model == "deterministic-hash-embedding"
    assert result.embedding_dimension == 8

    read_result = JsonlChunkEmbeddingRepository().read_embeddings(path=path)

    assert read_result.embedding_count == 2
    assert read_result.embeddings[0].paper_id == "a" * 40
    assert read_result.embeddings[0].embedding_dimension == 8
    assert read_result.embeddings[0].metadata["chunk_index"] == 0
    assert read_result.embeddings[0].metadata["section_path"] == ["1 Introduction"]


def test_chunk_embedding_pipeline_embed_chunks_is_deterministic() -> None:
    provider = DeterministicHashEmbeddingProvider(embedding_dimension=8)
    pipeline = ChunkEmbeddingPipeline(embedding_provider=provider)
    chunks = [_chunk(0, "agent memory trajectory")]

    first = pipeline.embed_chunks(chunks=chunks)
    second = pipeline.embed_chunks(chunks=chunks)

    assert first == second
