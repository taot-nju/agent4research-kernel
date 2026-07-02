"""chunk BM25 与论文级聚合测试。"""

from ai4research.indexing_pipeline.retrieval.bm25 import (
    BM25ChunkRetriever,
    tokenize_for_retrieval,
)
from ai4research.indexing_pipeline.retrieval.paper_aggregation import (
    PaperAggregationConfig,
    PaperScoreAggregator,
)
from ai4research.indexing_pipeline.schemas.document_chunk import (
    DocumentChunk,
)


def _build_chunk(
    *,
    paper_id: str,
    chunk_index: int,
    text: str,
) -> DocumentChunk:
    return DocumentChunk.create(
        paper_id=paper_id,
        chunk_index=chunk_index,
        text=text,
        page_start=chunk_index + 1,
        page_end=chunk_index + 1,
        section_path=("Test Section",),
        source_markdown_relative_path=(
            f"documents/{paper_id[:2]}/"
            f"{paper_id[2:4]}/{paper_id}/"
            "document.md"
        ),
        source_markdown_sha256="d" * 64,
        source_pdf_sha256="e" * 64,
        source_parser_name="test-parser",
        source_parser_version="1",
        splitter_name="test-splitter",
        splitter_version="1",
        splitter_options={
            "target_chars": 100,
        },
    )


def test_tokenizer_handles_unicode_punctuation():
    assert tokenize_for_retrieval(
        "Agent memory，trajectory"
    ) == (
        "agent",
        "memory",
        "trajectory",
    )


def test_bm25_search_is_stable():
    paper_a = "a" * 40
    paper_b = "b" * 40
    paper_c = "c" * 40

    chunks = (
        _build_chunk(
            paper_id=paper_a,
            chunk_index=0,
            text=(
                "Agent memory trajectory learning "
                "uses trajectory experience."
            ),
        ),
        _build_chunk(
            paper_id=paper_a,
            chunk_index=1,
            text=(
                "Memory improves an agent through "
                "past trajectories."
            ),
        ),
        _build_chunk(
            paper_id=paper_b,
            chunk_index=0,
            text=(
                "Agent memory retrieves external "
                "documents."
            ),
        ),
        _build_chunk(
            paper_id=paper_b,
            chunk_index=1,
            text="A maintainable memory system.",
        ),
        _build_chunk(
            paper_id=paper_c,
            chunk_index=0,
            text=(
                "Image classification with "
                "convolutional networks."
            ),
        ),
    )

    retriever = BM25ChunkRetriever()

    first = retriever.search(
        query="agent memory trajectory",
        chunks=chunks,
        limit=10,
    )
    second = retriever.search(
        query="agent memory trajectory",
        chunks=chunks,
        limit=10,
    )

    assert first.query_terms == (
        "agent",
        "memory",
        "trajectory",
    )
    assert first.hits
    assert (
        first.hits[0].chunk.paper_id
        == paper_a
    )
    assert all(
        hit.chunk.paper_id != paper_c
        for hit in first.hits
    )
    assert [
        hit.chunk.chunk_id
        for hit in first.hits
    ] == [
        hit.chunk.chunk_id
        for hit in second.hits
    ]


def test_paper_aggregation_limits_evidence():
    paper_a = "a" * 40
    paper_b = "b" * 40

    chunks = (
        _build_chunk(
            paper_id=paper_a,
            chunk_index=0,
            text=(
                "Agent memory trajectory learning."
            ),
        ),
        _build_chunk(
            paper_id=paper_a,
            chunk_index=1,
            text=(
                "Trajectory memory helps an agent."
            ),
        ),
        _build_chunk(
            paper_id=paper_a,
            chunk_index=2,
            text="Memory trajectory analysis.",
        ),
        _build_chunk(
            paper_id=paper_b,
            chunk_index=0,
            text=(
                "Agent memory retrieves documents."
            ),
        ),
        _build_chunk(
            paper_id=paper_b,
            chunk_index=1,
            text="External memory system.",
        ),
    )

    chunk_result = BM25ChunkRetriever().search(
        query="agent memory trajectory",
        chunks=chunks,
        limit=len(chunks),
    )

    aggregator = PaperScoreAggregator(
        PaperAggregationConfig(
            top_chunks_for_score=2,
            evidence_chunks_per_paper=2,
        )
    )

    result = aggregator.aggregate(
        chunk_result=chunk_result,
        limit=2,
    )

    assert result.matched_paper_count == 2
    assert len(result.hits) == 2
    assert result.hits[0].paper_id == paper_a
    assert (
        result.hits[0]
        .score_components["query_coverage"]
        == 1.0
    )
    assert all(
        len(hit.evidence) <= 2
        for hit in result.hits
    )
    assert all(
        hit.score > 0
        for hit in result.hits
    )
