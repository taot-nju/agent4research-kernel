"""
文档质量检查顺序运行器。

质量检查与 OCR 解析相互独立：
- 可以只检查尚未质检的文档；
- 可以在规则升级后重新检查已有文档；
- 不需要重新执行 OCR。
"""

from dataclasses import asdict, dataclass
from typing import Any

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.document_pipeline.quality_checks.base import (
    DocumentQualityChecker,
    DocumentQualityRequest,
)
from ai4research.document_pipeline.repositories.document_quality_repository import (
    mark_document_quality_result,
)
from ai4research.fulltext_pipeline.utils.storage_paths import (
    resolve_asset_path,
)


@dataclass
class DocumentQualityRunSummary:
    """一次质量检查运行的统计结果。"""

    checked: int = 0
    passed: int = 0
    warning: int = 0
    rejected: int = 0
    update_failed: int = 0
    errors: int = 0

    def record_status(
        self,
        status: str,
    ) -> None:
        """记录质量状态。"""

        if status == "passed":
            self.passed += 1
        elif status == "warning":
            self.warning += 1
        elif status == "rejected":
            self.rejected += 1

    def to_dict(self) -> dict[str, int]:
        """转换为普通字典。"""

        return asdict(self)


def _combine_filters(
    *conditions: dict[str, Any],
) -> dict[str, Any]:
    """组合多个 MongoDB 查询条件。"""

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


def run_document_quality_checks(
    *,
    selection_filter: dict[str, Any],
    limit: int,
    checker: DocumentQualityChecker,
    recheck: bool = False,
) -> DocumentQualityRunSummary:
    """顺序检查一批已成功解析的文档。"""

    if not isinstance(selection_filter, dict):
        raise TypeError(
            "selection_filter 必须是字典"
        )

    if limit <= 0:
        raise ValueError(
            "limit 必须大于 0"
        )

    conditions = [
        selection_filter,
        {
            "document_asset.status": "success",
        },
        {
            "document_asset.markdown_relative_path": {
                "$type": "string",
                "$gt": "",
            }
        },
    ]

    if not recheck:
        conditions.append({
            "document_asset.quality_status": (
                "unchecked"
            ),
        })

    query = _combine_filters(
        *conditions
    )

    papers = MongoDBClient.get_collection()
    summary = DocumentQualityRunSummary()

    cursor = (
        papers.find(
            query,
            {
                "title": 1,
                "pdf_asset.sha256": 1,
                "document_asset": 1,
            },
        )
        .sort("_id", 1)
        .limit(limit)
    )

    for paper in cursor:
        summary.checked += 1

        paper_id = str(
            paper.get("_id", "")
        )
        title = str(
            paper.get("title", "")
        )
        asset = paper.get(
            "document_asset",
            {},
        )

        print("-" * 100)
        print(
            f"[QUALITY {summary.checked}/{limit} checked_limit] "
            f"paper_id={paper_id}"
        )
        print(f"title={title}")

        try:
            markdown_relative_path = str(
                asset.get(
                    "markdown_relative_path",
                    "",
                )
            ).strip()
            report_relative_path = str(
                asset.get(
                    "report_relative_path",
                    "",
                )
            ).strip()
            source_pdf_sha256 = str(
                asset.get(
                    "source_pdf_sha256",
                    "",
                )
            ).strip()

            markdown_path = resolve_asset_path(
                markdown_relative_path
            )

            report_path = (
                resolve_asset_path(
                    report_relative_path
                )
                if report_relative_path
                else None
            )

            result = checker.check(
                DocumentQualityRequest(
                    paper_id=paper_id,
                    title=title,
                    markdown_path=markdown_path,
                    report_path=report_path,
                    page_count=int(
                        asset.get(
                            "page_count",
                            0,
                        )
                    ),
                    char_count=int(
                        asset.get(
                            "char_count",
                            0,
                        )
                    ),
                )
            )

            updated = (
                mark_document_quality_result(
                    paper_id=paper_id,
                    source_pdf_sha256=(
                        source_pdf_sha256
                    ),
                    checker_name=checker.name,
                    checker_version=(
                        checker.version
                    ),
                    result=result,
                )
            )

            if not updated:
                summary.update_failed += 1

                print(
                    "status=update_failed | "
                    "文档或 PDF 版本可能已变化"
                )
                continue

            summary.record_status(
                result.status
            )

            print(
                f"status={result.status} | "
                f"score={result.score:.4f}"
            )

            if result.warnings:
                print(
                    f"warnings={result.warnings}"
                )

        except Exception as error:
            summary.errors += 1

            print(
                "status=error | "
                f"{type(error).__name__}: {error}"
            )

    return summary
