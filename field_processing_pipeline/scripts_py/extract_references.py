"""
功能②命令行入口：从论文 PDF 抽取参考文献 + 每条的 in-text 引用上下文（GROBID）。

需先有可达的 GROBID 服务（默认 http://localhost:8070，可用 GROBID_URL 覆盖）。
windows_N 在读时现算，这里不落库；--window-n 仅预留。

示例：
  # 单篇（最常用于验证）
  python -m ai4research.field_processing_pipeline.scripts_py.extract_references --id <paper_id> --force
  # 按会议批量
  python -m ai4research.field_processing_pipeline.scripts_py.extract_references --accepted-by "ICLR 2025" --limit 20
  # 按来源
  python -m ai4research.field_processing_pipeline.scripts_py.extract_references --source OpenReview
"""

import argparse

from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.field_processing_pipeline.pipelines.reference_pipeline import (
    extract_references_for_papers,
)


def main():
    parser = argparse.ArgumentParser(
        description="Extract references + in-text citation contexts via GROBID."
    )
    parser.add_argument("--id", type=str, default=None, help="只处理单篇 _id")
    parser.add_argument("--accepted-by", type=str, default=None, help='按 accepted_by 选，如 "ICLR 2025"')
    parser.add_argument("--source", type=str, default=None, help="按 seen_in_sources 选，如 OpenReview")
    parser.add_argument("--limit", type=int, default=20, help="最多处理多少篇")
    parser.add_argument("--window-n", type=int, default=2, help="上下文窗口句数（读时现算，预留）")
    parser.add_argument("--force", action="store_true", help="忽略 references_extracted 闸门，强制重抽")
    parser.add_argument("--sleep", type=float, default=0.0, help="每篇间隔秒（限流）")
    args = parser.parse_args()

    if MongoDBClient.ping():
        print("✅ MongoDB connected successfully.")

    extract_references_for_papers(
        paper_id=args.id,
        accepted_by=args.accepted_by,
        source=args.source,
        limit=args.limit,
        window_n=args.window_n,
        force=args.force,
        sleep=args.sleep,
    )


if __name__ == "__main__":
    main()
