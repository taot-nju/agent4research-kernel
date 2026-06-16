"""
单个 PDF URL 下载器。

本模块只负责：

1. 以流式方式下载一个 PDF URL；
2. 先写入 .part 临时文件；
3. 下载后执行 PDF 基础校验；
4. 校验成功后原子重命名为最终文件；
5. 返回统一的下载结果；
6. 失败时清理不完整的临时文件。

本模块暂时不负责：

- MongoDB 状态更新；
- 任务筛选；
- 自动重试；
- 并发控制；
- 多候选 URL 回退。

这些功能后续由 Pipeline 和任务调度层负责。
"""

from dataclasses import asdict, dataclass
from pathlib import Path

import requests

from ai4research.fulltext_pipeline.utils.pdf_validator import (
    validate_pdf_file,
)
from ai4research.fulltext_pipeline.utils.storage_paths import (
    ensure_parent_directory,
)


DEFAULT_CONNECT_TIMEOUT_SECONDS = 10
DEFAULT_READ_TIMEOUT_SECONDS = 60
DEFAULT_DOWNLOAD_CHUNK_SIZE = 1024 * 1024

DEFAULT_USER_AGENT = (
    "ai4research-pdf-downloader/1.0 "
    "(academic research; respectful rate limiting)"
)


@dataclass(frozen=True)
class PDFDownloadResult:
    """
    单次 PDF 下载结果。
    """

    success: bool

    source_url: str
    final_url: str

    target_path: str
    temp_path: str

    http_status: int | None
    content_type: str

    size_bytes: int
    sha256: str

    error: str

    def to_dict(self) -> dict:
        """转换为普通字典，便于日志记录和数据库回写。"""

        return asdict(self)


def _remove_file_if_exists(file_path: Path) -> None:
    """
    删除可能存在的临时文件。

    清理失败不会覆盖真正的下载异常。
    """

    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        pass


def download_pdf_url(
    url: str,
    target_path: str | Path,
    *,
    temp_path: str | Path | None = None,
    finalize: bool = True,
    session: requests.Session | None = None,
    connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    read_timeout_seconds: int = DEFAULT_READ_TIMEOUT_SECONDS,
    chunk_size: int = DEFAULT_DOWNLOAD_CHUNK_SIZE,
    user_agent: str = DEFAULT_USER_AGENT,
) -> PDFDownloadResult:
    """
    下载单个 PDF URL，并在校验成功后写入最终文件。

    下载流程：

        URL
         ↓
        target.pdf.part
         ↓
        PDF 基础校验
         ↓
        target.pdf

    `.part` 文件与最终文件位于同一目录，因此最后的 replace
    可以在同一文件系统内完成原子替换。

    参数：
        url:
            PDF 来源地址。

        target_path:
            最终 PDF 的绝对路径。

        temp_path:
            可选的临时文件路径。并发 Worker 应使用各自独立的
            临时路径，避免共同操作同一个 .part 文件。

        finalize:
            True 时，校验成功后立即原子替换为 target_path；
            False 时，保留已校验的临时文件，由上层 Pipeline
            确认任务所有权后再完成最终落盘。

        session:
            可选 requests.Session。后续批量下载时可以复用连接。

        connect_timeout_seconds:
            建立网络连接的超时时间。

        read_timeout_seconds:
            等待服务器返回数据的超时时间。

        chunk_size:
            流式下载时每次写入的字节数。

        user_agent:
            请求头中的 User-Agent。
    """

    normalized_url = url.strip()

    if not normalized_url:
        raise ValueError("PDF URL 不能为空")

    if connect_timeout_seconds <= 0:
        raise ValueError("connect_timeout_seconds 必须大于 0")

    if read_timeout_seconds <= 0:
        raise ValueError("read_timeout_seconds 必须大于 0")

    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")

    final_path = Path(target_path)

    if temp_path is None:
        part_path = final_path.with_suffix(
            final_path.suffix + ".part"
        )
    else:
        part_path = Path(temp_path)

    if part_path == final_path:
        raise ValueError("temp_path 不能与 target_path 相同")

    ensure_parent_directory(final_path)
    ensure_parent_directory(part_path)

    # 防止上一次断网或进程异常留下残缺文件。
    _remove_file_if_exists(part_path)

    request_session = session or requests.Session()
    owns_session = session is None

    http_status: int | None = None
    final_url = ""
    content_type = ""

    try:
        response = request_session.get(
            normalized_url,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/pdf,*/*;q=0.8",
            },
            timeout=(
                connect_timeout_seconds,
                read_timeout_seconds,
            ),
            stream=True,
            allow_redirects=True,
        )

        http_status = response.status_code
        final_url = response.url
        content_type = response.headers.get(
            "Content-Type",
            "",
        )

        response.raise_for_status()

        with part_path.open("wb") as file:
            for chunk in response.iter_content(
                chunk_size=chunk_size
            ):
                if not chunk:
                    continue

                file.write(chunk)

            # 尽量确保 Python 缓冲区内容已经写入操作系统。
            file.flush()

        validation_result = validate_pdf_file(part_path)

        if not validation_result.valid:
            _remove_file_if_exists(part_path)

            return PDFDownloadResult(
                success=False,
                source_url=normalized_url,
                final_url=final_url,
                target_path=str(final_path),
                temp_path=str(part_path),
                http_status=http_status,
                content_type=content_type,
                size_bytes=validation_result.size_bytes,
                sha256="",
                error=(
                    "pdf_validation_failed: "
                    f"{validation_result.error}"
                ),
            )

        # 单文件独立使用时，下载器可以直接原子落盘。
        #
        # 并发任务模式下应传入 finalize=False：
        # 下载器只负责生成并校验 Worker 独立的临时文件；
        # Pipeline 确认任务所有权后再执行原子落盘。
        if finalize:
            part_path.replace(final_path)


        return PDFDownloadResult(
            success=True,
            source_url=normalized_url,
            final_url=final_url,
            target_path=str(final_path),
            temp_path=str(part_path),
            http_status=http_status,
            content_type=content_type,
            size_bytes=validation_result.size_bytes,
            sha256=validation_result.sha256,
            error="",
        )

    except requests.RequestException as error:
        _remove_file_if_exists(part_path)

        return PDFDownloadResult(
            success=False,
            source_url=normalized_url,
            final_url=final_url,
            target_path=str(final_path),
            temp_path=str(part_path),
            http_status=http_status,
            content_type=content_type,
            size_bytes=0,
            sha256="",
            error=f"request_error: {error}",
        )

    except OSError as error:
        _remove_file_if_exists(part_path)

        return PDFDownloadResult(
            success=False,
            source_url=normalized_url,
            final_url=final_url,
            target_path=str(final_path),
            temp_path=str(part_path),
            http_status=http_status,
            content_type=content_type,
            size_bytes=0,
            sha256="",
            error=f"os_error: {error}",
        )

    finally:
        if owns_session:
            request_session.close()
