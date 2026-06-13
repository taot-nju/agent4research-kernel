"""
AAAI 官方 Proceedings 爬取命令行入口。

示例：

调试爬取 3 篇：
python -m ai4research.data_pipeline.scripts_py.crawl_aaai_official \
  --year 2026 \
  --max-results 3

正式全量爬取：
python -m ai4research.data_pipeline.scripts_py.crawl_aaai_official \
  --year 2026
"""

import argparse

from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.data_pipeline.pipelines.aaai_official_pipeline import (
    crawl_aaai_official,
)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crawl AAAI official proceedings papers."
    )

    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="AAAI year, e.g. 2026",
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        help=(
            "Maximum number of papers to process. "
            "Default: no limit."
        ),
    )

    args = parser.parse_args()

    MongoDBClient.ping()
    print("✅ MongoDB connected successfully.")

    crawl_aaai_official(
        year=args.year,
        max_results=args.max_results,
    )