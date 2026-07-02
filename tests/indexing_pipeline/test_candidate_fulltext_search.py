"""候选论文全文二次检索 Pipeline 测试。"""

from ai4research.indexing_pipeline.pipelines.candidate_fulltext_search import (
    CandidateFullTextSearchRequest,
    search_candidate_fulltext,
)
from ai4research.indexing_pipeline.repositories.reader import (
    ChunkCorpusReader,
    ChunkCorpusReadResult,
)
from ai4research.indexing_pipeline.retrieval.bm25 import (
    BM25ChunkRetriever,
)
from ai4research.indexing_pipeline.retrieval.paper_aggregation import (
    PaperScoreAggregator,
)
from ai4research.indexing_pipeline.schemas.document_chunk import (
    DocumentChunk,
)


def _build_chunk(
    *,
    paper_id: str,
    text: str,
) -> DocumentChunk:
    return DocumentChunk.create(
        paper_id=paper_id,
        chunk_index=0,
        text=text,
        page_start=1,
        page_end=1,
        section_path=("Introduction",),
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


class _StubReader(ChunkCorpusReader):
    def __init__(
        self,
        *,
        chunks,
        loaded_paper_ids,
        missing_paper_ids,
    ):
        self._chunks = tuple(chunks)
        self._loaded = tuple(
            loaded_paper_ids
        )
        self._missing = tuple(
            missing_paper_ids
        )

    def read(self, request):
        return ChunkCorpusReadResult(
            requested_paper_ids=(
                request.paper_ids
            ),
            loaded_paper_ids=self._loaded,
            missing_paper_ids=(
                self._missing
            ),
            chunks=self._chunks,
            errors={
                paper_id: "missing"
                for paper_id
                in self._missing
            },
        )


def _build_request(
    paper_ids,
) -> CandidateFullTextSearchRequest:
    return CandidateFullTextSearchRequest(
        query="agent memory trajectory",
        candidate_paper_ids=tuple(
            paper_ids
        ),
        splitter_name="test-splitter",
        splitter_version="1",
        splitter_options={
            "target_chars": 100,
        },
        chunk_recall_limit=20,
        final_paper_limit=5,
    )


def test_partial_corpus_returns_ranked_results():
    paper_a = "a" * 40
    paper_b = "b" * 40
    paper_c = "c" * 40

    reader = _StubReader(
        chunks=(
            _build_chunk(
                paper_id=paper_a,
                text=(
                    "Agent memory trajectory "
                    "learning."
                ),
            ),
            _build_chunk(
                paper_id=paper_b,
                text=(
                    "Agent memory retrieval."
                ),
            ),
        ),
        loaded_paper_ids=(
            paper_a,
            paper_b,
        ),
        missing_paper_ids=(
            paper_c,
        ),
    )

    result = search_candidate_fulltext(
        request=_build_request(
            (
                paper_a,
                paper_b,
                paper_c,
            )
        ),
        corpus_reader=reader,
        chunk_retriever=(
            BM25ChunkRetriever()
        ),
        paper_aggregator=(
            PaperScoreAggregator()
        ),
    )

    assert result.success
    assert result.status == "partial"
    assert result.missing_paper_ids == (
        paper_c,
    )
    assert result.paper_search_result
    assert (
        result
        .paper_search_result
        .hits[0]
        .paper_id
        == paper_a
    )
    assert (
        result.relative_scores[paper_a]
        == 100.0
    )


def test_no_ready_chunks_returns_failure():
    paper_id = "a" * 40

    result = search_candidate_fulltext(
        request=_build_request(
            (paper_id,)
        ),
        corpus_reader=_StubReader(
            chunks=(),
            loaded_paper_ids=(),
            missing_paper_ids=(
                paper_id,
            ),
        ),
        chunk_retriever=(
            BM25ChunkRetriever()
        ),
        paper_aggregator=(
            PaperScoreAggregator()
        ),
    )

    assert not result.success
    assert result.status == "no_ready_chunks"
    assert result.paper_search_result is None
    assert paper_id in result.errors
