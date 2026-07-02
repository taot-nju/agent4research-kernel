"""从 MongoDB 读取可进入 chunk 流程的文档来源。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.fulltext_pipeline.utils.storage_paths import (
    resolve_asset_path,
)


@dataclass(frozen=True)
class IndexableDocumentSource:
    """一篇通过质量门槛的标准 Markdown 来源。"""

    paper_id: str
    title: str

    markdown_relative_path: str
    markdown_path: Path

    source_pdf_sha256: str
    parser_name: str
    parser_version: str
    quality_status: str

    def __post_init__(self) -> None:
        if not self.paper_id.strip():
            raise ValueError("paper_id 不能为空")

        if not self.markdown_relative_path.strip():
            raise ValueError(
                "markdown_relative_path 不能为空"
            )

        if not isinstance(
            self.markdown_path,
            Path,
        ):
            raise TypeError(
                "markdown_path 必须是 pathlib.Path"
            )

        if not self.source_pdf_sha256.strip():
            raise ValueError(
                "source_pdf_sha256 不能为空"
            )

        if not self.parser_name.strip():
            raise ValueError(
                "parser_name 不能为空"
            )

        if not self.parser_version.strip():
            raise ValueError(
                "parser_version 不能为空"
            )

        if not self.quality_status.strip():
            raise ValueError(
                "quality_status 不能为空"
            )


def load_indexable_document_source(
    *,
    paper_id: str,
    allowed_quality_statuses: tuple[
        str,
        ...,
    ] = ("passed", "warning"),
) -> IndexableDocumentSource:
    """读取并验证一篇可索引的标准 Markdown 文档。"""

    normalized_paper_id = paper_id.strip()

    if not normalized_paper_id:
        raise ValueError("paper_id 不能为空")

    normalized_quality_statuses = {
        status.strip()
        for status in allowed_quality_statuses
        if status.strip()
    }

    if not normalized_quality_statuses:
        raise ValueError(
            "allowed_quality_statuses 不能为空"
        )

    collection = MongoDBClient.get_collection()

    paper = collection.find_one(
        {"_id": normalized_paper_id},
        {
            "_id": 1,
            "title": 1,
            "pdf_asset.status": 1,
            "pdf_asset.sha256": 1,
            "document_asset.status": 1,
            "document_asset.quality_status": 1,
            "document_asset.markdown_relative_path": 1,
            "document_asset.source_pdf_sha256": 1,
            "document_asset.parser_name": 1,
            "document_asset.parser_version": 1,
        },
    )

    if paper is None:
        raise LookupError(
            f"论文不存在：{normalized_paper_id}"
        )

    pdf_asset = paper.get(
        "pdf_asset",
        {},
    )
    document_asset = paper.get(
        "document_asset",
        {},
    )

    if not isinstance(pdf_asset, dict):
        pdf_asset = {}

    if not isinstance(document_asset, dict):
        document_asset = {}

    document_status = str(
        document_asset.get("status", "")
    ).strip()

    if document_status != "success":
        raise ValueError(
            "文档尚不可索引："
            f"document_status={document_status or 'missing'}"
        )

    quality_status = str(
        document_asset.get(
            "quality_status",
            "",
        )
    ).strip()

    if (
        quality_status
        not in normalized_quality_statuses
    ):
        raise ValueError(
            "文档质量状态不允许索引："
            f"quality_status={quality_status or 'missing'}"
        )

    markdown_relative_path = str(
        document_asset.get(
            "markdown_relative_path",
            "",
        )
    ).strip()

    if not markdown_relative_path:
        raise ValueError(
            "document_asset 缺少 Markdown 路径"
        )

    source_pdf_sha256 = str(
        document_asset.get(
            "source_pdf_sha256",
            "",
        )
    ).strip()

    current_pdf_sha256 = str(
        pdf_asset.get("sha256", "")
    ).strip()

    if not source_pdf_sha256:
        raise ValueError(
            "document_asset 缺少来源 PDF SHA256"
        )

    if (
        current_pdf_sha256
        and current_pdf_sha256
        != source_pdf_sha256
    ):
        raise ValueError(
            "文档来源 PDF 已变化，需要重新解析"
        )

    parser_name = str(
        document_asset.get(
            "parser_name",
            "",
        )
    ).strip()
    parser_version = str(
        document_asset.get(
            "parser_version",
            "",
        )
    ).strip()

    if not parser_name or not parser_version:
        raise ValueError(
            "document_asset 缺少解析器信息"
        )

    markdown_path = resolve_asset_path(
        markdown_relative_path
    )

    if not markdown_path.is_file():
        raise FileNotFoundError(
            f"Markdown 文件不存在：{markdown_path}"
        )

    return IndexableDocumentSource(
        paper_id=normalized_paper_id,
        title=str(
            paper.get("title", "")
        ).strip(),
        markdown_relative_path=(
            markdown_relative_path
        ),
        markdown_path=markdown_path,
        source_pdf_sha256=source_pdf_sha256,
        parser_name=parser_name,
        parser_version=parser_version,
        quality_status=quality_status,
    )
