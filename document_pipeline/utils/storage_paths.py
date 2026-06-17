"""
标准文档资产路径生成工具。

一篇论文解析后的文档资产统一存放在：

    documents/<id前2位>/<id第3-4位>/<paper_id>/

例如：

    documents/af/32/af32138f.../
        document.md
        plain_text.txt
        layout.json
        parse_report.json
        raw/

原始 PDF 不在这里重复保存。
文档资产通过 source_pdf_relative_path 和 source_pdf_sha256
关联 fulltext_pipeline 已经下载的 PDF。
"""

from dataclasses import dataclass
from pathlib import Path

from ai4research.fulltext_pipeline.config import get_data_root
from ai4research.fulltext_pipeline.utils.storage_paths import (
    validate_paper_id,
)


DOCUMENTS_DIRECTORY_NAME = "documents"

MARKDOWN_FILENAME = "document.md"
PLAIN_TEXT_FILENAME = "plain_text.txt"
LAYOUT_FILENAME = "layout.json"
PARSE_REPORT_FILENAME = "parse_report.json"
RAW_DIRECTORY_NAME = "raw"


@dataclass(frozen=True)
class DocumentAssetPaths:
    """
    一篇论文的标准文档资产路径集合。

    relative_directory：
        相对于 AI4RESEARCH_DATA_ROOT 的论文文档目录。

    absolute_directory：
        当前机器上的实际论文文档目录。
    """

    relative_directory: Path
    absolute_directory: Path

    markdown_path: Path
    plain_text_path: Path
    layout_path: Path
    parse_report_path: Path
    raw_directory: Path


def get_document_relative_directory(
    paper_id: str,
) -> Path:
    """
    返回论文文档资产的相对目录。

    示例：

        documents/af/32/af32138f...
    """

    normalized_id = validate_paper_id(paper_id)

    first_level = normalized_id[:2]
    second_level = normalized_id[2:4]

    return (
        Path(DOCUMENTS_DIRECTORY_NAME)
        / first_level
        / second_level
        / normalized_id
    )


def get_document_absolute_directory(
    paper_id: str,
) -> Path:
    """返回论文文档资产的绝对目录。"""

    return (
        get_data_root()
        / get_document_relative_directory(paper_id)
    )


def build_document_asset_paths(
    paper_id: str,
) -> DocumentAssetPaths:
    """
    生成一篇论文全部标准文档资产的路径。

    本函数只计算路径，不创建目录或文件。
    """

    relative_directory = (
        get_document_relative_directory(paper_id)
    )

    absolute_directory = (
        get_data_root() / relative_directory
    )

    return DocumentAssetPaths(
        relative_directory=relative_directory,
        absolute_directory=absolute_directory,
        markdown_path=(
            absolute_directory / MARKDOWN_FILENAME
        ),
        plain_text_path=(
            absolute_directory / PLAIN_TEXT_FILENAME
        ),
        layout_path=(
            absolute_directory / LAYOUT_FILENAME
        ),
        parse_report_path=(
            absolute_directory / PARSE_REPORT_FILENAME
        ),
        raw_directory=(
            absolute_directory / RAW_DIRECTORY_NAME
        ),
    )


def ensure_document_asset_directories(
    paths: DocumentAssetPaths,
) -> None:
    """
    创建一篇论文所需的文档资产目录。

    只创建：

        论文文档目录
        raw 原始输出目录

    不创建任何空的 Markdown、TXT 或 JSON 文件。
    """

    paths.absolute_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    paths.raw_directory.mkdir(
        parents=True,
        exist_ok=True,
    )


def to_data_root_relative_path(
    path: str | Path,
) -> Path:
    """
    将资产根目录下的绝对路径转换成数据库可保存的相对路径。

    如果路径不在 AI4RESEARCH_DATA_ROOT 下，则抛出 ValueError。
    """

    absolute_path = Path(path).expanduser().resolve()
    data_root = get_data_root().expanduser().resolve()

    try:
        return absolute_path.relative_to(data_root)
    except ValueError as error:
        raise ValueError(
            f"路径不属于资产根目录：{absolute_path}"
        ) from error