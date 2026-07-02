from pathlib import Path

from ai4research.indexing_pipeline.embeddings import TokenHashEmbeddingProvider
from ai4research.indexing_pipeline.pipelines.chunk_embedding_pipeline import (
    ChunkEmbeddingPipeline,
)
from ai4research.indexing_pipeline.repositories.jsonl_embedding import (
    JsonlChunkEmbeddingRepository,
)
from ai4research.indexing_pipeline.retrieval.vector import CosineVectorRetriever
from ai4research.indexing_pipeline.retrieval.vector_paper_aggregation import (
    VectorPaperAggregationConfig,
    VectorPaperAggregator,
)
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


def test_token_hash_vector_end_to_end_demo_ranks_matching_paper_first(tmp_path: Path) -> None:
    paper_agent_memory = "a" * 40
    paper_multi_agent = "b" * 40

    chunks = [
        _chunk(
            paper_id=paper_agent_memory,
            index=0,
            text="LLM agent memory stores multi-turn trajectories for future reasoning.",
        ),
        _chunk(
            paper_id=paper_agent_memory,
            index=1,
            text="Trajectory clustering can organize agent experiences into reusable memory.",
        ),
        _chunk(
            paper_id=paper_multi_agent,
            index=0,
            text="Multi-agent collaboration needs planning, role assignment, and execution.",
        ),
    ]

    provider = TokenHashEmbeddingProvider(embedding_dimension=128)
    pipeline = ChunkEmbeddingPipeline(embedding_provider=provider)
    path = tmp_path / "embeddings.jsonl"

    write_result = pipeline.write_chunk_embeddings(
        path=path,
        chunks=chunks,
    )
    embeddings = JsonlChunkEmbeddingRepository().read_embeddings(path=path).embeddings

    query_vector = provider.embed_text("agent memory trajectory clustering")
    chunk_result = CosineVectorRetriever().search(
        query_vector=query_vector,
        embeddings=embeddings,
        top_k=3,
    )
    paper_result = VectorPaperAggregator().aggregate(
        query_vector_dimension=chunk_result.query_vector_dimension,
        chunk_hits=chunk_result.hits,
        config=VectorPaperAggregationConfig(
            final_paper_k=2,
            evidence_chunks_per_paper=2,
            top_chunks_for_score=2,
        ),
    )

    assert write_result.embedding_count == 3
    assert chunk_result.hits[0].embedding.paper_id == paper_agent_memory
    assert paper_result.hits[0].paper_id == paper_agent_memory
    assert len(paper_result.hits[0].evidence) == 2
