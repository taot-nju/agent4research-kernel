"""
初始化 MongoDB 索引。

索引用于提高高频查询字段的查询效率，并通过唯一索引避免重复插入同一篇 arXiv 论文。
"""

from pymongo import errors

from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient


def init_indexes():
    papers = MongoDBClient.get_collection()

    try:
        # 基础查询字段
        papers.create_index("title")
        papers.create_index("tags")
        papers.create_index("accepted_by")
        papers.create_index("references.title")
        papers.create_index("seen_in_sources")
        papers.create_index("seen_in_categories")

        # arXiv ID 唯一索引：
        # 只对非空 arxiv_id 生效，避免多个非 arXiv 论文或空 arxiv_id 发生唯一键冲突。
        papers.create_index(
            "arxiv_obj.arxiv_id",
            unique=True,
            partialFilterExpression={
                "arxiv_obj.arxiv_id": {
                    "$type": "string",
                    "$gt": ""
                }
            }
        )

        # OpenReview forum_id 唯一索引：
        # 同理，只对非空 forum_id 生效，避免重复插入同一篇 OpenReview 论文。
        papers.create_index(
            "openreview_obj.forum_id",
            unique=True,
            partialFilterExpression={
                "openreview_obj.forum_id": {
                    "$type": "string",
                    "$gt": ""
                }
            }
        )

        # OpenReview venue 普通索引（按会议检索）
        papers.create_index("openreview_obj.venue")

        print("✅ MongoDB indexes initialized successfully.")

    except errors.DuplicateKeyError as e:
        print(f"⚠️ Duplicate keys exist, some unique indexes not created: {e}")

    except Exception as e:
        print(f"⚠️ Index creation failed: {e}")