import argparse
from rich import print

from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.data_pipeline.pipelines.pmlr_pipeline import crawl_pmlr


def main():
    parser = argparse.ArgumentParser(
        description="Crawl PMLR proceedings papers."
    )

    parser.add_argument(
        "--venue",
        type=str,
        required=True,
        help="Venue name, e.g., ICML",
    )

    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Conference year, e.g., 2022",
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
        help="Fetch each paper detail page to parse abstract and publication metadata.",
    )

    args = parser.parse_args()

    MongoDBClient.ping()
    print("✅ MongoDB connected successfully.")

    crawl_pmlr(
        venue=args.venue,
        year=args.year,
        max_results=args.max_results,
        fetch_details=args.fetch_details,
    )


if __name__ == "__main__":
    main()