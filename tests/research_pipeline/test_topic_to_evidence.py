"""Topic → chunk → 全文证据编排测试。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from ai4research.indexing_pipeline.pipelines.document_chunk_pipeline import (
    DocumentChunkPipelineResult,
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
from ai4research.indexing_pipeline.splitters.markdown_block_splitter import (
    MarkdownBlockSplitter,
)
from ai4research.research_pipeline.pipelines import (
    topic_to_evidence,
)
from ai4research.research_pipeline.pipelines.topic_to_documents import (
    TopicDocumentOutcome,
    TopicWorkflowResult,
)
from ai4research.research_pipeline.retrieval.base import (
    TopicCandidate,
)
from ai4research.research_pipeline.scripts_py.process_research_topic_evidence import (
    build_argument_parser,
    validate_arguments,
)


class _StubCorpusReader(ChunkCorpusReader):
    def __init__(self, chunk):
        self._chunk = chunk

    def read(self, request):
        return ChunkCorpusReadResult(
            requested_paper_ids=(
                request.paper_ids
            ),
            loaded_paper_ids=(
                request.paper_ids
            ),
            missing_paper_ids=(),
            chunks=(self._chunk,),
        )


def _build_topic_result(
    *,
    paper_id: str,
) -> TopicWorkflowResult:
    candidate = TopicCandidate(
        paper_id=paper_id,
        title="Example Paper",
        accepted_by="ICLR 2026",
        score=10.0,
        matched_fields=(
            "title",
            "abstract",
        ),
    )

    outcome = TopicDocumentOutcome(
        rank=1,
        paper_id=paper_id,
        title=candidate.title,
        accepted_by=(
            candidate.accepted_by
        ),
        retrieval_score=candidate.score,
        matched_fields=(
            candidate.matched_fields
        ),
        pdf_status="success",
        document_status="success",
        quality_status="passed",
        markdown_relative_path=(
            f"documents/{paper_id[:2]}/"
            f"{paper_id[2:4]}/{paper_id}/"
            "document.md"
        ),
        markdown_absolute_path=(
            "/tmp/document.md"
        ),
        ready=True,
        error="",
    )

    return TopicWorkflowResult(
        topic="agent memory trajectory",
        retriever_name=(
            "test-metadata-retriever"
        ),
        retriever_version="1",
        candidates=(candidate,),
        refreshed_pdf_tasks=0,
        document_availability_changes=0,
        pdf_summary={},
        document_summary={},
        quality_summary={},
        outcomes=(outcome,),
    )


def test_topic_to_evidence_reuses_chunk_and_searches(
    monkeypatch,
):
    paper_id = "a" * 40
    splitter = MarkdownBlockSplitter()

    chunk = DocumentChunk.create(
        paper_id=paper_id,
        chunk_index=0,
        text=(
            "Agent memory trajectory learning."
        ),
        page_start=1,
        page_end=1,
        section_path=("Introduction",),
        source_markdown_relative_path=(
            f"documents/aa/aa/{paper_id}/"
            "document.md"
        ),
        source_markdown_sha256="d" * 64,
        source_pdf_sha256="e" * 64,
        source_parser_name="test-parser",
        source_parser_version="1",
        splitter_name=splitter.name,
        splitter_version=splitter.version,
        splitter_options=splitter.options,
    )

    monkeypatch.setattr(
        topic_to_evidence,
        "load_indexable_document_source",
        lambda **kwargs: SimpleNamespace(
            paper_id=paper_id,
            title="Example Paper",
            markdown_path=Path(
                "/tmp/document.md"
            ),
            markdown_relative_path=(
                chunk
                .source_markdown_relative_path
            ),
            source_pdf_sha256=(
                chunk.source_pdf_sha256
            ),
            parser_name=(
                chunk.source_parser_name
            ),
            parser_version=(
                chunk.source_parser_version
            ),
        ),
    )

    monkeypatch.setattr(
        topic_to_evidence,
        "process_document_chunks",
        lambda **kwargs: (
            DocumentChunkPipelineResult(
                success=True,
                status="reused",
                paper_id=paper_id,
                chunk_count=1,
                source_markdown_sha256=(
                    chunk
                    .source_markdown_sha256
                ),
                splitter_name=splitter.name,
                splitter_version=(
                    splitter.version
                ),
                splitter_options=(
                    splitter.options
                ),
                chunks_relative_path=(
                    "chunks/test/chunks.jsonl"
                ),
                manifest_relative_path=(
                    "chunks/test/manifest.json"
                ),
            )
        ),
    )

    result = (
        topic_to_evidence
        .run_topic_to_evidence(
            topic_result=(
                _build_topic_result(
                    paper_id=paper_id
                )
            ),
            query=(
                "agent memory trajectory"
            ),
            splitter=splitter,
            chunk_repository=object(),
            corpus_reader=(
                _StubCorpusReader(chunk)
            ),
            chunk_retriever=(
                BM25ChunkRetriever()
            ),
            paper_aggregator=(
                PaperScoreAggregator()
            ),
            chunk_recall_limit=10,
            final_paper_limit=1,
        )
    )

    assert result.success
    assert result.status == "complete"
    assert (
        result.chunk_outcomes[0].status
        == "reused"
    )
    assert result.fulltext_result
    assert (
        result
        .fulltext_result
        .paper_search_result
        .hits[0]
        .paper_id
        == paper_id
    )


def test_topic_to_evidence_handles_no_candidates():
    empty_topic_result = TopicWorkflowResult(
        topic="no result",
        retriever_name="test",
        retriever_version="1",
        candidates=(),
        refreshed_pdf_tasks=0,
        document_availability_changes=0,
        pdf_summary={},
        document_summary={},
        quality_summary={},
        outcomes=(),
    )

    result = (
        topic_to_evidence
        .run_topic_to_evidence(
            topic_result=empty_topic_result,
            query="no result",
            splitter=object(),
            chunk_repository=object(),
            corpus_reader=object(),
            chunk_retriever=object(),
            paper_aggregator=object(),
        )
    )

    assert result.success
    assert result.status == "no_candidates"
    assert result.fulltext_result is None


def test_topic_evidence_cli_defaults_and_limits():
    parser = build_argument_parser()

    args = parser.parse_args(
        [
            "--topic",
            "agent memory trajectory",
        ]
    )

    validate_arguments(args)

    assert args.metadata_candidate_k == 30
    assert args.final_paper_k == 5
    assert args.chunk_recall_k == 300

    invalid_args = parser.parse_args(
        [
            "--topic",
            "agent memory",
            "--metadata-candidate-k",
            "3",
            "--final-paper-k",
            "4",
        ]
    )

    with pytest.raises(
        ValueError,
        match="不能大于",
    ):
        validate_arguments(invalid_args)
