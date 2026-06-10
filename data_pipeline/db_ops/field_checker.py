from rich import print

from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient


EMPTY_VALUES = ("", None, [], {})


def get_nested_value(doc, field_path):
    """
    支持点路径字段，例如：
    - abstract
    - base_urls.pmlr_pdf_url
    - openreview_obj.pdf_url
    - arxiv_obj.arxiv_id
    """
    current = doc

    for part in field_path.split("."):
        if not isinstance(current, dict):
            return None

        if part not in current:
            return None

        current = current[part]

    return current


def is_empty_value(value):
    return value in EMPTY_VALUES


def check_fields(
    fields,
    query=None,
    limit=None,
    show_examples=10,
):
    """
    检查 MongoDB 中一批论文的字段完整性。

    fields:
        需要检查的字段列表，支持点路径。

    query:
        MongoDB 查询条件，例如：
        {"accepted_by": "ICML 2022", "seen_in_sources": "PMLR"}

    limit:
        最多检查多少条；None 表示全部。

    show_examples:
        每个字段最多展示多少条缺失样例。
    """
    query = query or {}

    papers = MongoDBClient.get_collection()

    cursor = papers.find(
        query,
        {
            "title": 1,
            "accepted_by": 1,
            "seen_in_sources": 1,
            "seen_in_categories": 1,
            **{field: 1 for field in fields},
        },
    )

    if limit is not None:
        cursor = cursor.limit(limit)

    total = 0

    missing = {
        field: []
        for field in fields
    }

    for doc in cursor:
        total += 1

        for field in fields:
            value = get_nested_value(doc, field)

            if is_empty_value(value):
                missing[field].append({
                    "_id": doc.get("_id", ""),
                    "title": doc.get("title", ""),
                    "accepted_by": doc.get("accepted_by", ""),
                    "seen_in_sources": doc.get("seen_in_sources", []),
                    "seen_in_categories": doc.get("seen_in_categories", []),
                })

    print("=" * 100)
    print("[bold]Field completeness check[/bold]")
    print("=" * 100)
    print("query:", query)
    print("total checked:", total)
    print("-" * 100)

    for field in fields:
        missing_count = len(missing[field])
        present_count = total - missing_count

        print(f"[bold]{field}[/bold]")
        print(f"  present: {present_count}")
        print(f"  missing: {missing_count}")

        if total > 0:
            ratio = present_count / total * 100
            print(f"  present_ratio: {ratio:.2f}%")

        if missing_count > 0 and show_examples > 0:
            print(f"  examples, first {min(show_examples, missing_count)}:")

            for item in missing[field][:show_examples]:
                print(
                    "   - "
                    f"_id={item['_id']} | "
                    f"accepted_by={item['accepted_by']} | "
                    f"title={item['title']}"
                )

        print("-" * 100)

    return {
        "total": total,
        "missing": missing,
    }