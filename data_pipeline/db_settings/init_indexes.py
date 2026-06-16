"""
初始化 MongoDB 索引。

索引用于提高高频查询字段的查询效率，并通过唯一索引避免重复插入同一篇 arXiv 论文。
"""

from pymongo import ASCENDING, errors

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

        # PDF 下载任务索引
        #
        # 1. 通用任务领取：
        #    status + attempts 用于筛选可领取任务；
        #    _id 用于稳定排序和逐条领取。
        papers.create_index(
            [
                ("pdf_asset.status", ASCENDING),
                ("pdf_asset.attempts", ASCENDING),
                ("_id", ASCENDING),
            ],
            name="pdf_task_claim_idx",
        )

        # 2. 按会议下载：
        #    支持 --accepted-by "ICLR 2022" 等高频场景。
        papers.create_index(
            [
                ("accepted_by", ASCENDING),
                ("pdf_asset.status", ASCENDING),
                ("pdf_asset.attempts", ASCENDING),
                ("_id", ASCENDING),
            ],
            name="accepted_by_pdf_task_claim_idx",
        )

        # 3. failed 任务的重试时间查询。
        papers.create_index(
            [
                ("pdf_asset.status", ASCENDING),
                ("pdf_asset.next_retry_at", ASCENDING),
                ("pdf_asset.attempts", ASCENDING),
                ("_id", ASCENDING),
            ],
            name="pdf_task_retry_idx",
        )

        # 4. running 任务的租约过期接管查询。
        papers.create_index(
            [
                ("pdf_asset.status", ASCENDING),
                ("pdf_asset.lease_until", ASCENDING),
                ("pdf_asset.attempts", ASCENDING),
                ("_id", ASCENDING),
            ],
            name="pdf_task_lease_idx",
        )

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

        print("✅ MongoDB indexes initialized successfully.")

    except errors.DuplicateKeyError as e:
        print(f"⚠️ Duplicate keys exist, some unique indexes not created: {e}")

    except Exception as e:
        print(f"⚠️ Index creation failed: {e}")