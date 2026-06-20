"""
文档质量结果的 MongoDB 持久化。

质量检查器只负责计算结果；
本模块负责在确认 PDF 版本未变化后安全回写。
"""

from typing import Any

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.document_pipeline.quality_checks.base import (
    DocumentQualityResult,
)
from ai4research.document_pipeline.repositories.document_task_repository import (
    utc_now,
)


def build_quality_checks_document(
    *,
    checker_name: str,
    checker_version: str,
    result: DocumentQualityResult,
) -> dict[str, Any]:
    """将质量结果转换为 MongoDB 可保存结构。"""

    normalized_name = checker_name.strip()
    normalized_version = checker_version.strip()

    if not normalized_name:
        raise ValueError(
            "checker_name 不能为空"
        )

    if not normalized_version:
        raise ValueError(
            "checker_version 不能为空"
        )

    checks_document: dict[str, Any] = {
        "_checker": {
            "name": normalized_name,
            "version": normalized_version,
        }
    }

    for check in result.checks:
        checks_document[check.name] = {
            "passed": check.passed,
            "score": check.score,
            "weight": check.weight,
            "critical": check.critical,
            "message": check.message,
            "details": dict(check.details),
        }

    return checks_document


def mark_document_quality_result(
    *,
    paper_id: str,
    source_pdf_sha256: str,
    checker_name: str,
    checker_version: str,
    result: DocumentQualityResult,
) -> bool:
    """
    将文档质量结果写入 MongoDB。

    只有同时满足以下条件才允许更新：

    1. document_asset.status = success；
    2. 文档绑定的 PDF SHA256 未变化；
    3. 当前 pdf_asset.sha256 仍与解析来源一致。
    """

    normalized_paper_id = paper_id.strip()
    normalized_sha256 = source_pdf_sha256.strip()

    if not normalized_paper_id:
        raise ValueError(
            "paper_id 不能为空"
        )

    if not normalized_sha256:
        raise ValueError(
            "source_pdf_sha256 不能为空"
        )

    checks_document = (
        build_quality_checks_document(
            checker_name=checker_name,
            checker_version=checker_version,
            result=result,
        )
    )

    now = utc_now()
    papers = MongoDBClient.get_collection()

    update_document: dict[str, Any] = {
        "$set": {
            "document_asset.quality_status": (
                result.status
            ),
            "document_asset.quality_score": (
                result.score
            ),
            "document_asset.quality_checks": (
                checks_document
            ),
            "document_asset.last_checked_at": now,
            "document_asset.updated_at": now,
        }
    }

    if result.warnings:
        update_document["$addToSet"] = {
            "document_asset.warnings": {
                "$each": list(
                    result.warnings
                )
            }
        }

    update_result = papers.update_one(
        {
            "_id": normalized_paper_id,
            "document_asset.status": "success",
            "document_asset.source_pdf_sha256": (
                normalized_sha256
            ),
            "pdf_asset.sha256": normalized_sha256,
        },
        update_document,
    )

    return update_result.modified_count == 1
