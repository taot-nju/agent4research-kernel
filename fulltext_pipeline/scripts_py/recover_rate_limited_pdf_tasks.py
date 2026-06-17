"""
恢复因 HTTP 429 限流而耗尽重试次数的 PDF 下载任务。

旧版本下载器将 HTTP 429 当作普通下载失败，可能导致任务的
pdf_asset.attempts 达到最大值，无法再次领取。

本程序只恢复满足以下条件的记录：

    pdf_asset.status = failed
    pdf_asset.http_status = 429

恢复后：

    pdf_asset.status         保持 failed
    pdf_asset.attempts       重置为 0
    pdf_asset.next_retry_at  设置为当前时间
    pdf_asset.worker_id      清空
    pdf_asset.lease_until    清空

原始 http_status 和 last_error 会被保留。

运行示例：

# 先预览全部历史 429 记录，不修改数据库
python -m ai4research.fulltext_pipeline.scripts_py.recover_rate_limited_pdf_tasks \
  --all \
  --dry-run

# 恢复全部历史 429 记录
python -m ai4research.fulltext_pipeline.scripts_py.recover_rate_limited_pdf_tasks \
  --all \
  --execute

# 只恢复指定会议
python -m ai4research.fulltext_pipeline.scripts_py.recover_rate_limited_pdf_tasks \
  --accepted-by "ICLR 2025" \
  --execute

# 最多恢复前 100 条
python -m ai4research.fulltext_pipeline.scripts_py.recover_rate_limited_pdf_tasks \
  --all \
  --limit 100 \
  --execute
"""

import argparse
from typing import Any

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.fulltext_pipeline.repositories.pdf_task_repository import (
    recover_rate_limited_pdf_tasks,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description=(
            "预览或恢复因 HTTP 429 限流而耗尽 attempts "
            "的 PDF 下载任务。"
        )
    )

    selection_group = parser.add_mutually_exclusive_group(
        required=True
    )

    selection_group.add_argument(
        "--paper-id",
        type=str,
        help="只处理指定 MongoDB 论文 _id。",
    )

    selection_group.add_argument(
        "--accepted-by",
        type=str,
        help='只处理指定会议，例如 "ICLR 2025"。',
    )

    selection_group.add_argument(
        "--all",
        action="store_true",
        help="处理全部历史 HTTP 429 任务。",
    )

    action_group = parser.add_mutually_exclusive_group(
        required=True
    )

    action_group.add_argument(
        "--dry-run",
        action="store_true",
        help="只统计将被恢复的任务，不修改数据库。",
    )

    action_group.add_argument(
        "--execute",
        action="store_true",
        help="正式执行恢复操作。",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多处理多少条记录；默认处理全部符合条件的记录。",
    )

    return parser


def build_selection_filter(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """根据参数生成额外业务筛选条件。"""

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


def build_rate_limited_query(
    selection_filter: dict[str, Any] | None,
) -> dict[str, Any]:
    """生成历史 HTTP 429 任务的完整查询条件。"""

    conditions: list[dict[str, Any]] = [
        {
            "pdf_asset.status": "failed",
        },
        {
            "pdf_asset.http_status": 429,
        },
    ]

    if selection_filter:
        conditions.insert(0, selection_filter)

    return {
        "$and": conditions,
    }


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit 必须大于 0")

    selection_filter = build_selection_filter(args)
    query = build_rate_limited_query(selection_filter)

    MongoDBClient.ping()
    papers = MongoDBClient.get_collection()

    matched_count = papers.count_documents(query)

    effective_count = matched_count

    if args.limit is not None:
        effective_count = min(
            matched_count,
            args.limit,
        )

    print("✅ MongoDB connected successfully.")
    print("=" * 100)
    print("HTTP 429 PDF 任务恢复配置")
    print("=" * 100)
    print(f"selection_filter: {selection_filter or {}}")
    print(f"matched_count:    {matched_count}")
    print(f"limit:            {args.limit}")
    print(f"effective_count:  {effective_count}")
    print(
        "mode:             "
        f"{'dry-run' if args.dry_run else 'execute'}"
    )
    print("=" * 100)

    if args.dry_run:
        print("✅ 预览完成；没有修改数据库")
        return

    modified_count = recover_rate_limited_pdf_tasks(
        selection_filter=selection_filter,
        limit=args.limit,
    )

    print("HTTP 429 PDF 任务恢复完成")
    print("=" * 100)
    print(f"预计处理记录数: {effective_count}")
    print(f"实际修改记录数: {modified_count}")
    print("=" * 100)

    if modified_count == 0:
        print("没有符合条件的 HTTP 429 任务需要恢复。")
    else:
        print(
            "✅ 历史 HTTP 429 任务已恢复为可重新领取状态"
        )


if __name__ == "__main__":
    main()