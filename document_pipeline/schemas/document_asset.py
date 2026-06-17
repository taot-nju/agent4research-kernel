"""
标准文档资产状态结构。

document_asset 用于记录：

1. PDF 是否已经进入文档解析流程；
2. 使用了哪个解析器和版本；
3. 生成了哪些 Markdown、TXT、JSON 资产；
4. 这些资产对应哪个版本的 PDF；
5. 解析程序是否成功；
6. 解析质量是否通过检查；
7. 并发任务领取、重试和租约信息。

本模块只定义默认结构，不执行数据库操作。
"""

from copy import deepcopy
from typing import Any


DOCUMENT_PARSE_STATUSES = {
    "pending",
    "running",
    "success",
    "failed",
    "blocked",
    "stale",
}

DOCUMENT_QUALITY_STATUSES = {
    "unchecked",
    "passed",
    "warning",
    "rejected",
}


DEFAULT_DOCUMENT_ASSET: dict[str, Any] = {
    # ------------------------------------------------------------
    # 文档解析任务状态
    # ------------------------------------------------------------
    #
    # pending：
    #   已具备可用 PDF，等待解析。
    #
    # running：
    #   某个 Worker 正在处理。
    #
    # success：
    #   解析器已经成功生成标准文档资产。
    #   注意：不代表质量检查一定通过。
    #
    # failed：
    #   解析过程失败，可以按照重试策略重新处理。
    #
    # blocked：
    #   当前缺少可用 PDF，暂时无法解析。
    #
    # stale：
    #   PDF 已经变化，现有文档资产需要重新生成。
    "status": "pending",

    # ------------------------------------------------------------
    # 解析器信息
    # ------------------------------------------------------------
    "parser_name": "",
    "parser_version": "",

    # 保存解析时使用的参数摘要。
    #
    # 例如：
    # {
    #     "page_batch_size": 4,
    #     "timeout_seconds": 300
    # }
    "parser_options": {},

    # ------------------------------------------------------------
    # 来源 PDF
    # ------------------------------------------------------------
    #
    # 文档资产必须绑定生成它时所使用的 PDF。
    # 如果这里的哈希与 pdf_asset.sha256 不一致，
    # 应将 document_asset.status 标记为 stale。
    "source_pdf_relative_path": "",
    "source_pdf_sha256": "",

    # ------------------------------------------------------------
    # 标准文档资产路径
    # ------------------------------------------------------------
    #
    # 所有路径均相对于 AI4RESEARCH_DATA_ROOT，
    # 不保存 /home/tao/... 或 /data/... 等机器绝对路径。
    "document_relative_dir": "",
    "markdown_relative_path": "",
    "plain_text_relative_path": "",
    "layout_relative_path": "",
    "report_relative_path": "",
    "raw_output_relative_path": "",

    # ------------------------------------------------------------
    # 解析结果统计
    # ------------------------------------------------------------
    "page_count": 0,
    "char_count": 0,
    "duration_seconds": 0.0,

    # ------------------------------------------------------------
    # 质量检查
    # ------------------------------------------------------------
    #
    # unchecked：
    #   尚未执行质量检查。
    #
    # passed：
    #   通过当前基础质量规则。
    #
    # warning：
    #   结果可以保留，但存在需要关注的问题。
    #
    # rejected：
    #   结果不适合进入后续 RAG 流程。
    "quality_status": "unchecked",
    "quality_score": None,

    # 保存每一项质量检查的结果。
    #
    # 例如：
    # {
    #     "non_empty": {
    #         "passed": True,
    #         "value": 48231
    #     },
    #     "title_match": {
    #         "passed": False,
    #         "score": 0.42
    #     }
    # }
    "quality_checks": {},

    # 解析器和质量检查产生的非致命警告。
    "warnings": [],

    # ------------------------------------------------------------
    # 任务执行与错误信息
    # ------------------------------------------------------------
    "attempts": 0,
    "last_error": "",

    # 时间字段由 Python datetime 写入 MongoDB，
    # 在 MongoDB 中保存为 BSON Date，统一使用 UTC 时间。
    "started_at": None,
    "last_checked_at": None,
    "next_retry_at": None,
    "parsed_at": None,
    "updated_at": None,

    # ------------------------------------------------------------
    # 并发任务领取和异常恢复
    # ------------------------------------------------------------
    "worker_id": "",
    "lease_until": None,
}


def create_default_document_asset() -> dict[str, Any]:
    """
    返回一份独立的 document_asset 默认结构。

    使用 deepcopy 是为了避免多篇论文共享同一个嵌套字典、
    列表或 parser_options 对象。
    """

    return deepcopy(DEFAULT_DOCUMENT_ASSET)


def validate_document_status(status: str) -> str:
    """验证并返回合法的文档解析状态。"""

    normalized_status = status.strip()

    if normalized_status not in DOCUMENT_PARSE_STATUSES:
        raise ValueError(
            f"不支持的 document status：{normalized_status}"
        )

    return normalized_status


def validate_quality_status(status: str) -> str:
    """验证并返回合法的文档质量状态。"""

    normalized_status = status.strip()

    if normalized_status not in DOCUMENT_QUALITY_STATUSES:
        raise ValueError(
            f"不支持的 quality status：{normalized_status}"
        )

    return normalized_status