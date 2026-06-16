from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.data_pipeline.utils.time_utils import now_beijing_iso
from ai4research.data_pipeline.schemas.paper_schema import CURRENT_SCHEMA_VERSION, DEFAULT_PAPER_FIELDS
from rich import print


def is_empty_value(value):
    """
    判断一个字段值是否为空。
    """
    return value in ("", [], {}, None)


def merge_missing_fields(old: dict, new: dict, prefix: str = "") -> dict:
    """
    仅补全 old 中为空 / 不存在的字段。

    支持嵌套字典，会返回 MongoDB 可直接用于 $set 的点路径字段。
    """
    updates = {}

    for key, new_value in new.items():
        field_path = f"{prefix}.{key}" if prefix else key
        old_value = old.get(key, None)

        if isinstance(old_value, dict) and isinstance(new_value, dict):
            nested_updates = merge_missing_fields(
                old=old_value,
                new=new_value,
                prefix=field_path
            )
            updates.update(nested_updates)

        elif key not in old:
            updates[field_path] = new_value

        elif is_empty_value(old_value) and not is_empty_value(new_value):
            updates[field_path] = new_value

    return updates


def upsert_paper(paper_data: dict, source: str, category: str = None):
    """
    upsert论文，自动区分全新/已有/不同来源更新

    :param paper_data: 单篇论文的字典
    :param source: 数据来源，例如 "arXiv", "NeurIPS 2024"
    :param category: arXiv分类（cs.AI, cs.CL,...），非arXiv可不传
    """
    papers = MongoDBClient.get_collection()

    # 避免与 $addToSet / $push 操作冲突的字段
    paper_data.pop("seen_in_categories", None)
    paper_data.pop("seen_in_sources", None)
    paper_data.pop("edit_logs", None)

    doc = papers.find_one({"_id": paper_data["_id"]})

    if doc is None:
        # 全新论文
        edit_log = {
            "time": now_beijing_iso(),
            "op": f"insert from {source}" + (f" @ {category}" if category else ""),
            "detail": "insert paper metadata"
        }
        update_dict = {
            "$set": paper_data,
            "$setOnInsert": {"_schema_version": CURRENT_SCHEMA_VERSION},
            "$addToSet": {"seen_in_sources": source},
            "$push": {"edit_logs": edit_log}
        }
        if category:
            update_dict["$addToSet"]["seen_in_categories"] = category

        papers.update_one({"_id": paper_data["_id"]}, update_dict, upsert=True)
        print(f"✅ Inserted new paper: {paper_data['_id']}")
    else:
        # 已存在（同源：都来自arXiv，虽然category不同，但依然是同源 —— 同arXiv）
        if source in doc.get("seen_in_sources", []):
            # 同源，但可能有信息补全
            patch = merge_missing_fields(doc, paper_data)

            if patch:
                edit_log = {
                    "time": now_beijing_iso(),
                    "op": f"patch update from {source}",
                    "detail": f"fields updated: {list(patch.keys())}"
                }
                update_ops = {
                    "$set": patch,
                    "$push": {"edit_logs": edit_log}
                }

                if category:
                    update_ops["$addToSet"] = {"seen_in_categories": category}

                papers.update_one(
                    {"_id": paper_data["_id"]},
                    update_ops
                )
                print(f"🩹 Patched paper fields: {paper_data['_id']} -> {list(patch.keys())}")
            else:
                edit_log = {
                    "time": now_beijing_iso(),
                    "op": f"no update, already seen during crawling {source}" + (f" , current category is {category}." if category else ""),
                    "detail": "no richer info"
                }
                update_ops = {
                    "$push": {"edit_logs": edit_log}
                }

                if category:
                    update_ops["$addToSet"] = {"seen_in_categories": category}

                papers.update_one(
                    {"_id": paper_data["_id"]},
                    update_ops
                )
                print(f"♻️ No update, paper already seen from this source: {paper_data['_id']}")
        # else:
        #     # 不同源，更新字段
        #     edit_log = {
        #         "time": now_beijing_iso(),
        #         "op": f"update from {source}" + (f" @ {category}" if category else ""),
        #         "detail": "update paper metadata"
        #     }


        #     update_dict = {
        #         "$set": paper_data,
        #         "$addToSet": {"seen_in_sources": source},
        #         "$push": {"edit_logs": edit_log}
        #     }


        #     if category:
        #         update_dict["$addToSet"]["seen_in_categories"] = category

        #     papers.update_one({"_id": paper_data["_id"]}, update_dict)
        #     print(f"♻️ Updated paper from new source: {paper_data['_id']}")
        # else:
        #     # 不同源：只补充缺失/空字段，避免用新来源的默认空值覆盖已有来源信息
        #     patch = merge_missing_fields(doc, paper_data)

        #     edit_log = {
        #         "time": now_beijing_iso(),
        #         "op": f"update from {source}" + (f" @ {category}" if category else ""),
        #         "detail": f"fields updated: {list(patch.keys())}" if patch else "new source recorded only"
        #     }
        else:
            # 不同源：只补充缺失/空字段，避免新来源的空值覆盖已有数据
            patch = merge_missing_fields(doc, paper_data)

            # arXiv 预印本被正式会议/期刊录用后，更新 accepted_by
            old_accepted_by = doc.get("accepted_by", "")
            new_accepted_by = paper_data.get("accepted_by", "")

            old_is_arxiv = (
                isinstance(old_accepted_by, str)
                and old_accepted_by.strip().lower().startswith("arxiv")
            )

            new_is_formal_venue = (
                isinstance(new_accepted_by, str)
                and new_accepted_by.strip()
                and not new_accepted_by.strip().lower().startswith("arxiv")
            )

            if old_is_arxiv and new_is_formal_venue:
                patch["accepted_by"] = new_accepted_by

            edit_log = {
                "time": now_beijing_iso(),
                "op": f"update from {source}" + (
                    f" @ {category}" if category else ""
                ),
                "detail": (
                    f"fields updated: {list(patch.keys())}"
                    if patch
                    else "new source recorded only"
                ),
            }

            update_ops = {
                "$addToSet": {"seen_in_sources": source},
                "$push": {"edit_logs": edit_log}
            }

            if patch:
                update_ops["$set"] = patch

            if category:
                update_ops["$addToSet"]["seen_in_categories"] = category

            papers.update_one({"_id": paper_data["_id"]}, update_ops)
            print(f"♻️ Updated paper from new source: {paper_data['_id']}")

    print("[red]One record processed!")

def migrate_schema():
    """
    遍历整个 papers 集合，执行 Schema 迁移：

    v1 -> v2:
    - 将旧字段 official_obj 重命名为 icml_official_obj

    通用处理：
    - 补齐 DEFAULT_PAPER_FIELDS 中缺失的顶层字段
    - 更新 _schema_version

    该方法仅手动/定期执行。
    """

    client = MongoDBClient._client

    if client is None:
        client = MongoDBClient.get_collection().database.client

    papers = MongoDBClient.get_collection()

    # ------------------------------------------------------------------
    # Schema v1 -> v2
    # 先重命名旧字段，必须在补齐默认字段之前执行。
    #
    # 过滤条件保证：
    # 1. 只有存在 official_obj 的记录才会处理；
    # 2. 如果目标字段 icml_official_obj 已经存在，则不会覆盖。
    # 因此该操作可以重复执行。
    # ------------------------------------------------------------------
    rename_result = papers.update_many(
        {
            "official_obj": {"$exists": True},
            "icml_official_obj": {"$exists": False},
        },
        {
            "$rename": {
                "official_obj": "icml_official_obj"
            }
        }
    )

    print(
        "🔹 Schema v1 -> v2 field migration finished. "
        f"{rename_result.modified_count} documents renamed: "
        "official_obj -> icml_official_obj"
    )

    batch_size = 100
    count = 0

    with client.start_session() as session:
        cursor = papers.find(
            {},
            no_cursor_timeout=True,
            session=session
        ).batch_size(batch_size)

        try:
            for doc in cursor:
                update_dict = {}

                # 补齐当前 Schema 中缺失的顶层字段
                for key, val in DEFAULT_PAPER_FIELDS.items():
                    if key not in doc:
                        update_dict[key] = val

                # 更新 Schema 版本号
                doc_version = doc.get("_schema_version", 0)

                if doc_version < CURRENT_SCHEMA_VERSION:
                    update_dict["_schema_version"] = CURRENT_SCHEMA_VERSION

                if update_dict:
                    papers.update_one(
                        {"_id": doc["_id"]},
                        {"$set": update_dict},
                        session=session
                    )
                    count += 1
        finally:
            cursor.close()

    print(
        f"🔹 Schema migration finished. "
        f"{count} documents upgraded to v{CURRENT_SCHEMA_VERSION}"
    )


# # 修改了 session 的 schema migration 方法
# def migrate_schema():
#     """
#     遍历整个 papers 集合，将缺失字段补全，升级 _schema_version
#     仅手动/定期执行
#     """

#     client = MongoDBClient._client

#     if client is None:
#         client = MongoDBClient.get_collection().database.client

#     papers = MongoDBClient.get_collection()

#     batch_size = 100
#     count = 0

#     with client.start_session() as session:
#         cursor = papers.find(
#             {},
#             no_cursor_timeout=True,
#             session = session
#         ).batch_size(batch_size)

#         for doc in cursor:
#             update_dict = {}

#             for key, val in DEFAULT_PAPER_FIELDS.items():
#                 if key not in doc:
#                     update_dict[key] = val

#             doc_version = doc.get("_schema_version", 0)
#             if doc_version < CURRENT_SCHEMA_VERSION:
#                 update_dict["_schema_version"] = CURRENT_SCHEMA_VERSION

#             if update_dict:
#                 papers.update_one(
#                     {"_id": doc["_id"]},
#                     {"$set": update_dict},
#                     session = session
#                 )
#                 count += 1

#     print(f"🔹 Schema migration finished. {count} documents upgraded to v{CURRENT_SCHEMA_VERSION}")
