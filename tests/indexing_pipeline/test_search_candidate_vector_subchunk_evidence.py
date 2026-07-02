from ai4research.indexing_pipeline.retrieval.vector import VectorChunkHit
from ai4research.indexing_pipeline.schemas.chunk_embedding import ChunkEmbedding
from ai4research.indexing_pipeline.schemas.document_chunk import (
    DocumentChunk,
    build_chunk_id,
    compute_text_sha256,
)


def _document_chunk(*, text: str) -> DocumentChunk:
    paper_id = "paper-001"
    chunk_index = 0
    page_start = 1
    page_end = 1
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
        content_sha256=content_sha256,
        page_start=page_start,
        page_end=page_end,
        section_path=section_path,
        source_markdown_relative_path="documents/paper-001/document.md",
        source_markdown_sha256=source_markdown_sha256,
        source_pdf_sha256=source_pdf_sha256,
        source_parser_name=source_parser_name,
        source_parser_version=source_parser_version,
        splitter_name=splitter_name,
        splitter_version=splitter_version,
        splitter_options=splitter_options,
    )


def test_subchunk_vector_hit_can_resolve_source_document_chunk() -> None:
    chunk = _document_chunk(text="abcdefghijklmnopqrstuvwxyz")
    subchunk_id = f"{chunk.chunk_id}::subchunk-0001"

    embedding = ChunkEmbedding(
        chunk_id=subchunk_id,
        paper_id=chunk.paper_id,
        embedding_model="test-model",
        embedding_model_version="v1",
        embedding_dimension=2,
        vector=(1.0, 0.0),
        source_chunk_sha256=chunk.content_sha256,
        metadata={
            "source_chunk_id": chunk.chunk_id,
            "subchunk_index": 1,
            "subchunk_count": 3,
            "char_start": 10,
            "char_end": 20,
            "is_subchunk": True,
        },
    )
    vector_hit = VectorChunkHit(
        rank=1,
        score=0.99,
        embedding=embedding,
    )

    chunks_by_id = {
        chunk.chunk_id: chunk,
    }
    source_chunk_id = str(
        vector_hit.embedding.metadata.get(
            "source_chunk_id",
            vector_hit.embedding.chunk_id,
        )
    )
    resolved_chunk = chunks_by_id[source_chunk_id]

    assert resolved_chunk == chunk
    assert vector_hit.embedding.chunk_id == subchunk_id
    assert vector_hit.embedding.metadata["char_start"] == 10
    assert vector_hit.embedding.metadata["char_end"] == 20
