"""
根据 PDF 资产状态刷新文档解析任务的可用性。

同步规则：

    pdf_asset.status = success
    document_asset.status = blocked
        -> pending

    pdf_asset.status != success
    document_asset.status = pending
        -> blocked

已经处于 running、success、failed、stale 等状态的文档任务
不会被本程序覆盖。

运行示例：

# 预览全部论文，不修改数据库
python -m ai4research.document_pipeline.scripts_py.refresh_document_availability \
  --all \
  --dry-run

# 正式刷新全部论文
python -m ai4research.document_pipeline.scripts_py.refresh_document_availability \
  --all \
  --execute

# 刷新指定论文
python -m ai4research.document_pipeline.scripts_py.refresh_document_availability \
  --paper-id <paper_id> \
  --execute

# 刷新指定会议
python -m ai4research.document_pipeline.scripts_py.refresh_document_availability \
  --accepted-by "ICLR 2026" \
  --execute
"""

import argparse
from typing import Any

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.document_pipeline.repositories.document_task_repository import (
    refresh_document_availability,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description=(
            "根据 pdf_asset.status 刷新 "
            "document_asset.status。"
        )
    )

    selection_group = parser.add_mutually_exclusive_group(
        required=True
    )

    selection_group.add_argument(
        "--paper-id",
        type=str,
        help="只刷新指定 MongoDB 论文 _id。",
    )

    selection_group.add_argument(
        "--accepted-by",
        type=str,
        help='只刷新指定会议，例如 "ICLR 2026"。',
    )

    selection_group.add_argument(
        "--all",
        action="store_true",
        help="刷新全部论文记录。",
    )

    action_group = parser.add_mutually_exclusive_group(
        required=True
    )

    action_group.add_argument(
        "--dry-run",
        action="store_true",
        help="只统计预计变化，不修改数据库。",
    )

    action_group.add_argument(
        "--execute",
        action="store_true",
        help="正式执行状态刷新。",
    )

    return parser


def build_selection_filter(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """根据命令行参数生成业务筛选条件。"""

    if args.paper_id:
        paper_id = args.paper_id.strip()

        if not paper_id:
            raise ValueError("--paper-id 不能为空")

        return {
            "_id": paper_id,
        }

    if args.accepted_by:
        accepted_by = args.accepted_by.strip()

        if not accepted_by:
            raise ValueError("--accepted-by 不能为空")

        return {
            "accepted_by": accepted_by,
        }

    if args.all:
        return None

    raise ValueError(
        "必须指定 --paper-id、--accepted-by 或 --all"
    )


def combine_filters(
    *conditions: dict[str, Any],
) -> dict[str, Any]:
    """将多个非空查询条件组合成 MongoDB $and。"""

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


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    selection_filter = build_selection_filter(args)
    business_filter = selection_filter or {}

    MongoDBClient.ping()
    papers = MongoDBClient.get_collection()

    blocked_to_pending_query = combine_filters(
        business_filter,
        {
            "pdf_asset.status": "success",
        },
        {
            "document_asset.status": "blocked",
        },
    )

    pending_to_blocked_query = combine_filters(
        business_filter,
        {
            "pdf_asset.status": {
                "$ne": "success",
            },
        },
        {
            "document_asset.status": "pending",
        },
    )

    blocked_to_pending_count = papers.count_documents(
        blocked_to_pending_query
    )

    pending_to_blocked_count = papers.count_documents(
        pending_to_blocked_query
    )

    expected_modified_count = (
        blocked_to_pending_count
        + pending_to_blocked_count
    )

    print("✅ MongoDB connected successfully.")
    print("=" * 100)
    print("文档解析任务可用性刷新配置")
    print("=" * 100)
    print(
        f"selection_filter:       "
        f"{selection_filter or {}}"
    )
    print(
        f"blocked -> pending:     "
        f"{blocked_to_pending_count}"
    )
    print(
        f"pending -> blocked:     "
        f"{pending_to_blocked_count}"
    )
    print(
        f"预计修改总数:          "
        f"{expected_modified_count}"
    )
    print(
        "mode:                   "
        f"{'dry-run' if args.dry_run else 'execute'}"
    )
    print("=" * 100)

    if args.dry_run:
        print("✅ 预览完成；没有修改数据库")
        return

    result = refresh_document_availability(
        selection_filter=selection_filter,
    )

    print("文档解析任务可用性刷新完成")
    print("=" * 100)
    print(
        f"blocked -> pending: "
        f"{result.blocked_to_pending}"
    )
    print(
        f"pending -> blocked: "
        f"{result.pending_to_blocked}"
    )
    print(
        f"实际修改总数:      "
        f"{result.modified_count}"
    )
    print("=" * 100)

    if result.modified_count == 0:
        print("没有需要刷新的文档解析任务。")
    else:
        print("✅ 文档解析任务可用性状态已同步")


if __name__ == "__main__":
    main()