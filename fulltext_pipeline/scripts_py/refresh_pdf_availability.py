"""
重新检查 unavailable 论文的 PDF 地址可用性。

当论文最初没有 PDF URL 时，其状态可能为：

    pdf_asset.status = unavailable

后续爬虫、数据融合或人工补充 PDF URL 后，可运行本命令，
将已经具备 PDF 候选地址的论文恢复为：

    pdf_asset.status = pending

恢复后，download_pdfs.py 就可以正常领取并下载这些论文。

运行示例：

# 刷新一篇指定论文
python -m ai4research.fulltext_pipeline.scripts_py.refresh_pdf_availability \
  --paper-id 31f2484a0f52c4c584dd0e2dc7df002c289e55ca

# 刷新某个会议
python -m ai4research.fulltext_pipeline.scripts_py.refresh_pdf_availability \
  --accepted-by "ICML 2026"

# 刷新数据库中的全部 unavailable 论文
python -m ai4research.fulltext_pipeline.scripts_py.refresh_pdf_availability \
  --all
"""

import argparse
from typing import Any

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.fulltext_pipeline.repositories.pdf_task_repository import (
    refresh_unavailable_pdf_tasks,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description=(
            "检查 unavailable 论文是否已经出现 PDF URL，"
            "并将符合条件的任务恢复为 pending。"
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
        help='只刷新指定会议，例如 "ICML 2026"。',
    )

    selection_group.add_argument(
        "--all",
        action="store_true",
        help="检查全部 unavailable 论文。",
    )

    return parser


def build_selection_filter(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """根据命令行参数生成 MongoDB 筛选条件。"""

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


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    selection_filter = build_selection_filter(args)

    MongoDBClient.ping()
    print("✅ MongoDB connected successfully.")

    print("=" * 100)
    print("PDF 可用性刷新配置")
    print("=" * 100)
    print(
        "selection_filter: "
        f"{selection_filter if selection_filter else '{}'}"
    )

    modified_count = refresh_unavailable_pdf_tasks(
        selection_filter=selection_filter,
    )

    print("=" * 100)
    print("PDF 可用性刷新完成")
    print("=" * 100)
    print(
        "恢复为 pending 的论文数: "
        f"{modified_count}"
    )

    if modified_count == 0:
        print(
            "没有发现已经补充 PDF URL 的 unavailable 论文。"
        )
    else:
        print(
            "这些论文现在可以由 download_pdfs.py 领取。"
        )


if __name__ == "__main__":
    main()