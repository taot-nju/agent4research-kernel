"""
单篇论文 PDF 下载流程。

本模块负责把以下组件串联起来：

1. PDF 候选 URL 解析；
2. Worker 独立临时文件下载；
3. PDF 基础校验；
4. 任务续租与所有权确认；
5. 临时文件原子移动到正式资产目录；
6. MongoDB 状态回写；
7. 多候选 URL 自动回退。

本模块处理的是已经通过 claim_next_pdf_task() 领取的论文记录。
批量循环、命令行参数和并发调度由后续模块负责。
"""

from dataclasses import asdict, dataclass
from hashlib import sha1
from pathlib import Path

import requests

from ai4research.fulltext_pipeline.config import get_temp_root
from ai4research.fulltext_pipeline.downloaders.pdf_downloader import (
    download_pdf_url,
)
from ai4research.fulltext_pipeline.downloaders.domain_rate_limiter import (
    DomainRateLimiter,
)
from ai4research.fulltext_pipeline.repositories.pdf_task_repository import (
    mark_pdf_task_failed,
    mark_pdf_task_success,
    mark_pdf_task_unavailable,
    renew_pdf_task_lease,
)
from ai4research.fulltext_pipeline.utils.pdf_url_resolver import (
    resolve_pdf_candidates,
)
from ai4research.fulltext_pipeline.utils.storage_paths import (
    ensure_parent_directory,
    get_pdf_relative_path,
    resolve_asset_path,
)


DEFAULT_RETRY_DELAY_SECONDS = 60
DEFAULT_COMMIT_LEASE_SECONDS = 10 * 60


@dataclass(frozen=True)
class PDFPipelineResult:
    """单篇论文 PDF 下载流程的执行结果。"""

    success: bool
    paper_id: str
    status: str

    source: str
    source_url: str
    final_url: str

    relative_path: str
    size_bytes: int
    sha256: str
    http_status: int | None

    attempted_candidates: int
    error: str

    def to_dict(self) -> dict:
        """转换为普通字典。"""

        return asdict(self)


def _safe_remove(file_path: Path) -> None:
    """尽力清理临时文件，清理失败不覆盖主要异常。"""

    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        pass


def _worker_directory_name(worker_id: str) -> str:
    """
    将 worker_id 转换为稳定且适合放入路径的短标识。

    不直接把 worker_id 写入路径，避免其中包含斜杠、冒号等字符。
    """

    return sha1(
        worker_id.encode("utf-8")
    ).hexdigest()[:16]


def build_worker_temp_pdf_path(
    *,
    paper_id: str,
    worker_id: str,
) -> Path:
    """
    为一个 Worker 的单篇论文任务生成独立临时路径。

    示例：

        temp/pdf_downloads/<worker_hash>/<paper_id>.pdf.part
    """

    worker_directory = _worker_directory_name(worker_id)

    return (
        get_temp_root()
        / "pdf_downloads"
        / worker_directory
        / f"{paper_id}.pdf.part"
    )


def process_claimed_pdf_task(
    *,
    paper: dict,
    worker_id: str,
    session: requests.Session | None = None,
    rate_limiter: DomainRateLimiter | None = None,
    retry_delay_seconds: int = DEFAULT_RETRY_DELAY_SECONDS,
    commit_lease_seconds: int = DEFAULT_COMMIT_LEASE_SECONDS,
) -> PDFPipelineResult:
    """
    处理一条已经领取并处于 running 状态的 PDF 任务。

    多个候选 URL 会按照优先级依次尝试：

        会议正式版
        → OpenReview
        → arXiv

    只有全部候选地址都失败时，任务才会标记为 failed。

    rate_limiter:
        可选的按域名限速器。顺序和并发运行器应共享同一个
        DomainRateLimiter 实例，使所有 Worker 共同遵守来源网站
        的并发限制和最小请求间隔。
    """

    paper_id = str(paper.get("_id", "")).strip()
    normalized_worker_id = worker_id.strip()

    if not paper_id:
        raise ValueError("paper 中缺少有效的 _id")

    if not normalized_worker_id:
        raise ValueError("worker_id 不能为空")

    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds 不能小于 0")

    if commit_lease_seconds <= 0:
        raise ValueError("commit_lease_seconds 必须大于 0")

    candidates = resolve_pdf_candidates(paper)

    # 当前没有任何 PDF 地址。
    if not candidates:
        updated = mark_pdf_task_unavailable(
            paper_id=paper_id,
            worker_id=normalized_worker_id,
            reason="no_pdf_candidate",
        )

        status = "unavailable" if updated else "ownership_lost"

        return PDFPipelineResult(
            success=False,
            paper_id=paper_id,
            status=status,
            source="",
            source_url="",
            final_url="",
            relative_path="",
            size_bytes=0,
            sha256="",
            http_status=None,
            attempted_candidates=0,
            error=(
                "no_pdf_candidate"
                if updated
                else "task_ownership_lost"
            ),
        )

    relative_path = get_pdf_relative_path(paper_id)
    final_path = resolve_asset_path(relative_path)

    temp_path = build_worker_temp_pdf_path(
        paper_id=paper_id,
        worker_id=normalized_worker_id,
    )

    errors: list[str] = []
    last_http_status: int | None = None
    last_final_url = ""

    for candidate_index, candidate in enumerate(
        candidates,
        start=1,
    ):
        source = candidate["source"]
        source_url = candidate["url"]

        # download_result = download_pdf_url(
        #     url=source_url,
        #     target_path=final_path,
        #     temp_path=temp_path,
        #     finalize=False,
        #     session=session,
        # )
        if rate_limiter is None:
            download_result = download_pdf_url(
                url=source_url,
                target_path=final_path,
                temp_path=temp_path,
                finalize=False,
                session=session,
            )
        else:
            # 获取当前 URL 所属域名的访问许可。
            # 同域名受到并发数和请求启动间隔限制；
            # 不同域名可以独立执行。
            with rate_limiter.limit(source_url):
                download_result = download_pdf_url(
                    url=source_url,
                    target_path=final_path,
                    temp_path=temp_path,
                    finalize=False,
                    session=session,
                )

        last_http_status = download_result.http_status
        last_final_url = download_result.final_url

        if not download_result.success:
            errors.append(
                f"{source}: {download_result.error}"
            )
            continue

        # 下载完成后先续租。
        # 续租成功表示当前 Worker 仍然拥有该任务。
        renewed = renew_pdf_task_lease(
            paper_id=paper_id,
            worker_id=normalized_worker_id,
            lease_seconds=commit_lease_seconds,
        )

        if not renewed:
            _safe_remove(temp_path)

            return PDFPipelineResult(
                success=False,
                paper_id=paper_id,
                status="ownership_lost",
                source=source,
                source_url=source_url,
                final_url=download_result.final_url,
                relative_path=str(relative_path),
                size_bytes=download_result.size_bytes,
                sha256=download_result.sha256,
                http_status=download_result.http_status,
                attempted_candidates=candidate_index,
                error="task_ownership_lost_before_commit",
            )

        try:
            ensure_parent_directory(final_path)

            # Worker 临时文件与正式文件都位于同一资产根目录，
            # replace() 可以完成原子替换。
            temp_path.replace(final_path)

        except OSError as error:
            _safe_remove(temp_path)

            error_message = f"atomic_commit_failed: {error}"

            updated = mark_pdf_task_failed(
                paper_id=paper_id,
                worker_id=normalized_worker_id,
                error=error_message,
                retry_delay_seconds=retry_delay_seconds,
                http_status=download_result.http_status,
                final_url=download_result.final_url,
            )

            return PDFPipelineResult(
                success=False,
                paper_id=paper_id,
                status=(
                    "failed"
                    if updated
                    else "ownership_lost"
                ),
                source=source,
                source_url=source_url,
                final_url=download_result.final_url,
                relative_path=str(relative_path),
                size_bytes=0,
                sha256="",
                http_status=download_result.http_status,
                attempted_candidates=candidate_index,
                error=error_message,
            )

        success_updated = mark_pdf_task_success(
            paper_id=paper_id,
            worker_id=normalized_worker_id,
            source=source,
            source_url=source_url,
            final_url=download_result.final_url,
            relative_path=str(relative_path),
            size_bytes=download_result.size_bytes,
            file_sha256=download_result.sha256,
            http_status=download_result.http_status,
        )

        if not success_updated:
            return PDFPipelineResult(
                success=False,
                paper_id=paper_id,
                status="ownership_lost",
                source=source,
                source_url=source_url,
                final_url=download_result.final_url,
                relative_path=str(relative_path),
                size_bytes=download_result.size_bytes,
                sha256=download_result.sha256,
                http_status=download_result.http_status,
                attempted_candidates=candidate_index,
                error="task_ownership_lost_after_commit",
            )

        return PDFPipelineResult(
            success=True,
            paper_id=paper_id,
            status="success",
            source=source,
            source_url=source_url,
            final_url=download_result.final_url,
            relative_path=str(relative_path),
            size_bytes=download_result.size_bytes,
            sha256=download_result.sha256,
            http_status=download_result.http_status,
            attempted_candidates=candidate_index,
            error="",
        )

    # 所有候选 URL 均下载失败。
    combined_error = " | ".join(errors)

    # 防止异常信息无限增长后写入 MongoDB。
    combined_error = combined_error[:4000]

    updated = mark_pdf_task_failed(
        paper_id=paper_id,
        worker_id=normalized_worker_id,
        error=combined_error or "all_pdf_candidates_failed",
        retry_delay_seconds=retry_delay_seconds,
        http_status=last_http_status,
        final_url=last_final_url,
    )

    return PDFPipelineResult(
        success=False,
        paper_id=paper_id,
        status="failed" if updated else "ownership_lost",
        source="",
        source_url="",
        final_url=last_final_url,
        relative_path=str(relative_path),
        size_bytes=0,
        sha256="",
        http_status=last_http_status,
        attempted_candidates=len(candidates),
        error=combined_error or "all_pdf_candidates_failed",
    )