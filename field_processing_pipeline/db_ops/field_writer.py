"""
富化层专属写库函数。

与 data_pipeline 的 upsert_paper 不同：upsert_paper 只补空字段、永不覆盖；
而功能②/① 需要把 references / cite_numbers 等字段刷新覆盖。所以这里用一个
按 _id 直接 $set + $push edit_logs 的写法（upsert=False，不新建论文）。
"""

from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.data_pipeline.utils.time_utils import now_beijing_iso


def update_paper_fields(
    paper_id: str,
    set_fields: dict,
    op: str,
    detail: str = "",
    status_flag: str = None,
    require_exists: bool = True,
) -> bool:
    """
    覆盖式更新指定字段（区别于 upsert_paper 的"只补空"）。

    :param paper_id:   论文 _id
    :param set_fields: 要 $set 的字段，支持点路径，例如 {"references": [...]} / {"local_pdf_path": "..."}
    :param op:         edit_logs 的 op 标签
    :param detail:     edit_logs 的 detail
    :param status_flag: 若给定（如 "references_extracted" / "pdf_downloaded"），
                        会一并 $set processing_status.<flag> = True
    :param require_exists: True 时若论文不存在则告警并返回 False（富化不新建论文）
    :return: 是否成功修改
    """
    papers = MongoDBClient.get_collection()

    doc = papers.find_one({"_id": paper_id}, {"_id": 1})
    if doc is None:
        if require_exists:
            print(f"⚠️  update_paper_fields: paper not found, skip: {paper_id}")
            return False

    set_doc = dict(set_fields)
    if status_flag:
        set_doc[f"processing_status.{status_flag}"] = True

    edit_log = {
        "time": now_beijing_iso(),
        "op": op,
        "detail": detail,
    }

    result = papers.update_one(
        {"_id": paper_id},
        {"$set": set_doc, "$push": {"edit_logs": edit_log}},
        upsert=False,
    )
    return result.modified_count > 0 or result.matched_count > 0
