import argparse
from rich import print

from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.data_pipeline.pipelines.icml_official_pipeline import crawl_icml_official


def main():
    parser = argparse.ArgumentParser(
        description="Crawl ICML official website papers."
    )

    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="ICML year, e.g., 2026",
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="Maximum number of papers to process for debugging.",
    )

    parser.add_argument(
        "--fetch-details",
        action="store_true",
        help="Fetch each detail page to parse authors and abstract.",
    )

    args = parser.parse_args()

    MongoDBClient.ping()
    print("✅ MongoDB connected successfully.")

    crawl_icml_official(
        year=args.year,
        max_results=args.max_results,
        fetch_details=args.fetch_details,
    )


if __name__ == "__main__":
    main()