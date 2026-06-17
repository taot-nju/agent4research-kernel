"""
文档解析任务的 MongoDB 仓库操作。

当前模块首先负责同步 PDF 资产状态与文档解析任务状态：

    pdf_asset.status = success
        document_asset.status: blocked -> pending

    pdf_asset.status != success
        document_asset.status: pending -> blocked

已经进入 running、success、failed、stale 等状态的文档任务
不会被可用性刷新逻辑覆盖。
"""

from dataclasses import asdict, dataclass

from datetime import datetime, timedelta, timezone
from pymongo import ReturnDocument
from typing import Any

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)


@dataclass(frozen=True)
class DocumentAvailabilityRefreshResult:
    """一次文档任务可用性刷新的统计结果。"""

    blocked_to_pending: int = 0
    pending_to_blocked: int = 0

    @property
    def modified_count(self) -> int:
        """返回本次实际修改的总记录数。"""

        return (
            self.blocked_to_pending
            + self.pending_to_blocked
        )

    def to_dict(self) -> dict[str, int]:
        """转换为普通字典。"""

        result = asdict(self)
        result["modified_count"] = self.modified_count
        return result


def utc_now() -> datetime:
    """返回带 UTC 时区信息的当前时间。"""

    return datetime.now(timezone.utc)


def _combine_filters(
    *conditions: dict[str, Any],
) -> dict[str, Any]:
    """将多个 MongoDB 查询条件安全组合成 $and。"""

    effective_conditions = [
        condition
        for condition in conditions
        if condition
    ]

    if not effective_conditions:
        return {}

    if len(effective_conditions) == 1:
        return effective_conditions[0]

    return {
        "$and": effective_conditions,
    }


def refresh_document_availability(
    *,
    selection_filter: dict[str, Any] | None = None,
) -> DocumentAvailabilityRefreshResult:
    """
    根据本地 PDF 状态刷新文档解析任务的可用性。

    规则一：

        pdf_asset.status = success
        document_asset.status = blocked

            -> document_asset.status = pending

    表示本地 PDF 已经准备完成，可以进入文档解析流程。

    规则二：

        pdf_asset.status != success
        document_asset.status = pending

            -> document_asset.status = blocked

    表示当前没有可用的本地 PDF，不能被文档解析 Worker 领取。

    注意：

    - 不修改 running、success、failed、stale；
    - 不修改质量状态、解析器信息和已有资产路径；
    - selection_filter 可限定论文、会议或其他业务范围；
    - 本函数可以重复执行。
    """

    if selection_filter is not None:
        if not isinstance(selection_filter, dict):
            raise TypeError(
                "selection_filter 必须是字典或 None"
            )

    business_filter = selection_filter or {}
    now = utc_now()
    papers = MongoDBClient.get_collection()

    blocked_to_pending_filter = _combine_filters(
        business_filter,
        {
            "pdf_asset.status": "success",
        },
        {
            "document_asset.status": "blocked",
        },
    )

    blocked_to_pending_result = papers.update_many(
        blocked_to_pending_filter,
        {
            "$set": {
                "document_asset.status": "pending",
                "document_asset.last_error": "",
                "document_asset.next_retry_at": None,
                "document_asset.worker_id": "",
                "document_asset.lease_until": None,
                "document_asset.updated_at": now,
            }
        },
    )

    pending_to_blocked_filter = _combine_filters(
        business_filter,
        {
            "pdf_asset.status": {
                "$ne": "success",
            },
        },
        {
            "document_asset.status": "pending",
        },
    )

    pending_to_blocked_result = papers.update_many(
        pending_to_blocked_filter,
        {
            "$set": {
                "document_asset.status": "blocked",
                "document_asset.last_error": (
                    "source_pdf_not_available"
                ),
                "document_asset.next_retry_at": None,
                "document_asset.worker_id": "",
                "document_asset.lease_until": None,
                "document_asset.updated_at": now,
            }
        },
    )

    return DocumentAvailabilityRefreshResult(
        blocked_to_pending=(
            blocked_to_pending_result.modified_count
        ),
        pending_to_blocked=(
            pending_to_blocked_result.modified_count
        ),
    )

def build_claimable_document_task_filter(
    *,
    selection_filter: dict[str, Any] | None,
    max_attempts: int,
    now: datetime,
) -> dict[str, Any]:
    """
    生成可领取文档解析任务的 MongoDB 查询条件。

    可以领取：

    1. pending：
       已有可用 PDF，尚未开始解析；

    2. failed：
       解析失败，但仍未达到最大尝试次数，
       并且已经到达 next_retry_at；

    3. stale：
       来源 PDF 已变化，需要重新解析；

    4. running：
       原 Worker 异常退出，并且任务租约已经过期。

    无论哪种状态，都必须满足：

        pdf_asset.status = success
        pdf_asset.relative_path 非空
        pdf_asset.sha256 非空
        document_asset.attempts < max_attempts
    """

    if max_attempts <= 0:
        raise ValueError("max_attempts 必须大于 0")

    business_filter = selection_filter or {}

    retry_ready_filter = {
        "$or": [
            {
                "document_asset.status": "pending",
            },
            {
                "document_asset.status": "stale",
            },
            {
                "$and": [
                    {
                        "document_asset.status": "failed",
                    },
                    {
                        "$or": [
                            {
                                "document_asset.next_retry_at": None,
                            },
                            {
                                "document_asset.next_retry_at": {
                                    "$lte": now,
                                }
                            },
                        ]
                    },
                ]
            },
            {
                "$and": [
                    {
                        "document_asset.status": "running",
                    },
                    {
                        "$or": [
                            {
                                "document_asset.lease_until": None,
                            },
                            {
                                "document_asset.lease_until": {
                                    "$lte": now,
                                }
                            },
                        ]
                    },
                ]
            },
        ]
    }

    return _combine_filters(
        business_filter,
        {
            "pdf_asset.status": "success",
        },
        {
            "pdf_asset.relative_path": {
                "$type": "string",
                "$gt": "",
            },
        },
        {
            "pdf_asset.sha256": {
                "$type": "string",
                "$gt": "",
            },
        },
        {
            "document_asset.attempts": {
                "$lt": max_attempts,
            },
        },
        retry_ready_filter,
    )


def claim_next_document_task(
    *,
    worker_id: str,
    selection_filter: dict[str, Any] | None = None,
    lease_seconds: int = 600,
    max_attempts: int = 3,
) -> dict[str, Any] | None:
    """
    原子领取一条可执行的文档解析任务。

    领取成功后会原子更新：

        document_asset.status       -> running
        document_asset.worker_id    -> 当前 Worker
        document_asset.lease_until  -> 当前时间 + 租约
        document_asset.started_at   -> 当前时间
        document_asset.updated_at   -> 当前时间
        document_asset.attempts     -> attempts + 1

    使用 find_one_and_update 保证多个 Worker 不会同时领取
    同一篇论文。

    返回：
        领取成功时返回更新后的论文记录；
        没有可领取任务时返回 None。
    """

    normalized_worker_id = worker_id.strip()

    if not normalized_worker_id:
        raise ValueError("worker_id 不能为空")

    if selection_filter is not None:
        if not isinstance(selection_filter, dict):
            raise TypeError(
                "selection_filter 必须是字典或 None"
            )

    if lease_seconds <= 0:
        raise ValueError("lease_seconds 必须大于 0")

    if max_attempts <= 0:
        raise ValueError("max_attempts 必须大于 0")

    now = utc_now()
    lease_until = now + timedelta(
        seconds=lease_seconds
    )

    claim_filter = build_claimable_document_task_filter(
        selection_filter=selection_filter,
        max_attempts=max_attempts,
        now=now,
    )

    papers = MongoDBClient.get_collection()

    return papers.find_one_and_update(
        claim_filter,
        {
            "$set": {
                "document_asset.status": "running",
                "document_asset.worker_id": (
                    normalized_worker_id
                ),
                "document_asset.lease_until": lease_until,
                "document_asset.started_at": now,
                "document_asset.updated_at": now,
            },
            "$inc": {
                "document_asset.attempts": 1,
            },
        },
        sort=[
            ("_id", 1),
        ],
        return_document=ReturnDocument.AFTER,
    )


def build_owned_running_document_task_filter(
    *,
    paper_id: str,
    worker_id: str,
) -> dict[str, Any]:
    """
    生成“任务仍由当前 Worker 持有”的查询条件。

    后续续租、成功回写、失败回写都会复用该条件，
    防止旧 Worker 覆盖已经被其他 Worker 接管的任务。
    """

    normalized_paper_id = paper_id.strip()
    normalized_worker_id = worker_id.strip()

    if not normalized_paper_id:
        raise ValueError("paper_id 不能为空")

    if not normalized_worker_id:
        raise ValueError("worker_id 不能为空")

    return {
        "_id": normalized_paper_id,
        "document_asset.status": "running",
        "document_asset.worker_id": normalized_worker_id,
    }


def renew_document_task_lease(
    *,
    paper_id: str,
    worker_id: str,
    lease_seconds: int = 600,
) -> bool:
    """
    延长当前 Worker 持有的文档解析任务租约。

    只有同时满足以下条件时才能续租：

        document_asset.status = running
        document_asset.worker_id = 当前 Worker

    如果任务已经结束，或已被其他 Worker 接管，则续租失败。

    返回：
        续租成功返回 True；
        当前 Worker 已失去任务所有权时返回 False。
    """

    if lease_seconds <= 0:
        raise ValueError("lease_seconds 必须大于 0")

    now = utc_now()
    lease_until = now + timedelta(
        seconds=lease_seconds
    )

    papers = MongoDBClient.get_collection()

    result = papers.update_one(
        build_owned_running_document_task_filter(
            paper_id=paper_id,
            worker_id=worker_id,
        ),
        {
            "$set": {
                "document_asset.lease_until": lease_until,
                "document_asset.updated_at": now,
            }
        },
    )

    return result.modified_count == 1


def mark_document_task_failed(
    *,
    paper_id: str,
    worker_id: str,
    error: str,
    retry_delay_seconds: int = 60,
) -> bool:
    """
    将当前 Worker 持有的文档解析任务标记为失败。

    只有任务仍满足以下条件时才能回写：

        document_asset.status = running
        document_asset.worker_id = 当前 Worker

    失败后：

        status         -> failed
        last_error     -> 本次错误
        next_retry_at  -> 当前时间 + 重试等待时间
        worker_id      -> 清空
        lease_until    -> 清空

    attempts 在任务领取时已经增加，本函数不会再次修改它。

    返回：
        回写成功返回 True；
        当前 Worker 已失去任务所有权时返回 False。
    """

    if retry_delay_seconds <= 0:
        raise ValueError(
            "retry_delay_seconds 必须大于 0"
        )

    normalized_error = error.strip()

    if not normalized_error:
        raise ValueError("error 不能为空")

    now = utc_now()
    next_retry_at = now + timedelta(
        seconds=retry_delay_seconds
    )

    papers = MongoDBClient.get_collection()

    result = papers.update_one(
        build_owned_running_document_task_filter(
            paper_id=paper_id,
            worker_id=worker_id,
        ),
        {
            "$set": {
                "document_asset.status": "failed",
                "document_asset.last_error": normalized_error,
                "document_asset.last_checked_at": now,
                "document_asset.next_retry_at": next_retry_at,
                "document_asset.updated_at": now,
                "document_asset.worker_id": "",
                "document_asset.lease_until": None,
            }
        },
    )

    return result.modified_count == 1


def mark_document_task_success(
    *,
    paper_id: str,
    worker_id: str,
    parser_name: str,
    parser_version: str,
    source_pdf_relative_path: str,
    source_pdf_sha256: str,
    document_relative_dir: str,
    markdown_relative_path: str = "",
    plain_text_relative_path: str = "",
    layout_relative_path: str = "",
    report_relative_path: str = "",
    raw_output_relative_path: str = "",
    page_count: int = 0,
    char_count: int = 0,
    duration_seconds: float = 0.0,
    parser_options: dict[str, Any] | None = None,
    warnings: list[str] | tuple[str, ...] | None = None,
) -> bool:
    """
    将当前 Worker 持有的文档解析任务标记为成功。

    除任务所有权外，还会检查：

        pdf_asset.sha256 = source_pdf_sha256

    这样可以防止 PDF 在解析期间被替换后，旧解析结果覆盖
    新 PDF 对应的文档状态。

    success 仅表示解析程序成功生成了标准资产；
    解析质量仍由后续独立质量检查流程判断。
    """

    normalized_parser_name = parser_name.strip()
    normalized_parser_version = parser_version.strip()
    normalized_pdf_path = source_pdf_relative_path.strip()
    normalized_pdf_sha256 = source_pdf_sha256.strip()
    normalized_document_dir = document_relative_dir.strip()

    if not normalized_parser_name:
        raise ValueError("parser_name 不能为空")

    if not normalized_parser_version:
        raise ValueError("parser_version 不能为空")

    if not normalized_pdf_path:
        raise ValueError(
            "source_pdf_relative_path 不能为空"
        )

    if not normalized_pdf_sha256:
        raise ValueError(
            "source_pdf_sha256 不能为空"
        )

    if not normalized_document_dir:
        raise ValueError(
            "document_relative_dir 不能为空"
        )

    if page_count < 0:
        raise ValueError("page_count 不能小于 0")

    if char_count < 0:
        raise ValueError("char_count 不能小于 0")

    if duration_seconds < 0:
        raise ValueError(
            "duration_seconds 不能小于 0"
        )

    normalized_warnings = [
        str(warning).strip()
        for warning in (warnings or [])
        if str(warning).strip()
    ]

    now = utc_now()
    papers = MongoDBClient.get_collection()

    update_filter = _combine_filters(
        build_owned_running_document_task_filter(
            paper_id=paper_id,
            worker_id=worker_id,
        ),
        {
            "pdf_asset.sha256": normalized_pdf_sha256,
        },
    )

    result = papers.update_one(
        update_filter,
        {
            "$set": {
                "document_asset.status": "success",
                "document_asset.parser_name": (
                    normalized_parser_name
                ),
                "document_asset.parser_version": (
                    normalized_parser_version
                ),
                "document_asset.parser_options": dict(
                    parser_options or {}
                ),
                "document_asset.source_pdf_relative_path": (
                    normalized_pdf_path
                ),
                "document_asset.source_pdf_sha256": (
                    normalized_pdf_sha256
                ),
                "document_asset.document_relative_dir": (
                    normalized_document_dir
                ),
                "document_asset.markdown_relative_path": (
                    markdown_relative_path.strip()
                ),
                "document_asset.plain_text_relative_path": (
                    plain_text_relative_path.strip()
                ),
                "document_asset.layout_relative_path": (
                    layout_relative_path.strip()
                ),
                "document_asset.report_relative_path": (
                    report_relative_path.strip()
                ),
                "document_asset.raw_output_relative_path": (
                    raw_output_relative_path.strip()
                ),
                "document_asset.page_count": page_count,
                "document_asset.char_count": char_count,
                "document_asset.duration_seconds": (
                    duration_seconds
                ),
                "document_asset.quality_status": "unchecked",
                "document_asset.quality_score": None,
                "document_asset.quality_checks": {},
                "document_asset.warnings": normalized_warnings,
                "document_asset.last_error": "",
                "document_asset.last_checked_at": None,
                "document_asset.next_retry_at": None,
                "document_asset.parsed_at": now,
                "document_asset.updated_at": now,
                "document_asset.worker_id": "",
                "document_asset.lease_until": None,
            }
        },
    )

    return result.modified_count == 1