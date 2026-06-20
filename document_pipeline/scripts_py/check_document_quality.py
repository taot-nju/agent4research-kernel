"""
检查已解析文档的基础质量并回写 MongoDB。

默认只处理 quality_status=unchecked 的文档。
使用 --recheck 可以重新检查已有质量结果。
"""

import argparse
from typing import Any

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.document_pipeline.pipelines.document_quality_runner import (
    run_document_quality_checks,
)
from ai4research.document_pipeline.quality_checks.basic import (
    BasicDocumentQualityChecker,
)


DEFAULT_LIMIT = 10


def build_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description=(
            "检查已成功解析的 Markdown 和解析报告，"
            "并回写 document_asset 质量状态。"
        )
    )

    selection_group = (
        parser.add_mutually_exclusive_group(
            required=True
        )
    )

    selection_group.add_argument(
        "--paper-id",
        type=str,
        help="只检查指定 MongoDB 论文 _id。",
    )

    selection_group.add_argument(
        "--accepted-by",
        type=str,
        help=(
            '只检查指定会议，例如 "NeurIPS 2025"。'
        ),
    )

    selection_group.add_argument(
        "--all",
        action="store_true",
        help=(
            "允许从全部已解析文档中检查；"
            "仍受到 --limit 限制。"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=(
            "本次最多检查多少篇；"
            f"默认 {DEFAULT_LIMIT}。"
        ),
    )

    parser.add_argument(
        "--recheck",
        action="store_true",
        help=(
            "重新检查已有 passed、warning "
            "或 rejected 结果。"
        ),
    )

    parser.add_argument(
        "--min-average-chars-per-page",
        type=int,
        default=100,
        help="平均每页最少字符数；默认 100。",
    )

    parser.add_argument(
        "--expected-chars-per-page",
        type=int,
        default=500,
        help=(
            "计算质量分数时的期望每页字符数；"
            "默认 500。"
        ),
    )

    parser.add_argument(
        "--min-char-count-ratio",
        type=float,
        default=0.95,
        help=(
            "实际字符数与解析记录的最低一致比例；"
            "默认 0.95。"
        ),
    )

    parser.add_argument(
        "--min-title-similarity",
        type=float,
        default=0.60,
        help=(
            "文档开头与数据库标题的最低相似度；"
            "默认 0.60。"
        ),
    )

    return parser


def build_selection_filter(
    args: argparse.Namespace,
) -> dict[str, Any]:
    """根据命令行参数生成业务筛选条件。"""

    if args.paper_id:
        paper_id = args.paper_id.strip()

        if not paper_id:
            raise ValueError(
                "--paper-id 不能为空"
            )

        return {
            "_id": paper_id,
        }

    if args.accepted_by:
        accepted_by = (
            args.accepted_by.strip()
        )

        if not accepted_by:
            raise ValueError(
                "--accepted-by 不能为空"
            )

        return {
            "accepted_by": accepted_by,
        }

    if args.all:
        return {}

    raise ValueError(
        "必须指定 --paper-id、"
        "--accepted-by 或 --all"
    )


def validate_arguments(
    args: argparse.Namespace,
) -> None:
    """检查命令行参数。"""

    if args.limit <= 0:
        raise ValueError(
            "--limit 必须大于 0"
        )

    if args.min_average_chars_per_page < 0:
        raise ValueError(
            "--min-average-chars-per-page "
            "不能小于 0"
        )

    if args.expected_chars_per_page <= 0:
        raise ValueError(
            "--expected-chars-per-page "
            "必须大于 0"
        )

    if not (
        0.0
        <= args.min_char_count_ratio
        <= 1.0
    ):
        raise ValueError(
            "--min-char-count-ratio "
            "必须在 0 到 1 之间"
        )

    if not (
        0.0
        <= args.min_title_similarity
        <= 1.0
    ):
        raise ValueError(
            "--min-title-similarity "
            "必须在 0 到 1 之间"
        )


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    validate_arguments(args)

    selection_filter = build_selection_filter(
        args
    )

    checker = BasicDocumentQualityChecker(
        min_average_chars_per_page=(
            args.min_average_chars_per_page
        ),
        expected_chars_per_page=(
            args.expected_chars_per_page
        ),
        min_char_count_ratio=(
            args.min_char_count_ratio
        ),
        min_title_similarity=(
            args.min_title_similarity
        ),
    )

    MongoDBClient.ping()

    print("✅ MongoDB connected successfully.")
    print("=" * 100)
    print("文档质量检查配置")
    print("=" * 100)
    print(
        f"selection_filter:          "
        f"{selection_filter}"
    )
    print(f"limit:                     {args.limit}")
    print(f"recheck:                   {args.recheck}")
    print(
        "min_average_chars/page:    "
        f"{args.min_average_chars_per_page}"
    )
    print(
        "expected_chars/page:       "
        f"{args.expected_chars_per_page}"
    )
    print(
        "min_char_count_ratio:      "
        f"{args.min_char_count_ratio}"
    )
    print(
        "min_title_similarity:      "
        f"{args.min_title_similarity}"
    )
    print("=" * 100)

    summary = run_document_quality_checks(
        selection_filter=selection_filter,
        limit=args.limit,
        checker=checker,
        recheck=args.recheck,
    )

    print("=" * 100)
    print("文档质量检查完成")
    print("=" * 100)
    print(f"检查文档数:      {summary.checked}")
    print(f"通过:            {summary.passed}")
    print(f"警告:            {summary.warning}")
    print(f"拒绝:            {summary.rejected}")
    print(
        f"数据库更新失败:  "
        f"{summary.update_failed}"
    )
    print(f"检查异常:        {summary.errors}")
    print("=" * 100)

    if summary.checked == 0:
        print(
            "没有符合条件且需要检查的文档。"
        )


if __name__ == "__main__":
    main()
