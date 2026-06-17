"""
PDF 下载任务状态仓库。

本模块负责从 MongoDB 中原子领取 PDF 下载任务。

核心目标：
1. 多个 Worker 并发运行时，同一篇论文只能被一个 Worker 领取；
2. pending 任务可以被领取；
3. failed 且已到重试时间的任务可以被重新领取；
4. running 但租约已经过期的任务可以被其他 Worker 接管；
5. success 和 unavailable 状态不会被重复领取；
6. 支持按论文 ID、会议、年份等 MongoDB 条件筛选任务。

本模块当前只实现“领取任务”。
成功、失败、无可用链接等状态回写将在后续步骤中实现。
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ReturnDocument

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)


DEFAULT_LEASE_SECONDS = 10 * 60
DEFAULT_MAX_ATTEMPTS = 3


def utc_now() -> datetime:
    """
    返回带 UTC 时区的当前时间。

    PyMongo 会将其写入 MongoDB 的 BSON Date。
    """

    return datetime.now(timezone.utc)


def build_pdf_task_claim_query(
    *,
    now: datetime,
    selection_filter: dict[str, Any] | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict[str, Any]:
    """
    构造 PDF 任务领取条件。

    可领取的状态包括：

    1. pending；
    2. failed，并且 next_retry_at 已到期或为空；
    3. running，但 lease_until 已过期或为空。

    selection_filter 用于附加业务筛选条件，例如：

        {"accepted_by": "ICLR 2022"}

    或：

        {"_id": {"$in": paper_ids}}
    """

    if max_attempts <= 0:
        raise ValueError("max_attempts 必须大于 0")

    task_eligibility_filter: dict[str, Any] = {
        "pdf_asset.attempts": {
            "$lt": max_attempts,
        },
        "$or": [
            {
                "pdf_asset.status": "pending",
            },
            {
                "pdf_asset.status": "failed",
                "$or": [
                    {
                        "pdf_asset.next_retry_at": None,
                    },
                    {
                        "pdf_asset.next_retry_at": {
                            "$lte": now,
                        }
                    },
                ],
            },
            {
                "pdf_asset.status": "running",
                "$or": [
                    {
                        "pdf_asset.lease_until": None,
                    },
                    {
                        "pdf_asset.lease_until": {
                            "$lte": now,
                        }
                    },
                ],
            },
        ],
    }

    if not selection_filter:
        return task_eligibility_filter

    return {
        "$and": [
            selection_filter,
            task_eligibility_filter,
        ]
    }


def claim_next_pdf_task(
    *,
    worker_id: str,
    selection_filter: dict[str, Any] | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> dict[str, Any] | None:
    """
    原子领取一条 PDF 下载任务。

    MongoDB 的 find_one_and_update 是原子操作。因此，即使多个
    Worker 同时执行，也只有一个 Worker 能成功把某条记录从
    pending/failed/过期 running 更新成 running。

    参数：
        worker_id:
            当前 Worker 的唯一标识，例如：

                hostname-pid-thread

        selection_filter:
            可选的 MongoDB 查询条件。例如：

                {"accepted_by": "ICLR 2022"}

                {"_id": {"$in": paper_ids}}

        lease_seconds:
            任务租约有效时间。Worker 在该时间内拥有任务。

        max_attempts:
            一篇论文允许被领取的最大次数。

    返回：
        成功领取时，返回更新后的完整论文记录；
        没有符合条件的任务时，返回 None。
    """

    normalized_worker_id = worker_id.strip()

    if not normalized_worker_id:
        raise ValueError("worker_id 不能为空")

    if lease_seconds <= 0:
        raise ValueError("lease_seconds 必须大于 0")

    now = utc_now()
    lease_until = now + timedelta(seconds=lease_seconds)

    claim_query = build_pdf_task_claim_query(
        now=now,
        selection_filter=selection_filter,
        max_attempts=max_attempts,
    )

    papers = MongoDBClient.get_collection()

    claimed_paper = papers.find_one_and_update(
        claim_query,
        {
            "$set": {
                "pdf_asset.status": "running",
                "pdf_asset.worker_id": normalized_worker_id,
                "pdf_asset.started_at": now,
                "pdf_asset.updated_at": now,
                "pdf_asset.lease_until": lease_until,
                "pdf_asset.last_error": "",
                "pdf_asset.next_retry_at": None,
            },
            "$inc": {
                "pdf_asset.attempts": 1,
            },
        },
        # 当前先按照 _id 稳定领取。
        # 后续可以增加任务优先级字段。
        sort=[
            ("_id", 1),
        ],
        return_document=ReturnDocument.AFTER,
    )

    return claimed_paper

def build_owned_running_task_filter(
    *,
    paper_id: str,
    worker_id: str,
) -> dict[str, Any]:
    """
    构造“当前 Worker 所拥有的运行中任务”查询条件。

    状态回写时必须同时检查：
    1. 论文 ID；
    2. 当前状态为 running；
    3. worker_id 与领取任务的 Worker 一致。

    这样可以避免租约过期后，旧 Worker 覆盖新 Worker 的处理结果。
    """

    normalized_paper_id = paper_id.strip()
    normalized_worker_id = worker_id.strip()

    if not normalized_paper_id:
        raise ValueError("paper_id 不能为空")

    if not normalized_worker_id:
        raise ValueError("worker_id 不能为空")

    return {
        "_id": normalized_paper_id,
        "pdf_asset.status": "running",
        "pdf_asset.worker_id": normalized_worker_id,
    }


def mark_pdf_task_success(
    *,
    paper_id: str,
    worker_id: str,
    source: str,
    source_url: str,
    final_url: str,
    relative_path: str,
    size_bytes: int,
    file_sha256: str,
    http_status: int | None,
) -> bool:
    """
    将当前 Worker 拥有的 PDF 任务标记为 success。

    同时更新旧版兼容字段：
    - processing_status.pdf_downloaded
    - local_pdf_path

    返回：
        成功更新返回 True；
        如果任务已被其他 Worker 接管或状态不再是 running，
        返回 False。
    """

    if size_bytes <= 0:
        raise ValueError("size_bytes 必须大于 0")

    normalized_sha256 = file_sha256.strip()

    if not normalized_sha256:
        raise ValueError("file_sha256 不能为空")

    now = utc_now()
    papers = MongoDBClient.get_collection()

    result = papers.update_one(
        build_owned_running_task_filter(
            paper_id=paper_id,
            worker_id=worker_id,
        ),
        {
            "$set": {
                "pdf_asset.status": "success",
                "pdf_asset.source": source.strip(),
                "pdf_asset.source_url": source_url.strip(),
                "pdf_asset.final_url": final_url.strip(),
                "pdf_asset.relative_path": relative_path.strip(),
                "pdf_asset.size_bytes": size_bytes,
                "pdf_asset.sha256": normalized_sha256,
                "pdf_asset.http_status": http_status,
                "pdf_asset.last_error": "",
                "pdf_asset.last_checked_at": now,
                "pdf_asset.next_retry_at": None,
                "pdf_asset.downloaded_at": now,
                "pdf_asset.updated_at": now,
                "pdf_asset.worker_id": "",
                "pdf_asset.lease_until": None,

                # 兼容旧字段，后续新版流程稳定后再考虑淘汰。
                "processing_status.pdf_downloaded": True,
                "local_pdf_path": relative_path.strip(),
            }
        },
    )

    return result.modified_count == 1


def mark_pdf_task_failed(
    *,
    paper_id: str,
    worker_id: str,
    error: str,
    retry_delay_seconds: int,
    http_status: int | None = None,
    final_url: str = "",
) -> bool:
    """
    将当前 Worker 拥有的 PDF 任务标记为 failed。

    next_retry_at 用于控制下一次允许重试的时间。
    attempts 已经在领取任务时累加，这里不再重复增加。
    """

    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds 不能小于 0")

    normalized_error = error.strip()

    if not normalized_error:
        raise ValueError("error 不能为空")

    now = utc_now()
    next_retry_at = now + timedelta(
        seconds=retry_delay_seconds
    )

    papers = MongoDBClient.get_collection()

    result = papers.update_one(
        build_owned_running_task_filter(
            paper_id=paper_id,
            worker_id=worker_id,
        ),
        {
            "$set": {
                "pdf_asset.status": "failed",
                "pdf_asset.final_url": final_url.strip(),
                "pdf_asset.http_status": http_status,
                "pdf_asset.last_error": normalized_error,
                "pdf_asset.last_checked_at": now,
                "pdf_asset.next_retry_at": next_retry_at,
                "pdf_asset.updated_at": now,
                "pdf_asset.worker_id": "",
                "pdf_asset.lease_until": None,
            }
        },
    )

    return result.modified_count == 1


def mark_pdf_task_unavailable(
    *,
    paper_id: str,
    worker_id: str,
    reason: str = "no_pdf_candidate",
) -> bool:
    """
    将任务标记为 unavailable。

    unavailable 表示当前没有可用 PDF 地址，并不代表永久不存在。
    后续可以通过单独的刷新程序重新检查来源字段，并把状态恢复为
    pending。
    """

    normalized_reason = reason.strip()

    if not normalized_reason:
        raise ValueError("reason 不能为空")

    now = utc_now()
    papers = MongoDBClient.get_collection()

    result = papers.update_one(
        build_owned_running_task_filter(
            paper_id=paper_id,
            worker_id=worker_id,
        ),
        {
            "$set": {
                "pdf_asset.status": "unavailable",
                "pdf_asset.last_error": normalized_reason,
                "pdf_asset.last_checked_at": now,
                "pdf_asset.next_retry_at": None,
                "pdf_asset.updated_at": now,
                "pdf_asset.worker_id": "",
                "pdf_asset.lease_until": None,
            },
            # 领取任务时 attempts 已经加 1。
            # 当前没有任何 PDF URL，并未真正发起下载，
            # 因此不应消耗一次下载尝试次数。
            "$inc": {
                "pdf_asset.attempts": -1,
            },
        },
    )

    return result.modified_count == 1

def renew_pdf_task_lease(
    *,
    paper_id: str,
    worker_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> bool:
    """
    为当前 Worker 拥有的 PDF 下载任务续租。

    典型使用场景：

        PDF 已下载到 Worker 独立临时文件
            ↓
        正式落盘前调用 renew_pdf_task_lease()
            ↓
        续租成功，说明当前 Worker 仍然拥有任务
            ↓
        原子移动临时文件到正式路径
            ↓
        mark_pdf_task_success()

    查询条件会同时检查：

    1. paper_id；
    2. pdf_asset.status == running；
    3. pdf_asset.worker_id 与当前 Worker 一致。

    因此，已经被其他 Worker 接管的旧 Worker 无法续租。

    返回：
        续租成功返回 True；
        已失去任务所有权返回 False。
    """

    if lease_seconds <= 0:
        raise ValueError("lease_seconds 必须大于 0")

    now = utc_now()
    lease_until = now + timedelta(seconds=lease_seconds)

    papers = MongoDBClient.get_collection()

    result = papers.update_one(
        build_owned_running_task_filter(
            paper_id=paper_id,
            worker_id=worker_id,
        ),
        {
            "$set": {
                "pdf_asset.lease_until": lease_until,
                "pdf_asset.updated_at": now,
            }
        },
    )

    return result.modified_count == 1


def refresh_unavailable_pdf_tasks(
    *,
    selection_filter: dict[str, Any] | None = None,
) -> int:
    """
    将已经出现 PDF URL 的 unavailable 任务恢复为 pending。

    典型场景：

        论文首次进入数据库时没有 PDF URL
            ↓
        pdf_asset.status = unavailable
            ↓
        后续爬虫或数据融合补充了 PDF URL
            ↓
        调用本函数
            ↓
        unavailable -> pending
            ↓
        PDF 下载器可以重新领取

    selection_filter 可用于只刷新指定会议或论文，例如：

        {"accepted_by": "ICML 2026"}

        {"_id": "paper_id"}

    返回：
        成功恢复为 pending 的论文数量。
    """

    pdf_url_fields = [
        "acl_anthology_obj.pdf_url",
        "aaai_obj.official_pdf_url",
        "icml_official_obj.official_pdf_url",
        "openreview_obj.pdf_url",
        "arxiv_obj.arxiv_pdf_url",
        "base_urls.pmlr_pdf_url",
        "base_urls.acl_anthology_pdf_url",
        "base_urls.official_pdf_url",
        "base_urls.openreview_pdf_url",
        "base_urls.arxiv_pdf_url",
    ]

    pdf_available_filter = {
        "$or": [
            {
                field: {
                    "$exists": True,
                    "$nin": ["", None],
                }
            }
            for field in pdf_url_fields
        ]
    }

    conditions: list[dict[str, Any]] = [
        {
            "pdf_asset.status": "unavailable",
        },
        pdf_available_filter,
    ]

    if selection_filter:
        conditions.insert(0, selection_filter)

    now = utc_now()
    papers = MongoDBClient.get_collection()

    result = papers.update_many(
        {
            "$and": conditions,
        },
        {
            "$set": {
                "pdf_asset.status": "pending",
                "pdf_asset.last_error": "",
                "pdf_asset.next_retry_at": None,
                "pdf_asset.updated_at": now,
                "pdf_asset.worker_id": "",
                "pdf_asset.lease_until": None,
            }
        },
    )

    return result.modified_count


def mark_pdf_task_rate_limited(
    *,
    paper_id: str,
    worker_id: str,
    error: str,
    retry_delay_seconds: int,
    http_status: int = 429,
    final_url: str = "",
) -> bool:
    """
    将当前 Worker 拥有的任务标记为“因来源网站限流而延后重试”。

    MongoDB 中仍使用 failed 状态，使现有任务领取逻辑可以根据
    next_retry_at 在冷却结束后重新领取。

    与普通下载失败的区别：

    1. 429 是来源网站的临时限流，不是论文自身的问题；
    2. 领取任务时 attempts 已经加 1；
    3. 本函数会将 attempts 减回去，不消耗论文的重试次数；
    4. next_retry_at 使用更长的来源冷却时间。

    返回：
        成功更新返回 True；
        如果任务已经不再属于当前 Worker，返回 False。
    """

    if retry_delay_seconds <= 0:
        raise ValueError(
            "retry_delay_seconds 必须大于 0"
        )

    normalized_error = error.strip()

    if not normalized_error:
        raise ValueError("error 不能为空")

    if http_status != 429:
        raise ValueError(
            "mark_pdf_task_rate_limited 只用于 HTTP 429"
        )

    now = utc_now()
    next_retry_at = now + timedelta(
        seconds=retry_delay_seconds
    )

    papers = MongoDBClient.get_collection()

    result = papers.update_one(
        build_owned_running_task_filter(
            paper_id=paper_id,
            worker_id=worker_id,
        ),
        {
            "$set": {
                "pdf_asset.status": "failed",
                "pdf_asset.final_url": final_url.strip(),
                "pdf_asset.http_status": http_status,
                "pdf_asset.last_error": normalized_error,
                "pdf_asset.last_checked_at": now,
                "pdf_asset.next_retry_at": next_retry_at,
                "pdf_asset.updated_at": now,
                "pdf_asset.worker_id": "",
                "pdf_asset.lease_until": None,
            },

            # claim_next_pdf_task() 在领取任务时已经将 attempts 加 1。
            # HTTP 429 属于来源网站临时限流，不应消耗论文自身的
            # 下载尝试次数，因此在这里减回去。
            "$inc": {
                "pdf_asset.attempts": -1,
            },
        },
    )

    return result.modified_count == 1


def recover_rate_limited_pdf_tasks(
    *,
    selection_filter: dict[str, Any] | None = None,
    limit: int | None = None,
) -> int:
    """
    恢复因历史 HTTP 429 限流而耗尽 attempts 的 PDF 任务。

    适用场景：

        旧版本下载器将 OpenReview 429 当成普通下载失败，
        导致同一论文多次重试，并最终达到 max_attempts。

    恢复后：

        pdf_asset.status         保持 failed
        pdf_asset.attempts       重置为 0
        pdf_asset.next_retry_at  设置为当前时间
        pdf_asset.worker_id      清空
        pdf_asset.lease_until    清空

    保留：

        pdf_asset.http_status
        pdf_asset.last_error

    这样可以保留历史错误信息，同时允许新版下载器重新领取。

    selection_filter:
        可选的附加业务筛选条件，例如：

            {"accepted_by": "ICLR 2025"}

            {"_id": "paper_id"}

    limit:
        最多恢复多少条记录。
        None 表示恢复全部符合条件的记录。

    返回：
        实际恢复的记录数量。
    """

    if selection_filter is not None:
        if not isinstance(selection_filter, dict):
            raise TypeError(
                "selection_filter 必须是字典或 None"
            )

    if limit is not None and limit <= 0:
        raise ValueError("limit 必须大于 0")

    conditions: list[dict[str, Any]] = [
        {
            "pdf_asset.status": "failed",
        },
        {
            "pdf_asset.http_status": 429,
        },
    ]

    if selection_filter:
        conditions.insert(0, selection_filter)

    query = {
        "$and": conditions,
    }

    now = utc_now()
    papers = MongoDBClient.get_collection()

    # update_many 不支持 limit，因此有限量恢复时，
    # 先稳定地查询需要恢复的论文 _id。
    if limit is not None:
        paper_ids = [
            document["_id"]
            for document in papers.find(
                query,
                {
                    "_id": 1,
                },
            ).sort("_id", 1).limit(limit)
        ]

        if not paper_ids:
            return 0

        query = {
            "_id": {
                "$in": paper_ids,
            }
        }

    result = papers.update_many(
        query,
        {
            "$set": {
                "pdf_asset.status": "failed",
                "pdf_asset.attempts": 0,
                "pdf_asset.next_retry_at": now,
                "pdf_asset.updated_at": now,
                "pdf_asset.worker_id": "",
                "pdf_asset.lease_until": None,
            }
        },
    )

    return result.modified_count