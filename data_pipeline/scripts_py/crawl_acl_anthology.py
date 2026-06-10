import argparse

from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.data_pipeline.pipelines.acl_anthology_pipeline import crawl_acl_anthology


def main():
    parser = argparse.ArgumentParser(
        description="Crawl papers from ACL Anthology volumes."
    )

    parser.add_argument(
        "--venue",
        type=str,
        default="ACL",
        help="Venue name, default: ACL",
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Conference year, e.g., 2025",
    )
    parser.add_argument(
        "--subtype",
        type=str,
        default="long",
        help="Volume subtype, e.g., long",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="Maximum number of papers to crawl for debugging.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.5,
        help="Delay between paper detail page requests.",
    )

    args = parser.parse_args()

    if MongoDBClient.ping():
        print("✅ MongoDB connected successfully.")

    crawl_acl_anthology(
        venue=args.venue,
        year=args.year,
        subtype=args.subtype,
        max_results=args.max_results,
        delay_seconds=args.delay_seconds,
    )


if __name__ == "__main__":
    main()