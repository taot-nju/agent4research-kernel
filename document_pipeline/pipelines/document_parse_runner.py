"""
文档解析任务顺序运行器。

负责循环执行：

    原子领取一条任务
        ↓
    调用单篇文档解析 Pipeline
        ↓
    记录统计并继续领取

多论文并发版本可以复用同一个单任务 Pipeline。
"""

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from ai4research.document_pipeline.parsers.base import (
    DocumentParser,
)
from ai4research.document_pipeline.pipelines.document_parse_pipeline import (
    process_claimed_document_task,
)
from ai4research.document_pipeline.repositories.document_task_repository import (
    claim_next_document_task,
)


DEFAULT_DOCUMENT_LEASE_SECONDS = 60 * 60
DEFAULT_DOCUMENT_MAX_ATTEMPTS = 3
DEFAULT_DOCUMENT_RETRY_DELAY_SECONDS = 60


@dataclass
class DocumentRunSummary:
    """一次文档解析运行的统计结果。"""

    claimed: int = 0
    success: int = 0
    failed: int = 0
    ownership_lost: int = 0
    other: int = 0

    def record_status(
        self,
        status: str,
    ) -> None:
        """根据单篇任务状态更新统计。"""

        if status == "success":
            self.success += 1
        elif status == "failed":
            self.failed += 1
        elif status == "ownership_lost":
            self.ownership_lost += 1
        else:
            self.other += 1

    def to_dict(self) -> dict[str, int]:
        """转换为普通字典。"""

        return asdict(self)


def run_document_parse_tasks(
    *,
    worker_id: str,
    selection_filter: dict[str, Any],
    limit: int,
    parser: DocumentParser,
    parser_options: Mapping[str, Any] | None = None,
    lease_seconds: int = (
        DEFAULT_DOCUMENT_LEASE_SECONDS
    ),
    max_attempts: int = (
        DEFAULT_DOCUMENT_MAX_ATTEMPTS
    ),
    retry_delay_seconds: int = (
        DEFAULT_DOCUMENT_RETRY_DELAY_SECONDS
    ),
) -> DocumentRunSummary:
    """顺序处理一批文档解析任务。"""

    normalized_worker_id = worker_id.strip()

    if not normalized_worker_id:
        raise ValueError(
            "worker_id 不能为空"
        )

    if not isinstance(selection_filter, dict):
        raise TypeError(
            "selection_filter 必须是字典"
        )

    if limit <= 0:
        raise ValueError(
            "limit 必须大于 0"
        )

    if lease_seconds <= 0:
        raise ValueError(
            "lease_seconds 必须大于 0"
        )

    if max_attempts <= 0:
        raise ValueError(
            "max_attempts 必须大于 0"
        )

    if retry_delay_seconds <= 0:
        raise ValueError(
            "retry_delay_seconds 必须大于 0"
        )

    summary = DocumentRunSummary()

    while summary.claimed < limit:
        paper = claim_next_document_task(
            worker_id=normalized_worker_id,
            selection_filter=selection_filter,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )

        if paper is None:
            break

        summary.claimed += 1

        paper_id = str(
            paper.get("_id", "")
        )
        title = str(
            paper.get("title", "")
        )

        print("-" * 100)
        print(
            f"[OCR {summary.claimed}/{limit} claimed_limit] "
            f"paper_id={paper_id}"
        )
        print(f"title={title}")

        result = process_claimed_document_task(
            paper=paper,
            worker_id=normalized_worker_id,
            parser=parser,
            parser_options=parser_options,
            retry_delay_seconds=(
                retry_delay_seconds
            ),
            commit_lease_seconds=(
                lease_seconds
            ),
        )

        summary.record_status(
            result.status
        )

        print(
            f"status={result.status} | "
            f"pages={result.page_count} | "
            f"chars={result.char_count} | "
            f"duration={result.duration_seconds:.2f}s"
        )

        if result.error:
            print(f"error={result.error}")

    return summary
