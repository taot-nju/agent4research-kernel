"""
查看 PDF 下载任务和本地资产的整体状态。

本程序只读取 MongoDB 和本地文件，不会修改数据库，
不会下载或删除任何 PDF。

主要用途：

1. 全量下载前保存状态快照；
2. 下载过程中查看进度；
3. 全量下载后与之前的快照进行对比；
4. 查看数据库状态与本地资产数量是否大致一致。

运行示例：

# 只在终端显示报告
python -m ai4research.fulltext_pipeline.scripts_py.report_pdf_download_status

# 显示报告，并保存下载前快照
python -m ai4research.fulltext_pipeline.scripts_py.report_pdf_download_status \
  --save-json /data/ai4research_assets/reports/pdf_download_before.json
"""

import argparse
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.fulltext_pipeline.config import (
    get_data_root,
    get_pdf_root,
    get_structured_root,
    get_temp_root,
    get_txt_root,
)


PDF_URL_FIELDS = [
    "acl_anthology_obj.pdf_url",
    "aaai_obj.official_pdf_url",
    "icml_official_obj.official_pdf_url",
    "openreview_obj.pdf_url",
    "arxiv_obj.arxiv_pdf_url",
    "base_urls.pmlr_pdf_url",
    "base_urls.acl_anthology_pdf_url",
    "base_urls.official_pdf_url",
    "base_urls.openreview_pdf_url",
    "base_urls.arxiv_pdf_url",
]

KNOWN_PDF_STATUSES = [
    "pending",
    "running",
    "success",
    "failed",
    "unavailable",
]


def human_bytes(size_bytes: int) -> str:
    """把字节数转换成更容易阅读的单位。"""

    value = float(size_bytes)

    for unit in ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]:
        if value < 1024 or unit == "PiB":
            return f"{value:.2f} {unit}"

        value /= 1024

    return f"{size_bytes} B"


def scan_directory(directory: Path) -> dict[str, Any]:
    """
    递归统计目录中的文件数量和占用空间。

    同时统计：
    - PDF 文件数量；
    - .part 临时文件数量；
    - TXT 文件数量；
    - JSON 文件数量。
    """

    result: dict[str, Any] = {
        "path": str(directory),
        "exists": directory.exists(),
        "total_files": 0,
        "total_bytes": 0,
        "pdf_files": 0,
        "part_files": 0,
        "txt_files": 0,
        "json_files": 0,
        "scan_errors": 0,
    }

    if not directory.exists():
        return result

    for path in directory.rglob("*"):
        try:
            if not path.is_file():
                continue

            size_bytes = path.stat().st_size
            lower_name = path.name.lower()

            result["total_files"] += 1
            result["total_bytes"] += size_bytes

            if lower_name.endswith(".pdf"):
                result["pdf_files"] += 1

            if lower_name.endswith(".part"):
                result["part_files"] += 1

            if lower_name.endswith(".txt"):
                result["txt_files"] += 1

            if lower_name.endswith(".json"):
                result["json_files"] += 1

        except OSError:
            result["scan_errors"] += 1

    return result


def build_pdf_available_filter() -> dict[str, Any]:
    """构造“至少存在一个非空 PDF URL”的 MongoDB 查询条件。"""

    return {
        "$or": [
            {
                field: {
                    "$type": "string",
                    "$gt": "",
                }
            }
            for field in PDF_URL_FIELDS
        ]
    }


def aggregate_group_counts(
    papers,
    *,
    match_filter: dict[str, Any],
    group_field: str,
) -> dict[str, int]:
    """按照指定字段进行 MongoDB 分组计数。"""

    pipeline = [
        {
            "$match": match_filter,
        },
        {
            "$group": {
                "_id": f"${group_field}",
                "count": {
                    "$sum": 1,
                },
            }
        },
        {
            "$sort": {
                "_id": 1,
            }
        },
    ]

    result: dict[str, int] = {}

    for item in papers.aggregate(pipeline):
        key = item.get("_id")

        if key is None:
            key = "<missing>"
        elif key == "":
            key = "<empty>"
        else:
            key = str(key)

        result[key] = int(item["count"])

    return result


def collect_mongodb_statistics(papers) -> dict[str, Any]:
    """收集 MongoDB 中 PDF 下载任务的整体状态。"""

    now = datetime.now(timezone.utc)
    total_papers = papers.count_documents({})

    status_counts = {
        status: papers.count_documents({
            "pdf_asset.status": status,
        })
        for status in KNOWN_PDF_STATUSES
    }

    missing_status = papers.count_documents({
        "pdf_asset.status": {
            "$exists": False,
        }
    })

    known_status_total = sum(status_counts.values())

    other_status = (
        total_papers
        - known_status_total
        - missing_status
    )

    pdf_available_filter = build_pdf_available_filter()

    papers_with_pdf_url = papers.count_documents(
        pdf_available_filter
    )

    papers_without_pdf_url = (
        total_papers - papers_with_pdf_url
    )

    success_with_relative_path = papers.count_documents({
        "pdf_asset.status": "success",
        "pdf_asset.relative_path": {
            "$type": "string",
            "$gt": "",
        },
    })

    success_without_relative_path = papers.count_documents({
        "pdf_asset.status": "success",
        "$or": [
            {
                "pdf_asset.relative_path": {
                    "$exists": False,
                }
            },
            {
                "pdf_asset.relative_path": "",
            },
            {
                "pdf_asset.relative_path": None,
            },
        ],
    })

    legacy_downloaded_true = papers.count_documents({
        "processing_status.pdf_downloaded": True,
    })

    local_pdf_path_nonempty = papers.count_documents({
        "local_pdf_path": {
            "$type": "string",
            "$gt": "",
        }
    })

    expired_running = papers.count_documents({
        "pdf_asset.status": "running",
        "$or": [
            {
                "pdf_asset.lease_until": None,
            },
            {
                "pdf_asset.lease_until": {
                    "$lte": now,
                }
            },
        ],
    })

    active_running = (
        status_counts["running"] - expired_running
    )

    retryable_failed = papers.count_documents({
        "pdf_asset.status": "failed",
        "pdf_asset.attempts": {
            "$lt": 3,
        },
        "$or": [
            {
                "pdf_asset.next_retry_at": None,
            },
            {
                "pdf_asset.next_retry_at": {
                    "$lte": now,
                }
            },
        ],
    })

    max_attempts_reached = papers.count_documents({
        "pdf_asset.status": "failed",
        "pdf_asset.attempts": {
            "$gte": 3,
        },
    })

    unavailable_with_pdf_url = papers.count_documents({
        "$and": [
            {
                "pdf_asset.status": "unavailable",
            },
            pdf_available_filter,
        ]
    })

    size_pipeline = [
        {
            "$match": {
                "pdf_asset.status": "success",
            }
        },
        {
            "$group": {
                "_id": None,
                "total_size_bytes": {
                    "$sum": {
                        "$ifNull": [
                            "$pdf_asset.size_bytes",
                            0,
                        ]
                    }
                },
            }
        },
    ]

    size_result = list(papers.aggregate(size_pipeline))

    database_success_size_bytes = (
        int(size_result[0]["total_size_bytes"])
        if size_result
        else 0
    )

    attempts_distribution = aggregate_group_counts(
        papers,
        match_filter={},
        group_field="pdf_asset.attempts",
    )

    success_source_distribution = aggregate_group_counts(
        papers,
        match_filter={
            "pdf_asset.status": "success",
        },
        group_field="pdf_asset.source",
    )

    return {
        "total_papers": total_papers,
        "status_counts": status_counts,
        "missing_status": missing_status,
        "other_status": other_status,
        "papers_with_pdf_url": papers_with_pdf_url,
        "papers_without_pdf_url": papers_without_pdf_url,
        "success_with_relative_path": success_with_relative_path,
        "success_without_relative_path": (
            success_without_relative_path
        ),
        "legacy_downloaded_true": legacy_downloaded_true,
        "local_pdf_path_nonempty": local_pdf_path_nonempty,
        "active_running": active_running,
        "expired_running": expired_running,
        "retryable_failed": retryable_failed,
        "max_attempts_reached": max_attempts_reached,
        "unavailable_with_pdf_url": (
            unavailable_with_pdf_url
        ),
        "database_success_size_bytes": (
            database_success_size_bytes
        ),
        "attempts_distribution": attempts_distribution,
        "success_source_distribution": (
            success_source_distribution
        ),
    }


def print_directory_statistics(
    name: str,
    statistics: dict[str, Any],
) -> None:
    """打印一个资产目录的统计信息。"""

    print(f"{name}:")
    print(f"  路径:             {statistics['path']}")
    print(f"  是否存在:         {statistics['exists']}")
    print(f"  文件总数:         {statistics['total_files']}")
    print(
        "  占用空间:         "
        f"{human_bytes(statistics['total_bytes'])} "
        f"({statistics['total_bytes']} bytes)"
    )
    print(f"  PDF 文件数:       {statistics['pdf_files']}")
    print(f"  TXT 文件数:       {statistics['txt_files']}")
    print(f"  JSON 文件数:      {statistics['json_files']}")
    print(f"  .part 临时文件数: {statistics['part_files']}")
    print(f"  扫描错误数:       {statistics['scan_errors']}")


def print_mapping(
    title: str,
    mapping: dict[str, int],
) -> None:
    """打印字典形式的分布统计。"""

    print(title)

    if not mapping:
        print("  <empty>: 0")
        return

    for key, count in mapping.items():
        print(f"  {key:<30} {count}")


def build_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description=(
            "查看 PDF 下载状态、本地资产占用空间，"
            "并可保存 JSON 快照用于下载前后对比。"
        )
    )

    parser.add_argument(
        "--save-json",
        type=str,
        default="",
        help=(
            "可选。把本次报告保存为 JSON 文件，"
            "例如 /data/ai4research_assets/reports/"
            "pdf_download_before.json"
        ),
    )

    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    MongoDBClient.ping()
    papers = MongoDBClient.get_collection()

    data_root = get_data_root()

    root_statistics = scan_directory(data_root)
    pdf_statistics = scan_directory(get_pdf_root())
    txt_statistics = scan_directory(get_txt_root())
    structured_statistics = scan_directory(
        get_structured_root()
    )
    temp_statistics = scan_directory(get_temp_root())

    disk_usage = shutil.disk_usage(data_root)

    mongodb_statistics = collect_mongodb_statistics(
        papers
    )

    snapshot = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "data_root": str(data_root),
        "filesystem": {
            "total_bytes": disk_usage.total,
            "used_bytes": disk_usage.used,
            "free_bytes": disk_usage.free,
        },
        "asset_directories": {
            "root": root_statistics,
            "pdf": pdf_statistics,
            "txt": txt_statistics,
            "structured": structured_statistics,
            "temp": temp_statistics,
        },
        "mongodb": mongodb_statistics,
    }

    print("=" * 110)
    print("AI4Research PDF 下载状态报告")
    print("=" * 110)
    print(f"生成时间（UTC）: {snapshot['generated_at_utc']}")
    print(f"资产根目录:       {data_root}")

    print("=" * 110)
    print("一、所在磁盘分区")
    print("=" * 110)
    print(
        "分区总容量: "
        f"{human_bytes(disk_usage.total)}"
    )
    print(
        "分区已使用: "
        f"{human_bytes(disk_usage.used)}"
    )
    print(
        "分区剩余空间: "
        f"{human_bytes(disk_usage.free)}"
    )

    print("=" * 110)
    print("二、本地资产目录")
    print("=" * 110)

    print_directory_statistics(
        "资产根目录总体",
        root_statistics,
    )
    print("-" * 110)

    print_directory_statistics(
        "PDF 目录",
        pdf_statistics,
    )
    print("-" * 110)

    print_directory_statistics(
        "TXT 目录",
        txt_statistics,
    )
    print("-" * 110)

    print_directory_statistics(
        "Structured 目录",
        structured_statistics,
    )
    print("-" * 110)

    print_directory_statistics(
        "Temp 目录",
        temp_statistics,
    )

    mongo = mongodb_statistics
    statuses = mongo["status_counts"]

    print("=" * 110)
    print("三、MongoDB PDF 任务状态")
    print("=" * 110)
    print(f"论文总数:                  {mongo['total_papers']}")
    print(f"pending:                   {statuses['pending']}")
    print(f"running:                   {statuses['running']}")
    print(f"success:                   {statuses['success']}")
    print(f"failed:                    {statuses['failed']}")
    print(f"unavailable:               {statuses['unavailable']}")
    print(f"缺少 pdf_asset.status:     {mongo['missing_status']}")
    print(f"其他未知状态:              {mongo['other_status']}")

    print("-" * 110)
    print(f"具有 PDF URL:              {mongo['papers_with_pdf_url']}")
    print(f"没有 PDF URL:              {mongo['papers_without_pdf_url']}")
    print(
        "success 且相对路径非空:   "
        f"{mongo['success_with_relative_path']}"
    )
    print(
        "success 但相对路径为空:   "
        f"{mongo['success_without_relative_path']}"
    )
    print(
        "旧字段 pdf_downloaded=True: "
        f"{mongo['legacy_downloaded_true']}"
    )
    print(
        "旧字段 local_pdf_path 非空: "
        f"{mongo['local_pdf_path_nonempty']}"
    )

    print("-" * 110)
    print(f"有效租约中的 running:      {mongo['active_running']}")
    print(f"租约已过期的 running:      {mongo['expired_running']}")
    print(f"当前可重试的 failed:       {mongo['retryable_failed']}")
    print(f"已达到最大尝试次数:        {mongo['max_attempts_reached']}")
    print(
        "unavailable 但已有 URL:   "
        f"{mongo['unavailable_with_pdf_url']}"
    )

    print("-" * 110)
    print(
        "数据库记录的 success PDF 总大小: "
        f"{human_bytes(mongo['database_success_size_bytes'])} "
        f"({mongo['database_success_size_bytes']} bytes)"
    )

    print("=" * 110)
    print("四、尝试次数分布")
    print("=" * 110)
    print_mapping(
        "pdf_asset.attempts:",
        mongo["attempts_distribution"],
    )

    print("=" * 110)
    print("五、成功下载来源分布")
    print("=" * 110)
    print_mapping(
        "pdf_asset.source:",
        mongo["success_source_distribution"],
    )

    print("=" * 110)
    print("六、本地文件与数据库的总体对照")
    print("=" * 110)
    print(
        "本地 PDF 文件数:          "
        f"{pdf_statistics['pdf_files']}"
    )
    print(
        "MongoDB success 数:       "
        f"{statuses['success']}"
    )
    print(
        "本地 PDF 目录实际大小:    "
        f"{human_bytes(pdf_statistics['total_bytes'])}"
    )
    print(
        "数据库 success 大小合计:  "
        f"{human_bytes(mongo['database_success_size_bytes'])}"
    )
    print(
        "残留 .part 临时文件数:    "
        f"{root_statistics['part_files']}"
    )

    if args.save_json:
        output_path = Path(
            args.save_json
        ).expanduser().resolve()

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path.write_text(
            json.dumps(
                snapshot,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        print("=" * 110)
        print(f"✅ JSON 快照已保存：{output_path}")

    print("=" * 110)
    print("✅ PDF 下载状态报告生成完成")


if __name__ == "__main__":
    main()


