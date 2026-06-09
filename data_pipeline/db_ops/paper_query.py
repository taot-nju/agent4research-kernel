"""
论文查询相关数据库操作。

职责：
1. 根据 _id 查询论文；
2. 根据标题模糊查询论文；
3. 查询某些字段非空的论文；
4. 只做 read-only 操作，不负责删除和修改。
"""

import re
from difflib import SequenceMatcher

from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.data_pipeline.utils.text_utils import normalize_title


EMPTY_VALUES = ["", [], {}, None]


def get_paper_by_id(paper_id: str):
    """
    根据 MongoDB _id 精确查询一篇论文。
    """
    papers = MongoDBClient.get_collection()
    return papers.find_one({"_id": paper_id})


def find_papers_by_title(title_query: str, limit: int = 10, min_score: float = 0.65):
    """
    根据标题模糊查询论文。

    适用情况：
    - 用户输入完整标题；
    - 用户输入标题的一部分；
    - 大小写、标点、空格和数据库中略有不同。

    返回：
    [
        {
            "score": 相似度,
            "paper": 论文记录
        },
        ...
    ]
    """
    papers = MongoDBClient.get_collection()

    normalized_query = normalize_title(title_query)
    if not normalized_query:
        raise ValueError("title_query cannot be empty.")

    # 第一层：先用正则粗筛，减少全库扫描压力
    # 例如输入 "YYy"，可以匹配标题中包含 YYy 的记录
    regex = re.compile(re.escape(title_query), re.IGNORECASE)

    candidates = list(
        papers.find(
            {"title": {"$regex": regex}},
            limit=limit * 5
        )
    )

    # 第二层：如果粗筛没有结果，则退化为扫描 title 字段
    # 适合处理 "xx:yyy" vs "XX: YYy?" 这种标点/空格差异
    if not candidates:
        candidates = list(
            papers.find(
                {},
                {
                    "_id": 1,
                    "title": 1,
                    "authors": 1,
                    "abstract": 1,
                    "arxiv_obj": 1,
                    "accepted_by": 1,
                    "seen_in_sources": 1,
                    "seen_in_categories": 1,
                    "base_urls": 1,
                    "edit_logs": 1,
                }
            )
        )

    results = []

    for paper in candidates:
        db_title = paper.get("title", "")
        normalized_db_title = normalize_title(db_title)

        if not normalized_db_title:
            continue

        # 子串匹配直接给较高分
        if normalized_query in normalized_db_title:
            score = 1.0
        else:
            score = SequenceMatcher(
                None,
                normalized_query,
                normalized_db_title
            ).ratio()

        if score >= min_score:
            results.append({
                "score": score,
                "paper": paper
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def find_papers_with_non_empty_fields(fields, limit: int = 20):
    """
    查询指定字段都不为空的论文。

    fields 示例：
        ["abstract"]
        ["abstract", "arxiv_obj.arxiv_id"]
        ["pipeline", "baselines", "benchmarks"]

    注意：
        所有字段之间是 AND 关系。
        即：这些字段必须同时非空。
    """
    papers = MongoDBClient.get_collection()

    query = {}
    for field in fields:
        query[field] = {
            "$exists": True,
            "$nin": EMPTY_VALUES
        }

    return list(papers.find(query).limit(limit))


def find_papers_by_field_value(field: str, value, limit: int = 20):
    """
    按指定字段的值精确查询论文。

    示例：
        field="accepted_by", value="arXiv"
        field="arxiv_obj.arxiv_id", value="2606.02965"
    """
    papers = MongoDBClient.get_collection()

    query = {
        field: value
    }

    return list(papers.find(query).limit(limit))

