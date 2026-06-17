"""
PDF 下载任务并发运行器。

设计原则：

1. 主线程通过 MongoDB 原子领取任务；
2. 使用 ThreadPoolExecutor 并发处理多篇论文；
3. 每个线程独立创建 requests.Session，避免跨线程共享 Session；
4. 所有线程共享同一个 DomainRateLimiter；
5. 不同域名可以并行；
6. 同一域名仍遵守独立的并发数和请求间隔限制；
7. 已成功、unavailable、达到最大尝试次数的任务不会被领取。
"""

import threading
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
    as_completed,
)
from dataclasses import asdict, dataclass
from typing import Any

import requests

from ai4research.fulltext_pipeline.downloaders.domain_rate_limiter import (
    DomainRateLimiter,
)
from ai4research.fulltext_pipeline.pipelines.pdf_download_pipeline import (
    PDFPipelineResult,
    process_claimed_pdf_task,
)
from ai4research.fulltext_pipeline.repositories.pdf_task_repository import (
    DEFAULT_LEASE_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    claim_next_pdf_task,
)


@dataclass
class ConcurrentPDFRunSummary:
    """一次并发 PDF 下载任务的统计结果。"""

    claimed: int = 0
    completed: int = 0
    success: int = 0
    failed: int = 0
    unavailable: int = 0
    ownership_lost: int = 0
    worker_exception: int = 0
    other: int = 0

    def record_result(
        self,
        result: PDFPipelineResult,
    ) -> None:
        """记录一篇论文的 Pipeline 结果。"""

        self.completed += 1

        if result.status == "success":
            self.success += 1
        elif result.status == "failed":
            self.failed += 1
        elif result.status == "unavailable":
            self.unavailable += 1
        elif result.status == "ownership_lost":
            self.ownership_lost += 1
        else:
            self.other += 1

    def to_dict(self) -> dict:
        """转换为普通字典。"""

        return asdict(self)


_thread_local = threading.local()


def _get_thread_session() -> requests.Session:
    """
    为当前线程获取独立的 requests.Session。

    同一个线程连续处理任务时可以复用连接；
    不同线程不会共享同一个 Session。
    """

    session = getattr(
        _thread_local,
        "requests_session",
        None,
    )

    if session is None:
        session = requests.Session()
        _thread_local.requests_session = session

    return session


def _process_one_claimed_task(
    *,
    paper: dict[str, Any],
    worker_id: str,
    rate_limiter: DomainRateLimiter,
    retry_delay_seconds: int,
    lease_seconds: int,
) -> PDFPipelineResult:
    """在线程中处理一条已经领取的 PDF 任务。"""

    session = _get_thread_session()

    return process_claimed_pdf_task(
        paper=paper,
        worker_id=worker_id,
        session=session,
        rate_limiter=rate_limiter,
        retry_delay_seconds=retry_delay_seconds,
        commit_lease_seconds=lease_seconds,
    )


def run_concurrent_pdf_download_tasks(
    *,
    worker_id_prefix: str,
    selection_filter: dict[str, Any],
    limit: int,
    max_workers: int,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_delay_seconds: int = 60,
    rate_limiter: DomainRateLimiter | None = None,
) -> ConcurrentPDFRunSummary:
    """
    并发处理一批 PDF 下载任务。

    参数：
        worker_id_prefix:
            当前进程的 Worker 前缀。每个线程会生成独立 Worker ID，
            例如：

                server-pid-123-thread-0

        selection_filter:
            MongoDB 业务筛选条件。

        limit:
            本次最多领取的论文总数。

        max_workers:
            线程池最大线程数。它只控制全局并发；
            每个来源网站仍受到 DomainRateLimiter 的独立限制。

        lease_seconds:
            每条任务的租约时长。

        max_attempts:
            单篇论文允许被领取的最大次数。

        retry_delay_seconds:
            下载失败后的重试等待时间。

        rate_limiter:
            可选的共享域名限速器。
    """

    normalized_prefix = worker_id_prefix.strip()

    if not normalized_prefix:
        raise ValueError("worker_id_prefix 不能为空")

    if not isinstance(selection_filter, dict):
        raise TypeError("selection_filter 必须是字典")

    if limit <= 0:
        raise ValueError("limit 必须大于 0")

    if max_workers <= 0:
        raise ValueError("max_workers 必须大于 0")

    if lease_seconds <= 0:
        raise ValueError("lease_seconds 必须大于 0")

    if max_attempts <= 0:
        raise ValueError("max_attempts 必须大于 0")

    if retry_delay_seconds < 0:
        raise ValueError(
            "retry_delay_seconds 不能小于 0"
        )

    shared_rate_limiter = (
        rate_limiter or DomainRateLimiter()
    )

    summary = ConcurrentPDFRunSummary()

    # 本次运行一旦检测到来源网站返回 429，
    # 停止继续领取新任务。
    #
    # 已经提交到线程池的任务仍会正常完成，
    # 避免强行中断后留下 running 状态。
    rate_limit_detected = False

    future_metadata: dict[
        Future[PDFPipelineResult],
        tuple[str, str],
    ] = {}

    with ThreadPoolExecutor(
        max_workers=max_workers,
        thread_name_prefix="pdf-download",
    ) as executor:

        # 只维持最多 max_workers 个正在执行的任务，
        # 避免提前领取大量任务后排队，导致租约尚未执行便过期。
        while (
            summary.claimed < limit
            or future_metadata
        ):
            while (
                summary.claimed < limit
                and len(future_metadata) < max_workers
                and not rate_limit_detected
            ):
                task_number = summary.claimed + 1

                task_worker_id = (
                    f"{normalized_prefix}-slot-{task_number}"
                )

                paper = claim_next_pdf_task(
                    worker_id=task_worker_id,
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
                    f"[claimed {summary.claimed}/{limit}] "
                    f"paper_id={paper_id}"
                )
                print(f"title={title}")

                future = executor.submit(
                    _process_one_claimed_task,
                    paper=paper,
                    worker_id=task_worker_id,
                    rate_limiter=shared_rate_limiter,
                    retry_delay_seconds=(
                        retry_delay_seconds
                    ),
                    lease_seconds=lease_seconds,
                )

                future_metadata[future] = (
                    paper_id,
                    title,
                )

            if not future_metadata:
                break

            # 等待当前至少一个任务完成，再补充新的任务。
            completed_future = next(
                as_completed(future_metadata)
            )

            paper_id, title = future_metadata.pop(
                completed_future
            )

            try:
                result = completed_future.result()

            except Exception as error:
                summary.completed += 1
                summary.worker_exception += 1

                print(
                    f"worker_exception | "
                    f"paper_id={paper_id} | "
                    f"title={title}"
                )
                print(f"error={error}")

                # 未在这里修改数据库状态。
                # 该任务仍保持 running，租约过期后可以重新领取。
                continue

            summary.record_result(result)

            if result.http_status == 429:
                rate_limit_detected = True

                print(
                    "⚠️ 检测到 HTTP 429，"
                    "本次运行将停止领取新的 PDF 任务。"
                )
                print(
                    "已经提交到线程池的任务仍会正常结束。"
                )

            print(
                f"completed={summary.completed} | "
                f"paper_id={paper_id} | "
                f"status={result.status} | "
                f"source={result.source or '-'} | "
                f"attempted_candidates="
                f"{result.attempted_candidates}"
            )

            if result.error:
                print(f"error={result.error}")

    if rate_limit_detected:
        print("=" * 100)
        print(
            "⚠️ 本次 PDF 下载因来源网站限流而提前停止领取任务。"
        )
        print(
            "请等待冷却期结束后，再重新执行下载命令。"
        )

    return summary