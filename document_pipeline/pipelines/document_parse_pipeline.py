"""
单篇文档解析 Pipeline。

本模块处理一条已经被 Worker 领取的 document task，负责：

1. 校验来源 PDF；
2. 调用可替换的 DocumentParser；
3. 在临时目录生成文档资产；
4. 确认任务所有权；
5. 将资产提交到正式目录；
6. 回写 MongoDB 状态。
"""

import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from ai4research.document_pipeline.parsers.base import (
    DocumentParser,
    ParseRequest,
)
from ai4research.document_pipeline.repositories.document_task_repository import (
    mark_document_task_failed,
    mark_document_task_success,
    renew_document_task_lease,
)
from ai4research.document_pipeline.utils.storage_paths import (
    build_document_asset_paths,
    ensure_document_asset_directories,
    to_data_root_relative_path,
)
from ai4research.fulltext_pipeline.config import (
    get_temp_root,
)
from ai4research.fulltext_pipeline.utils.pdf_validator import (
    validate_pdf_file,
)
from ai4research.fulltext_pipeline.utils.storage_paths import (
    resolve_asset_path,
)


DEFAULT_RETRY_DELAY_SECONDS = 60
DEFAULT_COMMIT_LEASE_SECONDS = 10 * 60


@dataclass(frozen=True)
class DocumentPipelineResult:
    """单篇文档解析 Pipeline 的执行结果。"""

    success: bool
    paper_id: str
    status: str

    parser_name: str
    parser_version: str

    document_relative_dir: str
    markdown_relative_path: str
    plain_text_relative_path: str
    layout_relative_path: str
    report_relative_path: str
    raw_output_relative_path: str

    page_count: int
    char_count: int
    duration_seconds: float

    error: str

    def to_dict(self) -> dict[str, Any]:
        """转换为普通字典。"""

        return asdict(self)


def _empty_result(
    *,
    paper_id: str,
    status: str,
    error: str,
    parser: DocumentParser,
) -> DocumentPipelineResult:
    """创建不包含已提交资产的失败结果。"""

    return DocumentPipelineResult(
        success=False,
        paper_id=paper_id,
        status=status,
        parser_name=parser.name,
        parser_version=parser.version,
        document_relative_dir="",
        markdown_relative_path="",
        plain_text_relative_path="",
        layout_relative_path="",
        report_relative_path="",
        raw_output_relative_path="",
        page_count=0,
        char_count=0,
        duration_seconds=0.0,
        error=error,
    )


def _mark_failed(
    *,
    paper_id: str,
    worker_id: str,
    parser: DocumentParser,
    error: str,
    retry_delay_seconds: int,
) -> DocumentPipelineResult:
    """回写失败；任务已被接管时返回 ownership_lost。"""

    normalized_error = (
        error.strip() or "document_parse_failed"
    )[:4000]

    updated = mark_document_task_failed(
        paper_id=paper_id,
        worker_id=worker_id,
        error=normalized_error,
        retry_delay_seconds=retry_delay_seconds,
    )

    return _empty_result(
        paper_id=paper_id,
        status=(
            "failed"
            if updated
            else "ownership_lost"
        ),
        error=(
            normalized_error
            if updated
            else "task_ownership_lost"
        ),
        parser=parser,
    )


def _commit_file(
    *,
    source_path: Path | None,
    destination_path: Path,
) -> Path | None:
    """将一个解析资产原子移动到正式路径。"""

    if source_path is None:
        return None

    if not source_path.exists():
        raise FileNotFoundError(
            f"解析资产不存在：{source_path}"
        )

    if not source_path.is_file():
        raise ValueError(
            f"解析资产不是普通文件：{source_path}"
        )

    destination_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_path.replace(destination_path)

    return destination_path


def _commit_raw_output(
    *,
    source_path: Path | None,
    raw_directory: Path,
) -> Path | None:
    """提交解析器的可选原始输出。"""

    if source_path is None:
        return None

    if not source_path.exists():
        raise FileNotFoundError(
            f"原始解析输出不存在：{source_path}"
        )

    if source_path.is_dir():
        if raw_directory.exists():
            shutil.rmtree(raw_directory)

        source_path.replace(raw_directory)
        return raw_directory

    raw_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination_path = (
        raw_directory / source_path.name
    )

    source_path.replace(destination_path)

    return destination_path


def _relative_path_or_empty(
    path: Path | None,
) -> str:
    """将已提交资产路径转换为数据库相对路径。"""

    if path is None:
        return ""

    return str(
        to_data_root_relative_path(path)
    )


def process_claimed_document_task(
    *,
    paper: dict[str, Any],
    worker_id: str,
    parser: DocumentParser,
    parser_options: Mapping[str, Any] | None = None,
    retry_delay_seconds: int = (
        DEFAULT_RETRY_DELAY_SECONDS
    ),
    commit_lease_seconds: int = (
        DEFAULT_COMMIT_LEASE_SECONDS
    ),
) -> DocumentPipelineResult:
    """
    处理一条已经领取的文档解析任务。

    paper 必须来自 claim_next_document_task()，
    且当前状态为 running。
    """

    paper_id = str(
        paper.get("_id", "")
    ).strip()
    normalized_worker_id = worker_id.strip()

    if not paper_id:
        raise ValueError(
            "paper 中缺少有效的 _id"
        )

    if not normalized_worker_id:
        raise ValueError(
            "worker_id 不能为空"
        )

    if retry_delay_seconds <= 0:
        raise ValueError(
            "retry_delay_seconds 必须大于 0"
        )

    if commit_lease_seconds <= 0:
        raise ValueError(
            "commit_lease_seconds 必须大于 0"
        )

    pdf_asset = paper.get(
        "pdf_asset",
        {},
    )

    if not isinstance(pdf_asset, dict):
        return _mark_failed(
            paper_id=paper_id,
            worker_id=normalized_worker_id,
            parser=parser,
            error="pdf_asset 不是字典",
            retry_delay_seconds=(
                retry_delay_seconds
            ),
        )

    source_pdf_relative_path = str(
        pdf_asset.get("relative_path", "")
    ).strip()
    source_pdf_sha256 = str(
        pdf_asset.get("sha256", "")
    ).strip()

    if not source_pdf_relative_path:
        return _mark_failed(
            paper_id=paper_id,
            worker_id=normalized_worker_id,
            parser=parser,
            error=(
                "pdf_asset.relative_path 为空"
            ),
            retry_delay_seconds=(
                retry_delay_seconds
            ),
        )

    if not source_pdf_sha256:
        return _mark_failed(
            paper_id=paper_id,
            worker_id=normalized_worker_id,
            parser=parser,
            error="pdf_asset.sha256 为空",
            retry_delay_seconds=(
                retry_delay_seconds
            ),
        )

    try:
        source_pdf_path = resolve_asset_path(
            source_pdf_relative_path
        )
    except Exception as error:
        return _mark_failed(
            paper_id=paper_id,
            worker_id=normalized_worker_id,
            parser=parser,
            error=(
                f"invalid_pdf_path: "
                f"{type(error).__name__}: {error}"
            ),
            retry_delay_seconds=(
                retry_delay_seconds
            ),
        )

    validation = validate_pdf_file(
        source_pdf_path
    )

    if not validation.valid:
        return _mark_failed(
            paper_id=paper_id,
            worker_id=normalized_worker_id,
            parser=parser,
            error=(
                "source_pdf_validation_failed: "
                f"{validation.error}"
            ),
            retry_delay_seconds=(
                retry_delay_seconds
            ),
        )

    if validation.sha256 != source_pdf_sha256:
        return _mark_failed(
            paper_id=paper_id,
            worker_id=normalized_worker_id,
            parser=parser,
            error=(
                "source_pdf_sha256_mismatch: "
                f"database={source_pdf_sha256}; "
                f"actual={validation.sha256}"
            ),
            retry_delay_seconds=(
                retry_delay_seconds
            ),
        )

    temp_parent = (
        get_temp_root()
        / "document_parses"
    )
    temp_parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_output_directory = Path(
        tempfile.mkdtemp(
            prefix=f"{paper_id[:12]}-",
            dir=temp_parent,
        )
    )

    try:
        effective_parser_options = dict(
            parser_options or {}
        )

        parse_result = parser.parse(
            ParseRequest(
                paper_id=paper_id,
                pdf_path=source_pdf_path,
                source_pdf_sha256=(
                    source_pdf_sha256
                ),
                output_directory=(
                    temp_output_directory
                ),
                title=str(
                    paper.get("title", "")
                ),
                parser_options=(
                    effective_parser_options
                ),
            )
        )

        if not parse_result.success:
            return _mark_failed(
                paper_id=paper_id,
                worker_id=normalized_worker_id,
                parser=parser,
                error=parse_result.error,
                retry_delay_seconds=(
                    retry_delay_seconds
                ),
            )

        if (
            parse_result.source_pdf_sha256
            != source_pdf_sha256
        ):
            return _mark_failed(
                paper_id=paper_id,
                worker_id=normalized_worker_id,
                parser=parser,
                error=(
                    "parser_source_pdf_sha256_mismatch"
                ),
                retry_delay_seconds=(
                    retry_delay_seconds
                ),
            )

        primary_assets = [
            parse_result.artifacts.markdown_path,
            parse_result.artifacts.plain_text_path,
            parse_result.artifacts.layout_path,
        ]

        if not any(primary_assets):
            return _mark_failed(
                paper_id=paper_id,
                worker_id=normalized_worker_id,
                parser=parser,
                error=(
                    "parser_returned_no_primary_asset"
                ),
                retry_delay_seconds=(
                    retry_delay_seconds
                ),
            )

        renewed = renew_document_task_lease(
            paper_id=paper_id,
            worker_id=normalized_worker_id,
            lease_seconds=(
                commit_lease_seconds
            ),
        )

        if not renewed:
            return _empty_result(
                paper_id=paper_id,
                status="ownership_lost",
                error=(
                    "task_ownership_lost_before_commit"
                ),
                parser=parser,
            )

        asset_paths = build_document_asset_paths(
            paper_id
        )

        ensure_document_asset_directories(
            asset_paths
        )

        committed_markdown = _commit_file(
            source_path=(
                parse_result
                .artifacts
                .markdown_path
            ),
            destination_path=(
                asset_paths.markdown_path
            ),
        )

        committed_plain_text = _commit_file(
            source_path=(
                parse_result
                .artifacts
                .plain_text_path
            ),
            destination_path=(
                asset_paths.plain_text_path
            ),
        )

        committed_layout = _commit_file(
            source_path=(
                parse_result
                .artifacts
                .layout_path
            ),
            destination_path=(
                asset_paths.layout_path
            ),
        )

        committed_report = _commit_file(
            source_path=(
                parse_result
                .artifacts
                .report_path
            ),
            destination_path=(
                asset_paths.parse_report_path
            ),
        )

        committed_raw_output = (
            _commit_raw_output(
                source_path=(
                    parse_result
                    .artifacts
                    .raw_output_path
                ),
                raw_directory=(
                    asset_paths.raw_directory
                ),
            )
        )

        document_relative_dir = str(
            asset_paths.relative_directory
        )
        markdown_relative_path = (
            _relative_path_or_empty(
                committed_markdown
            )
        )
        plain_text_relative_path = (
            _relative_path_or_empty(
                committed_plain_text
            )
        )
        layout_relative_path = (
            _relative_path_or_empty(
                committed_layout
            )
        )
        report_relative_path = (
            _relative_path_or_empty(
                committed_report
            )
        )
        raw_output_relative_path = (
            _relative_path_or_empty(
                committed_raw_output
            )
        )

        stored_parser_options = dict(
            effective_parser_options
        )
        stored_parser_options.update({
            "backend_name": (
                parse_result.metadata.get(
                    "backend_name",
                    "",
                )
            ),
            "backend_version": (
                parse_result.metadata.get(
                    "backend_version",
                    "",
                )
            ),
        })

        success_updated = (
            mark_document_task_success(
                paper_id=paper_id,
                worker_id=normalized_worker_id,
                parser_name=(
                    parse_result.parser_name
                ),
                parser_version=(
                    parse_result.parser_version
                ),
                source_pdf_relative_path=(
                    source_pdf_relative_path
                ),
                source_pdf_sha256=(
                    source_pdf_sha256
                ),
                document_relative_dir=(
                    document_relative_dir
                ),
                markdown_relative_path=(
                    markdown_relative_path
                ),
                plain_text_relative_path=(
                    plain_text_relative_path
                ),
                layout_relative_path=(
                    layout_relative_path
                ),
                report_relative_path=(
                    report_relative_path
                ),
                raw_output_relative_path=(
                    raw_output_relative_path
                ),
                page_count=(
                    parse_result.page_count
                ),
                char_count=(
                    parse_result.char_count
                ),
                duration_seconds=(
                    parse_result.duration_seconds
                ),
                parser_options=(
                    stored_parser_options
                ),
                warnings=list(
                    parse_result.warnings
                ),
            )
        )

        if not success_updated:
            return _empty_result(
                paper_id=paper_id,
                status="ownership_lost",
                error=(
                    "task_ownership_lost_after_commit"
                ),
                parser=parser,
            )

        return DocumentPipelineResult(
            success=True,
            paper_id=paper_id,
            status="success",
            parser_name=(
                parse_result.parser_name
            ),
            parser_version=(
                parse_result.parser_version
            ),
            document_relative_dir=(
                document_relative_dir
            ),
            markdown_relative_path=(
                markdown_relative_path
            ),
            plain_text_relative_path=(
                plain_text_relative_path
            ),
            layout_relative_path=(
                layout_relative_path
            ),
            report_relative_path=(
                report_relative_path
            ),
            raw_output_relative_path=(
                raw_output_relative_path
            ),
            page_count=(
                parse_result.page_count
            ),
            char_count=(
                parse_result.char_count
            ),
            duration_seconds=(
                parse_result.duration_seconds
            ),
            error="",
        )

    except Exception as error:
        return _mark_failed(
            paper_id=paper_id,
            worker_id=normalized_worker_id,
            parser=parser,
            error=(
                f"{type(error).__name__}: {error}"
            ),
            retry_delay_seconds=(
                retry_delay_seconds
            ),
        )

    finally:
        shutil.rmtree(
            temp_output_directory,
            ignore_errors=True,
        )
