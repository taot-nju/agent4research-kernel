"""
Research Topic 到标准文档资产的上层工作流。

流程：

Topic 召回
→ PDF 下载或跳过
→ 刷新文档可用性
→ OCR 或跳过
→ 质量检查或跳过
→ 按召回顺序返回 Markdown 路径
"""

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.document_pipeline.parsers.base import (
    DocumentParser,
)
from ai4research.document_pipeline.pipelines.document_parse_runner import (
    run_document_parse_tasks,
)
from ai4research.document_pipeline.pipelines.document_quality_runner import (
    run_document_quality_checks,
)
from ai4research.document_pipeline.quality_checks.base import (
    DocumentQualityChecker,
)
from ai4research.document_pipeline.repositories.document_task_repository import (
    refresh_document_availability,
)
from ai4research.fulltext_pipeline.pipelines.concurrent_pdf_download_runner import (
    run_concurrent_pdf_download_tasks,
)
from ai4research.fulltext_pipeline.pipelines.pdf_download_runner import (
    run_pdf_download_tasks,
)
from ai4research.fulltext_pipeline.repositories.pdf_task_repository import (
    refresh_unavailable_pdf_tasks,
)
from ai4research.fulltext_pipeline.utils.pdf_url_resolver import (
    has_pdf_candidate,
)
from ai4research.fulltext_pipeline.utils.storage_paths import (
    resolve_asset_path,
)
from ai4research.research_pipeline.retrieval.base import (
    TopicCandidate,
    TopicRetriever,
)


@dataclass(frozen=True)
class TopicDocumentOutcome:
    """一篇 Topic 候选论文的最终处理结果。"""

    rank: int
    paper_id: str
    title: str
    accepted_by: str
    retrieval_score: float
    matched_fields: tuple[str, ...]

    pdf_status: str
    document_status: str
    quality_status: str

    markdown_relative_path: str
    markdown_absolute_path: str
    ready: bool
    error: str

    def to_dict(self) -> dict[str, Any]:
        """转换为普通字典。"""

        return asdict(self)


@dataclass(frozen=True)
class TopicWorkflowResult:
    """一次 Research Topic 工作流结果。"""

    topic: str
    retriever_name: str
    retriever_version: str
    candidates: tuple[TopicCandidate, ...]

    refreshed_pdf_tasks: int
    document_availability_changes: int

    pdf_summary: dict[str, Any]
    document_summary: dict[str, Any]
    quality_summary: dict[str, Any]

    outcomes: tuple[
        TopicDocumentOutcome,
        ...
    ]

    def to_dict(self) -> dict[str, Any]:
        """转换为普通字典。"""

        return {
            "topic": self.topic,
            "retriever_name": (
                self.retriever_name
            ),
            "retriever_version": (
                self.retriever_version
            ),
            "candidates": [
                candidate.to_dict()
                for candidate
                in self.candidates
            ],
            "refreshed_pdf_tasks": (
                self.refreshed_pdf_tasks
            ),
            "document_availability_changes": (
                self.document_availability_changes
            ),
            "pdf_summary": self.pdf_summary,
            "document_summary": (
                self.document_summary
            ),
            "quality_summary": (
                self.quality_summary
            ),
            "outcomes": [
                outcome.to_dict()
                for outcome in self.outcomes
            ],
        }

def select_processable_topic_candidates(
    *,
    topic: str,
    top_k: int,
    candidate_scan_limit: int,
    retriever: TopicRetriever,
) -> list[TopicCandidate]:
    """按相关性选择具备 PDF 处理条件的候选论文。"""

    normalized_topic = topic.strip()

    if not normalized_topic:
        raise ValueError("topic 不能为空")

    if top_k <= 0:
        raise ValueError("top_k 必须大于 0")

    if candidate_scan_limit <= 0:
        raise ValueError(
            "candidate_scan_limit 必须大于 0"
        )

    recalled_candidates = retriever.search(
        topic=normalized_topic,
        limit=max(top_k, candidate_scan_limit),
    )

    if not recalled_candidates:
        return []

    collection = MongoDBClient.get_collection()
    paper_ids = [
        candidate.paper_id
        for candidate in recalled_candidates
    ]

    documents = {
        str(document["_id"]): document
        for document in collection.find(
            {"_id": {"$in": paper_ids}}
        )
    }

    selected_candidates = []

    for candidate in recalled_candidates:
        document = documents.get(
            candidate.paper_id,
            {},
        )
        pdf_asset = document.get(
            "pdf_asset",
            {},
        )

        if not isinstance(pdf_asset, dict):
            pdf_asset = {}

        pdf_status = str(
            pdf_asset.get("status", "")
        )

        if (
            pdf_status != "success"
            and not has_pdf_candidate(document)
        ):
            continue

        selected_candidates.append(candidate)

        if len(selected_candidates) >= top_k:
            break

    return selected_candidates

def _build_outcomes(
    *,
    candidates: list[TopicCandidate],
) -> tuple[TopicDocumentOutcome, ...]:
    """按召回顺序收集最终状态和 Markdown 路径。"""

    if not candidates:
        return ()

    papers = MongoDBClient.get_collection()

    paper_ids = [
        candidate.paper_id
        for candidate in candidates
    ]

    documents = {
        str(document["_id"]): document
        for document in papers.find(
            {
                "_id": {
                    "$in": paper_ids,
                }
            },
            {
                "pdf_asset.status": 1,
                "document_asset.status": 1,
                "document_asset.quality_status": 1,
                "document_asset.markdown_relative_path": 1,
            },
        )
    }

    outcomes = []

    for rank, candidate in enumerate(
        candidates,
        start=1,
    ):
        document = documents.get(
            candidate.paper_id,
            {},
        )
        pdf_asset = document.get(
            "pdf_asset",
            {},
        )
        document_asset = document.get(
            "document_asset",
            {},
        )

        pdf_status = str(
            pdf_asset.get(
                "status",
                "",
            )
        )
        document_status = str(
            document_asset.get(
                "status",
                "",
            )
        )
        quality_status = str(
            document_asset.get(
                "quality_status",
                "",
            )
        )
        markdown_relative_path = str(
            document_asset.get(
                "markdown_relative_path",
                "",
            )
        ).strip()

        markdown_absolute_path = ""
        ready = False
        error = ""

        if markdown_relative_path:
            try:
                absolute_path = resolve_asset_path(
                    markdown_relative_path
                )

                if absolute_path.exists():
                    markdown_absolute_path = str(
                        absolute_path
                    )
                    ready = True
                else:
                    error = (
                        "markdown_file_missing"
                    )

            except Exception as path_error:
                error = (
                    "invalid_markdown_path: "
                    f"{type(path_error).__name__}: "
                    f"{path_error}"
                )

        elif pdf_status != "success":
            error = (
                f"pdf_status={pdf_status or 'missing'}"
            )

        elif document_status != "success":
            error = (
                "document_status="
                f"{document_status or 'missing'}"
            )

        else:
            error = "markdown_path_missing"

        if quality_status == "rejected":
            ready = False
            error = "quality_rejected"

        outcomes.append(
            TopicDocumentOutcome(
                rank=rank,
                paper_id=candidate.paper_id,
                title=candidate.title,
                accepted_by=(
                    candidate.accepted_by
                ),
                retrieval_score=(
                    candidate.score
                ),
                matched_fields=(
                    candidate.matched_fields
                ),
                pdf_status=pdf_status,
                document_status=(
                    document_status
                ),
                quality_status=(
                    quality_status
                ),
                markdown_relative_path=(
                    markdown_relative_path
                ),
                markdown_absolute_path=(
                    markdown_absolute_path
                ),
                ready=ready,
                error=error,
            )
        )

    return tuple(outcomes)


def run_topic_to_documents(
    *,
    topic: str,
    top_k: int,
    candidate_scan_limit: int,
    retriever: TopicRetriever,
    document_parser: DocumentParser,
    quality_checker: DocumentQualityChecker,
    worker_id_prefix: str,
    parser_options: Mapping[str, Any] | None = None,
    download_workers: int = 1,
    pdf_lease_seconds: int = 600,
    document_lease_seconds: int = 3600,
    max_attempts: int = 3,
    retry_delay_seconds: int = 60,
    recheck_quality: bool = False,
) -> TopicWorkflowResult:
    """执行完整的 Topic 到 Markdown 工作流。"""

    normalized_topic = topic.strip()
    normalized_worker_id = (
        worker_id_prefix.strip()
    )

    if not normalized_topic:
        raise ValueError(
            "topic 不能为空"
        )

    if top_k <= 0:
        raise ValueError(
            "top_k 必须大于 0"
        )

    if not normalized_worker_id:
        raise ValueError(
            "worker_id_prefix 不能为空"
        )

    if download_workers <= 0:
        raise ValueError(
            "download_workers 必须大于 0"
        )

    if pdf_lease_seconds <= 0:
        raise ValueError(
            "pdf_lease_seconds 必须大于 0"
        )

    if document_lease_seconds <= 0:
        raise ValueError(
            "document_lease_seconds 必须大于 0"
        )

    if max_attempts <= 0:
        raise ValueError(
            "max_attempts 必须大于 0"
        )

    if retry_delay_seconds <= 0:
        raise ValueError(
            "retry_delay_seconds 必须大于 0"
        )

    # candidates = retriever.search(
    #     topic=normalized_topic,
    #     limit=top_k,
    # )

    candidates = select_processable_topic_candidates(
        topic=normalized_topic,
        top_k=top_k,
        candidate_scan_limit=candidate_scan_limit,
        retriever=retriever,
    )

    if not candidates:
        return TopicWorkflowResult(
            topic=normalized_topic,
            retriever_name=retriever.name,
            retriever_version=(
                retriever.version
            ),
            candidates=(),
            refreshed_pdf_tasks=0,
            document_availability_changes=0,
            pdf_summary={},
            document_summary={},
            quality_summary={},
            outcomes=(),
        )

    paper_ids = [
        candidate.paper_id
        for candidate in candidates
    ]

    selection_filter = {
        "_id": {
            "$in": paper_ids,
        }
    }

    # unavailable 论文如果后来出现 URL，
    # 先恢复为 pending。
    refreshed_pdf_tasks = (
        refresh_unavailable_pdf_tasks(
            selection_filter=(
                selection_filter
            )
        )
    )

    if download_workers == 1:
        pdf_summary_object = (
            run_pdf_download_tasks(
                worker_id=(
                    f"{normalized_worker_id}-pdf"
                ),
                selection_filter=(
                    selection_filter
                ),
                limit=top_k,
                lease_seconds=(
                    pdf_lease_seconds
                ),
                max_attempts=max_attempts,
                retry_delay_seconds=(
                    retry_delay_seconds
                ),
            )
        )
    else:
        pdf_summary_object = (
            run_concurrent_pdf_download_tasks(
                worker_id_prefix=(
                    f"{normalized_worker_id}-pdf"
                ),
                selection_filter=(
                    selection_filter
                ),
                limit=top_k,
                max_workers=(
                    download_workers
                ),
                lease_seconds=(
                    pdf_lease_seconds
                ),
                max_attempts=max_attempts,
                retry_delay_seconds=(
                    retry_delay_seconds
                ),
            )
        )

    availability_result = (
        refresh_document_availability(
            selection_filter=(
                selection_filter
            )
        )
    )

    document_summary_object = (
        run_document_parse_tasks(
            worker_id=(
                f"{normalized_worker_id}-document"
            ),
            selection_filter=(
                selection_filter
            ),
            limit=top_k,
            parser=document_parser,
            parser_options=parser_options,
            lease_seconds=(
                document_lease_seconds
            ),
            max_attempts=max_attempts,
            retry_delay_seconds=(
                retry_delay_seconds
            ),
        )
    )

    quality_summary_object = (
        run_document_quality_checks(
            selection_filter=(
                selection_filter
            ),
            limit=top_k,
            checker=quality_checker,
            recheck=recheck_quality,
        )
    )

    outcomes = _build_outcomes(
        candidates=candidates
    )

    return TopicWorkflowResult(
        topic=normalized_topic,
        retriever_name=retriever.name,
        retriever_version=(
            retriever.version
        ),
        candidates=tuple(candidates),
        refreshed_pdf_tasks=(
            refreshed_pdf_tasks
        ),
        document_availability_changes=(
            availability_result.modified_count
        ),
        pdf_summary=(
            pdf_summary_object.to_dict()
        ),
        document_summary=(
            document_summary_object.to_dict()
        ),
        quality_summary=(
            quality_summary_object.to_dict()
        ),
        outcomes=outcomes,
    )
