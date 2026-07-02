"""将 Topic 到 Markdown 结果继续处理为论文级全文证据。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ai4research.indexing_pipeline.pipelines.candidate_fulltext_search import (
    CandidateFullTextSearchRequest,
    CandidateFullTextSearchResult,
    search_candidate_fulltext,
)
from ai4research.indexing_pipeline.pipelines.document_chunk_pipeline import (
    DocumentChunkPipelineRequest,
    process_document_chunks,
)
from ai4research.indexing_pipeline.repositories.base import (
    ChunkRepository,
)
from ai4research.indexing_pipeline.repositories.document_source import (
    load_indexable_document_source,
)
from ai4research.indexing_pipeline.repositories.reader import (
    ChunkCorpusReader,
)
from ai4research.indexing_pipeline.retrieval.base import (
    ChunkRetriever,
)
from ai4research.indexing_pipeline.retrieval.paper_aggregation import (
    PaperScoreAggregator,
)
from ai4research.indexing_pipeline.splitters.base import (
    DocumentSplitter,
)
from ai4research.research_pipeline.pipelines.topic_to_documents import (
    TopicWorkflowResult,
)


@dataclass(frozen=True)
class TopicChunkOutcome:
    """一篇 Topic 候选论文的 chunk 处理结果。"""

    paper_id: str
    success: bool
    status: str

    chunk_count: int = 0
    chunks_relative_path: str = ""
    manifest_relative_path: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TopicEvidenceWorkflowResult:
    """Topic → Markdown → chunk → 全文证据结果。"""

    topic_result: TopicWorkflowResult
    chunk_outcomes: tuple[
        TopicChunkOutcome,
        ...,
    ]

    fulltext_result: (
        CandidateFullTextSearchResult | None
    )

    success: bool
    status: str
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "error": self.error,
            "topic_result": (
                self.topic_result.to_dict()
            ),
            "chunk_outcomes": [
                outcome.to_dict()
                for outcome
                in self.chunk_outcomes
            ],
            "fulltext_result": (
                self.fulltext_result.to_dict()
                if self.fulltext_result
                else None
            ),
        }


def run_topic_to_evidence(
    *,
    topic_result: TopicWorkflowResult,
    query: str,
    splitter: DocumentSplitter,
    chunk_repository: ChunkRepository,
    corpus_reader: ChunkCorpusReader,
    chunk_retriever: ChunkRetriever,
    paper_aggregator: PaperScoreAggregator,
    chunk_recall_limit: int = 300,
    final_paper_limit: int = 5,
) -> TopicEvidenceWorkflowResult:
    """处理 Topic 候选的 chunk，并执行全文二次检索。"""

    normalized_query = query.strip()

    if not normalized_query:
        raise ValueError("query 不能为空")

    if chunk_recall_limit <= 0:
        raise ValueError(
            "chunk_recall_limit 必须大于 0"
        )

    if final_paper_limit <= 0:
        raise ValueError(
            "final_paper_limit 必须大于 0"
        )

    candidate_paper_ids = tuple(
        candidate.paper_id
        for candidate
        in topic_result.candidates
    )

    if not candidate_paper_ids:
        return TopicEvidenceWorkflowResult(
            topic_result=topic_result,
            chunk_outcomes=(),
            fulltext_result=None,
            success=True,
            status="no_candidates",
        )

    outcomes_by_paper_id = {
        outcome.paper_id: outcome
        for outcome in topic_result.outcomes
    }

    chunk_outcomes = []

    for paper_id in candidate_paper_ids:
        document_outcome = (
            outcomes_by_paper_id.get(
                paper_id
            )
        )

        if (
            document_outcome is None
            or not document_outcome.ready
        ):
            chunk_outcomes.append(
                TopicChunkOutcome(
                    paper_id=paper_id,
                    success=False,
                    status=(
                        "document_not_ready"
                    ),
                    error=(
                        document_outcome.error
                        if document_outcome
                        else "document_outcome_missing"
                    ),
                )
            )
            continue

        try:
            source = (
                load_indexable_document_source(
                    paper_id=paper_id
                )
            )

            chunk_result = (
                process_document_chunks(
                    request=(
                        DocumentChunkPipelineRequest(
                            paper_id=(
                                source.paper_id
                            ),
                            markdown_path=(
                                source.markdown_path
                            ),
                            source_markdown_relative_path=(
                                source
                                .markdown_relative_path
                            ),
                            source_pdf_sha256=(
                                source
                                .source_pdf_sha256
                            ),
                            source_parser_name=(
                                source.parser_name
                            ),
                            source_parser_version=(
                                source.parser_version
                            ),
                            title=source.title,
                        )
                    ),
                    splitter=splitter,
                    repository=(
                        chunk_repository
                    ),
                )
            )

            chunk_outcomes.append(
                TopicChunkOutcome(
                    paper_id=paper_id,
                    success=(
                        chunk_result.success
                    ),
                    status=chunk_result.status,
                    chunk_count=(
                        chunk_result.chunk_count
                    ),
                    chunks_relative_path=(
                        chunk_result
                        .chunks_relative_path
                    ),
                    manifest_relative_path=(
                        chunk_result
                        .manifest_relative_path
                    ),
                    error=chunk_result.error,
                )
            )

        except Exception as error:
            chunk_outcomes.append(
                TopicChunkOutcome(
                    paper_id=paper_id,
                    success=False,
                    status="chunk_failed",
                    error=(
                        f"{type(error).__name__}: "
                        f"{error}"
                    )[:4000],
                )
            )

    fulltext_result = (
        search_candidate_fulltext(
            request=(
                CandidateFullTextSearchRequest(
                    query=normalized_query,
                    candidate_paper_ids=(
                        candidate_paper_ids
                    ),
                    splitter_name=(
                        splitter.name
                    ),
                    splitter_version=(
                        splitter.version
                    ),
                    splitter_options=(
                        splitter.options
                    ),
                    chunk_recall_limit=(
                        chunk_recall_limit
                    ),
                    final_paper_limit=(
                        final_paper_limit
                    ),
                )
            ),
            corpus_reader=corpus_reader,
            chunk_retriever=(
                chunk_retriever
            ),
            paper_aggregator=(
                paper_aggregator
            ),
        )
    )

    return TopicEvidenceWorkflowResult(
        topic_result=topic_result,
        chunk_outcomes=tuple(
            chunk_outcomes
        ),
        fulltext_result=fulltext_result,
        success=fulltext_result.success,
        status=fulltext_result.status,
        error=fulltext_result.error,
    )
