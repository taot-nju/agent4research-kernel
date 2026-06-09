import argparse

from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.data_pipeline.pipelines.openreview_pipeline import crawl_openreview


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--venue", required=True, help="Venue name, e.g. ICLR")
    parser.add_argument("--year", required=True, type=int, help="Year, e.g. 2026")
    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="Maximum number of papers to process. Default: no limit."
    )

    args = parser.parse_args()

    MongoDBClient.ping()
    print("✅ MongoDB connected successfully.")

    crawl_openreview(
        venue=args.venue,
        year=args.year,
        max_results=args.max_results,
    )