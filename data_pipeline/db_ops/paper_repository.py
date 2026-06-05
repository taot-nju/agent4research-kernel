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
        else:
            # 不同源，更新字段
            edit_log = {
                "time": now_beijing_iso(),
                "op": f"update from {source}" + (f" @ {category}" if category else ""),
                "detail": "update paper metadata"
            }
            update_dict = {
                "$set": paper_data,
                "$addToSet": {"seen_in_sources": source},
                "$push": {"edit_logs": edit_log}
            }
            if category:
                update_dict["$addToSet"]["seen_in_categories"] = category

            papers.update_one({"_id": paper_data["_id"]}, update_dict)
            print(f"♻️ Updated paper from new source: {paper_data['_id']}")

    print("[red]One record processed!")

def _merge_cite_numbers(old_list, new_list):
    """合并带时间戳的引用快照列表（["<count>@<YYYY.MM.DD>", ...]）。

    - 同一天的快照用新值替换旧值；
    - 不同天的新快照追加到末尾；
    使重复运行幂等地累积引用历史，而不是覆盖或重复。
    """
    combined = list(old_list or [])
    for snap in (new_list or []):
        if not isinstance(snap, str):
            continue
        date = snap.split("@")[-1] if "@" in snap else None
        existing_dates = {s.split("@")[-1] for s in combined if isinstance(s, str) and "@" in s}
        if date is not None and date in existing_dates:
            combined = [s for s in combined
                        if not (isinstance(s, str) and s.split("@")[-1] == date)] + [snap]
        elif snap not in combined:
            combined.append(snap)
    return combined


def upsert_openreview_paper(paper_data: dict, venue: str):
    """upsert 一篇来自 OpenReview 的论文。

    与 arXiv 的 upsert_paper 相互独立，专门处理「跨源合并」：
    - 全新论文：直接插入；
    - 已存在论文（可能先来自 arXiv）：用 merge_missing_fields 只补全空缺/缺失字段
      （以点路径方式合并嵌套 dict，因此**不会**用空值覆盖已有的 arxiv_obj / base_urls）；
      并强制把 accepted_by 覆盖为会议名（会议优先于 arXiv），同时把 cite_numbers 以
      时间戳快照的方式幂等累积，最后 $addToSet 记录来源、$push 一条 edit_log。

    :param paper_data: 单篇论文的字典（来自 record_to_paper_data，已映射为 schema）
    :param venue: 会议来源，例如 "ICLR 2026"
    """
    papers = MongoDBClient.get_collection()

    # 浅拷贝，避免改动调用方的对象；剥离瞬时键与会与 $addToSet/$push 冲突的字段
    paper_data = dict(paper_data)
    paper_data.pop("_openreview_record", None)
    paper_data.pop("seen_in_categories", None)
    paper_data.pop("seen_in_sources", None)
    paper_data.pop("edit_logs", None)

    new_cites = paper_data.get("cite_numbers") or []

    doc = papers.find_one({"_id": paper_data["_id"]})

    if doc is None:
        # 全新论文
        edit_log = {
            "time": now_beijing_iso(),
            "op": f"insert from {venue}",
            "detail": "insert paper metadata (OpenReview)"
        }
        update_dict = {
            "$set": paper_data,
            "$setOnInsert": {"_schema_version": CURRENT_SCHEMA_VERSION},
            "$addToSet": {"seen_in_sources": venue},
            "$push": {"edit_logs": edit_log}
        }
        papers.update_one({"_id": paper_data["_id"]}, update_dict, upsert=True)
        print(f"✅ Inserted new paper (OpenReview): {paper_data['_id']}")
    else:
        # 已存在：只补全空缺字段（点路径），不覆盖已有的非空字段
        patch = merge_missing_fields(doc, paper_data)

        # accepted_by：会议覆盖 arXiv（即使旧值非空也要覆盖）
        if venue:
            patch["accepted_by"] = venue

        # cite_numbers：幂等累积时间戳快照（覆盖 merge_missing_fields 可能产生的版本）
        merged_cites = _merge_cite_numbers(doc.get("cite_numbers"), new_cites)
        if merged_cites != (doc.get("cite_numbers") or []):
            patch["cite_numbers"] = merged_cites
        else:
            patch.pop("cite_numbers", None)

        edit_log = {
            "time": now_beijing_iso(),
            "op": f"update from {venue}",
            "detail": (f"fields updated: {sorted(patch.keys())}" if patch
                       else "no richer info")
        }
        update_ops = {
            "$addToSet": {"seen_in_sources": venue},
            "$push": {"edit_logs": edit_log},
        }
        if patch:
            update_ops["$set"] = patch

        papers.update_one({"_id": paper_data["_id"]}, update_ops)
        if patch:
            print(f"🩹 Merged OpenReview paper: {paper_data['_id']} -> {sorted(patch.keys())}")
        else:
            print(f"♻️ OpenReview paper already up to date: {paper_data['_id']}")

    print("[red]One record processed!")


# 修改了 session 的 schema migration 方法
def migrate_schema():
    """
    遍历整个 papers 集合，将缺失字段补全，升级 _schema_version
    仅手动/定期执行
    """

    client = MongoDBClient._client

    if client is None:
        client = MongoDBClient.get_collection().database.client

    papers = MongoDBClient.get_collection()

    batch_size = 100
    count = 0

    with client.start_session() as session:
        cursor = papers.find(
            {},
            no_cursor_timeout=True,
            session = session
        ).batch_size(batch_size)

        for doc in cursor:
            update_dict = {}

            for key, val in DEFAULT_PAPER_FIELDS.items():
                if key not in doc:
                    update_dict[key] = val

            doc_version = doc.get("_schema_version", 0)
            if doc_version < CURRENT_SCHEMA_VERSION:                
                update_dict["_schema_version"] = CURRENT_SCHEMA_VERSION

            if update_dict:
                papers.update_one(
                    {"_id": doc["_id"]},
                    {"$set": update_dict},
                    session = session
                )
                count += 1

    print(f"🔹 Schema migration finished. {count} documents upgraded to v{CURRENT_SCHEMA_VERSION}")