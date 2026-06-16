"""
审计已经下载成功的 PDF 资产。

本程序只读取 MongoDB 和本地文件，不修改数据库，也不删除文件。

检查内容：

1. pdf_asset.relative_path 是否为空；
2. 本地文件是否存在；
3. 文件是否通过 PDF 基础校验；
4. 本地文件大小是否与 MongoDB 一致；
5. 本地文件 SHA256 是否与 MongoDB 一致。

运行示例：

# 检查指定论文
python -m ai4research.fulltext_pipeline.scripts_py.audit_pdf_assets \
  --paper-id af32138f7c04e15f3d021a8008bbc64b66f1ba23

# 检查某个会议最多 100 篇已下载论文
python -m ai4research.fulltext_pipeline.scripts_py.audit_pdf_assets \
  --accepted-by "ICLR 2022" \
  --limit 100

# 检查全部已下载论文中的前 1000 篇
python -m ai4research.fulltext_pipeline.scripts_py.audit_pdf_assets \
  --all \
  --limit 1000
"""

import argparse
from dataclasses import dataclass
from typing import Any

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.fulltext_pipeline.utils.pdf_validator import (
    validate_pdf_file,
)
from ai4research.fulltext_pipeline.utils.storage_paths import (
    resolve_asset_path,
)


DEFAULT_LIMIT = 100


@dataclass
class PDFAuditSummary:
    """一次 PDF 资产审计的统计结果。"""

    checked: int = 0
    valid: int = 0

    empty_relative_path: int = 0
    file_missing: int = 0
    validation_failed: int = 0
    size_mismatch: int = 0
    sha256_mismatch: int = 0

    def issue_count(self) -> int:
        """返回发现问题的论文总数。"""

        return (
            self.empty_relative_path
            + self.file_missing
            + self.validation_failed
            + self.size_mismatch
            + self.sha256_mismatch
        )


def build_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description=(
            "检查 MongoDB 中已标记 success 的 PDF，"
            "验证本地文件、大小和 SHA256 是否一致。"
        )
    )

    selection_group = parser.add_mutually_exclusive_group(
        required=True
    )

    selection_group.add_argument(
        "--paper-id",
        type=str,
        help="只检查指定 MongoDB 论文 _id。",
    )

    selection_group.add_argument(
        "--accepted-by",
        type=str,
        help='只检查指定会议，例如 "ICLR 2022"。',
    )

    selection_group.add_argument(
        "--all",
        action="store_true",
        help="从全部已下载成功的 PDF 中进行检查。",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=(
            "本次最多检查的论文数量，"
            f"默认值为 {DEFAULT_LIMIT}。"
        ),
    )

    return parser


def build_selection_filter(
    args: argparse.Namespace,
) -> dict[str, Any]:
    """根据命令行参数生成 MongoDB 筛选条件。"""

    conditions: list[dict[str, Any]] = [
        {
            "pdf_asset.status": "success",
        }
    ]

    if args.paper_id:
        paper_id = args.paper_id.strip()

        if not paper_id:
            raise ValueError("--paper-id 不能为空")

        conditions.append({
            "_id": paper_id,
        })

    elif args.accepted_by:
        accepted_by = args.accepted_by.strip()

        if not accepted_by:
            raise ValueError("--accepted-by 不能为空")

        conditions.append({
            "accepted_by": accepted_by,
        })

    elif not args.all:
        raise ValueError(
            "必须指定 --paper-id、--accepted-by 或 --all"
        )

    return {
        "$and": conditions,
    }


def validate_arguments(args: argparse.Namespace) -> None:
    """检查命令行参数是否合法。"""

    if args.limit <= 0:
        raise ValueError("--limit 必须大于 0")


def print_issue(
    *,
    paper_id: str,
    title: str,
    issue: str,
    detail: str,
) -> None:
    """打印一条审计异常。"""

    print("-" * 100)
    print(f"paper_id: {paper_id}")
    print(f"title:    {title}")
    print(f"issue:    {issue}")
    print(f"detail:   {detail}")


def audit_one_paper(
    paper: dict[str, Any],
    summary: PDFAuditSummary,
) -> None:
    """审计一篇已经标记为 success 的论文。"""

    summary.checked += 1

    paper_id = str(paper.get("_id", ""))
    title = str(paper.get("title", ""))

    pdf_asset = paper.get("pdf_asset", {})

    if not isinstance(pdf_asset, dict):
        summary.validation_failed += 1

        print_issue(
            paper_id=paper_id,
            title=title,
            issue="invalid_pdf_asset",
            detail="pdf_asset 不是字典",
        )
        return

    relative_path = str(
        pdf_asset.get("relative_path", "")
    ).strip()

    if not relative_path:
        summary.empty_relative_path += 1

        print_issue(
            paper_id=paper_id,
            title=title,
            issue="empty_relative_path",
            detail="pdf_asset.relative_path 为空",
        )
        return

    try:
        absolute_path = resolve_asset_path(relative_path)
    except (TypeError, ValueError) as error:
        summary.validation_failed += 1

        print_issue(
            paper_id=paper_id,
            title=title,
            issue="invalid_relative_path",
            detail=str(error),
        )
        return

    if not absolute_path.exists():
        summary.file_missing += 1

        print_issue(
            paper_id=paper_id,
            title=title,
            issue="file_missing",
            detail=str(absolute_path),
        )
        return

    validation = validate_pdf_file(absolute_path)

    if not validation.valid:
        summary.validation_failed += 1

        print_issue(
            paper_id=paper_id,
            title=title,
            issue="pdf_validation_failed",
            detail=(
                f"path={absolute_path}; "
                f"error={validation.error}"
            ),
        )
        return

    database_size = pdf_asset.get("size_bytes", 0)
    database_sha256 = str(
        pdf_asset.get("sha256", "")
    ).strip()

    if validation.size_bytes != database_size:
        summary.size_mismatch += 1

        print_issue(
            paper_id=paper_id,
            title=title,
            issue="size_mismatch",
            detail=(
                f"database={database_size}; "
                f"actual={validation.size_bytes}; "
                f"path={absolute_path}"
            ),
        )
        return

    if validation.sha256 != database_sha256:
        summary.sha256_mismatch += 1

        print_issue(
            paper_id=paper_id,
            title=title,
            issue="sha256_mismatch",
            detail=(
                f"database={database_sha256}; "
                f"actual={validation.sha256}; "
                f"path={absolute_path}"
            ),
        )
        return

    summary.valid += 1


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    validate_arguments(args)
    selection_filter = build_selection_filter(args)

    MongoDBClient.ping()
    papers = MongoDBClient.get_collection()

    print("✅ MongoDB connected successfully.")
    print("=" * 100)
    print("PDF 资产审计配置")
    print("=" * 100)
    print(f"selection_filter: {selection_filter}")
    print(f"limit:            {args.limit}")
    print("=" * 100)

    summary = PDFAuditSummary()

    cursor = papers.find(
        selection_filter,
        {
            "title": 1,
            "accepted_by": 1,
            "pdf_asset": 1,
        },
    ).sort("_id", 1).limit(args.limit)

    for paper in cursor:
        audit_one_paper(
            paper=paper,
            summary=summary,
        )

    print("=" * 100)
    print("PDF 资产审计完成")
    print("=" * 100)
    print(f"检查论文数:          {summary.checked}")
    print(f"完全正常:            {summary.valid}")
    print(f"相对路径为空:        {summary.empty_relative_path}")
    print(f"本地文件不存在:      {summary.file_missing}")
    print(f"PDF 基础校验失败:    {summary.validation_failed}")
    print(f"文件大小不一致:      {summary.size_mismatch}")
    print(f"SHA256 不一致:       {summary.sha256_mismatch}")
    print(f"问题总数:            {summary.issue_count()}")
    print("=" * 100)

    if summary.checked == 0:
        print("没有找到符合条件且状态为 success 的 PDF。")
    elif summary.issue_count() == 0:
        print("✅ 所有被检查的 PDF 资产均与 MongoDB 记录一致")
    else:
        print(
            "⚠️ 发现 PDF 资产异常。"
            "本程序只报告问题，不会自动修改数据库或文件。"
        )


if __name__ == "__main__":
    main()
