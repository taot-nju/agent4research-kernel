import argparse
from pprint import pprint

from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.data_pipeline.db_ops.paper_query import (
    get_paper_by_id,
    find_papers_by_title,
    find_papers_with_non_empty_fields,
    find_papers_by_field_value,
)


def print_brief_paper(doc, score=None, show_abstract=False):
    """
    打印论文的简要信息，适合命令行快速查看。
    """
    if score is not None:
        print(f"score: {score:.4f}")

    print(f"_id: {doc.get('_id', '')}")
    print(f"title: {doc.get('title', '')}")
    print(f"accepted_by: {doc.get('accepted_by', '')}")

    arxiv_obj = doc.get("arxiv_obj", {})
    print(f"arxiv_id: {arxiv_obj.get('arxiv_id', '')}")
    print(f"arxiv_categories: {arxiv_obj.get('arxiv_categories', [])}")

    print(f"seen_in_sources: {doc.get('seen_in_sources', [])}")
    print(f"seen_in_categories: {doc.get('seen_in_categories', [])}")

    base_urls = doc.get("base_urls", {})
    if base_urls:
        print(f"arxiv_url: {base_urls.get('arxiv_url', '')}")
        print(f"arxiv_pdf_url: {base_urls.get('arxiv_pdf_url', '')}")

    if show_abstract:
        abstract = doc.get("abstract", "")
        print(f"abstract: {abstract[:300]}{'...' if len(abstract) > 300 else ''}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--id", help="MongoDB _id of the paper", default=None)
    parser.add_argument("--title", help="Title or partial title of the paper", default=None)

    parser.add_argument(
        "--non-empty",
        nargs="+",
        default=None,
        help="Find papers where all given fields are non-empty. Example: --non-empty abstract arxiv_obj.arxiv_id"
    )

    parser.add_argument(
        "--brief",
        action="store_true",
        help="Print brief paper information instead of full document."
    )

    parser.add_argument(
        "--show-abstract",
        action="store_true",
        help="Show abstract preview in brief mode."
    )

    parser.add_argument("--limit", type=int, default=10)

    parser.add_argument("--field", help="Field name for exact value query", default=None)
    parser.add_argument("--value", help="Field value for exact value query", default=None)

    args = parser.parse_args()

    MongoDBClient.ping()
    print("✅ MongoDB connected successfully.")

    if args.id:
        doc = get_paper_by_id(args.id)
        if args.brief and doc:
            print_brief_paper(doc, show_abstract=args.show_abstract)
        else:
            pprint(doc)

    elif args.title:
        results = find_papers_by_title(
            title_query=args.title,
            limit=args.limit,
        )

        print(f"Found {len(results)} result(s).")
        for item in results:
            print("=" * 100)
            print(f"score: {item['score']:.4f}")
            if args.brief:
                print_brief_paper(item["paper"], score=item["score"], show_abstract=args.show_abstract)
            else:
                print(f"score: {item['score']:.4f}")
                pprint(item["paper"])

    elif args.field and args.value is not None:
        docs = find_papers_by_field_value(
            field=args.field,
            value=args.value,
            limit=args.limit,
        )

        print(f"Found {len(docs)} result(s).")
        for doc in docs:
            print("=" * 100)
            if args.brief:
                print_brief_paper(doc, show_abstract=args.show_abstract)
            else:
                pprint(doc)

    elif args.non_empty:
        docs = find_papers_with_non_empty_fields(
            fields=args.non_empty,
            limit=args.limit,
        )

        print(f"Found {len(docs)} result(s).")
        for doc in docs:
            print("=" * 100)
            if args.brief:
                print_brief_paper(doc, show_abstract=args.show_abstract)
            else:
                pprint(doc)

    else:
        parser.print_help()