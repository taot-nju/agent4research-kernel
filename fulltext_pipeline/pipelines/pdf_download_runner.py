"""
PDF 下载任务顺序运行器。

负责不断执行：

    原子领取一条任务
        ↓
    执行单篇 PDF 下载 Pipeline
        ↓
    继续领取下一条任务

本模块不负责命令行参数解析。
正式用户入口将在 scripts_py/download_pdfs.py 中实现。

第一版采用顺序执行，先保证任务筛选、断点续跑和状态回写正确。
后续并发版本可以复用同一个单篇任务处理流程。
"""

from dataclasses import asdict, dataclass
from typing import Any

import requests

from ai4research.fulltext_pipeline.downloaders.domain_rate_limiter import (
    DomainRateLimiter,
)

from ai4research.fulltext_pipeline.pipelines.pdf_download_pipeline import (
    process_claimed_pdf_task,
)
from ai4research.fulltext_pipeline.repositories.pdf_task_repository import (
    DEFAULT_LEASE_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    claim_next_pdf_task,
)


@dataclass
class PDFRunSummary:
    """一次 PDF 下载运行的统计结果。"""

    claimed: int = 0
    success: int = 0
    failed: int = 0
    unavailable: int = 0
    ownership_lost: int = 0
    other: int = 0

    def record_status(self, status: str) -> None:
        """根据单篇任务状态更新统计结果。"""

        if status == "success":
            self.success += 1
        elif status == "failed":
            self.failed += 1
        elif status == "unavailable":
            self.unavailable += 1
        elif status == "ownership_lost":
            self.ownership_lost += 1
        else:
            self.other += 1

    def to_dict(self) -> dict:
        """转换为普通字典。"""

        return asdict(self)


def run_pdf_download_tasks(
    *,
    worker_id: str,
    selection_filter: dict[str, Any],
    limit: int,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_delay_seconds: int = 60,
    rate_limiter: DomainRateLimiter | None = None,
) -> PDFRunSummary:
    """
    顺序处理一批 PDF 下载任务。

    参数：
        worker_id:
            当前 Worker 的唯一标识。

        selection_filter:
            MongoDB 业务筛选条件，例如：

                {"accepted_by": "ICLR 2022"}

                {"_id": "xxx"}

        limit:
            本次最多领取并处理多少篇论文。

        lease_seconds:
            每条任务领取后的租约时长。

        max_attempts:
            每篇论文允许被领取的最大次数。

        retry_delay_seconds:
            下载失败后，至少等待多久才能再次领取。

        rate_limiter:
            可选的按域名限速器。如果没有传入，则本次运行自动创建
            一个 DomainRateLimiter。顺序任务共享同一个实例，
            后续并发 Worker 也将共享该实例。

    返回：
        本次运行的统计摘要。
    """

    normalized_worker_id = worker_id.strip()

    if not normalized_worker_id:
        raise ValueError("worker_id 不能为空")

    if not isinstance(selection_filter, dict):
        raise TypeError("selection_filter 必须是字典")

    if limit <= 0:
        raise ValueError("limit 必须大于 0")

    if lease_seconds <= 0:
        raise ValueError("lease_seconds 必须大于 0")

    if max_attempts <= 0:
        raise ValueError("max_attempts 必须大于 0")

    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds 不能小于 0")

    summary = PDFRunSummary()

    shared_rate_limiter = rate_limiter or DomainRateLimiter()

    # 顺序执行时复用一个 Session，减少重复建立连接的开销。
    with requests.Session() as session:
        while summary.claimed < limit:
            paper = claim_next_pdf_task(
                worker_id=normalized_worker_id,
                selection_filter=selection_filter,
                lease_seconds=lease_seconds,
                max_attempts=max_attempts,
            )

            if paper is None:
                break

            summary.claimed += 1

            paper_id = str(paper.get("_id", ""))
            title = str(paper.get("title", ""))

            print("-" * 100)
            print(
                f"[{summary.claimed}/{limit}] "
                f"paper_id={paper_id}"
            )
            print(f"title={title}")

            result = process_claimed_pdf_task(
                paper=paper,
                worker_id=normalized_worker_id,
                session=session,
                rate_limiter=shared_rate_limiter,
                retry_delay_seconds=retry_delay_seconds,
                commit_lease_seconds=lease_seconds,
            )

            summary.record_status(result.status)

            print(
                f"status={result.status} | "
                f"source={result.source or '-'} | "
                f"attempted_candidates="
                f"{result.attempted_candidates}"
            )

            if result.error:
                print(f"error={result.error}")
                # 来源网站返回 HTTP 429 时，不再继续领取新任务。
                #
                # 当前任务已经通过 Pipeline 写入较晚的 next_retry_at，
                # 并且没有消耗 attempts。继续领取同一来源的论文只会
                # 产生无意义的数据库状态更新。
                if result.http_status == 429:
                    print("=" * 100)
                    print(
                        "⚠️ 检测到 HTTP 429，"
                        "本次顺序下载将停止领取新的 PDF 任务。"
                    )
                    print(
                        "请等待来源网站冷却期结束后，"
                        "再重新执行下载命令。"
                    )
                    break

    return summary