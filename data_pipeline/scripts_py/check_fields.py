import argparse
import json
from rich import print

from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.data_pipeline.db_ops.field_checker import check_fields


def build_query(args):
    query = {}

    if args.accepted_by:
        query["accepted_by"] = args.accepted_by

    if args.source:
        query["seen_in_sources"] = args.source

    if args.category:
        query["seen_in_categories"] = args.category

    if args.query_json:
        try:
            extra_query = json.loads(args.query_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid --query-json: {e}")

        if not isinstance(extra_query, dict):
            raise ValueError("--query-json must be a JSON object.")

        query.update(extra_query)

    return query


def main():
    parser = argparse.ArgumentParser(
        description="Check field completeness for papers in MongoDB."
    )

    parser.add_argument(
        "--field",
        action="append",
        required=True,
        help=(
            "Field path to check. Can be used multiple times. "
            "Examples: abstract, base_urls.pmlr_pdf_url, openreview_obj.pdf_url"
        ),
    )

    parser.add_argument(
        "--accepted-by",
        type=str,
        default=None,
        help='Filter by accepted_by, e.g., "ICML 2022".',
    )

    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help='Filter by seen_in_sources, e.g., "PMLR" or "OpenReview".',
    )

    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help='Filter by seen_in_categories, e.g., "PMLR v162".',
    )

    parser.add_argument(
        "--query-json",
        type=str,
        default=None,
        help=(
            "Extra MongoDB query as JSON string. "
            "Example: '{\"accepted_by\": \"ICML 2022\"}'"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of documents to check.",
    )

    parser.add_argument(
        "--show-examples",
        type=int,
        default=10,
        help="Show at most this many missing examples per field.",
    )

    args = parser.parse_args()

    MongoDBClient.ping()
    print("✅ MongoDB connected successfully.")

    query = build_query(args)

    check_fields(
        fields=args.field,
        query=query,
        limit=args.limit,
        show_examples=args.show_examples,
    )


if __name__ == "__main__":
    main()