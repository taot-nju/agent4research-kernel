import argparse

from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.data_pipeline.pipelines.arxiv_daily import crawl_daily


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", help="Start date YYYY-MM-DD", default=None)
    parser.add_argument("--end", help="End date YYYY-MM-DD", default=None)
    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="Maximum number of papers per category. Default: no limit."
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        default=None,
        help="arXiv categories to crawl, e.g. --categories cs.AI cs.CL"
    )
        
    args = parser.parse_args()

    MongoDBClient.ping()
    print("✅ MongoDB connected successfully.")

    crawl_daily(
        start_date=args.start, 
        end_date=args.end, 
        max_results=args.max_results, 
        categories=args.categories
    )