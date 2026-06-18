"""
功能②编排：选论文 -> 下载 PDF -> GROBID -> 解析 TEI -> 写回 references。

- 幂等闸门：非 --force 时跳过 processing_status.references_extracted == True 的论文。
- 单篇 try/except：任何一篇出错（无 PDF / 扫描件 NO_BLOCKS / 网络）都不影响整批。
- body_sentences（体量大）落 cache/store/body_sentences/，不进 Mongo。
"""

import json
import os
import time

from tqdm import tqdm

from ai4research.data_pipeline.db_ops.paper_query import (
    find_papers_by_field_value,
    get_paper_by_id,
)
from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.field_processing_pipeline.configs.reference_config import (
    SENT_DIR,
    build_session,
    ensure_dirs,
)
from ai4research.field_processing_pipeline.db_ops.field_writer import update_paper_fields
from ai4research.field_processing_pipeline.extractors import grobid_client, tei_parser
from ai4research.field_processing_pipeline.extractors.grobid_client import GrobidError
from ai4research.field_processing_pipeline.extractors.pdf_provider import ensure_local_pdf


def _select_papers(paper_id, accepted_by, source, limit):
    if paper_id:
        p = get_paper_by_id(paper_id)
        return [p] if p else []
    if accepted_by:
        return find_papers_by_field_value("accepted_by", accepted_by, limit=limit or 20)
    if source:
        return find_papers_by_field_value("seen_in_sources", source, limit=limit or 20)
    papers = MongoDBClient.get_collection()
    cursor = papers.find({})
    if limit:
        cursor = cursor.limit(limit)
    return list(cursor)


def extract_references_for_papers(
    paper_id=None,
    accepted_by=None,
    source=None,
    limit=20,
    window_n=2,  # 透传/预留；窗口在读时现算，不影响落库
    force=False,
    sleep=0.0,
):
    ensure_dirs()
    session = build_session()

    if not grobid_client.is_alive(session):
        print(
            "❌ GROBID is not reachable. Start it first, e.g.:\n"
            "   docker run --rm --init -p 8070:8070 lfoppiano/grobid:0.8.0\n"
            "   (or set GROBID_URL to a reachable GROBID service)"
        )
        return

    papers = _select_papers(paper_id, accepted_by, source, limit)
    print(f"📄 Selected {len(papers)} paper(s).")

    stats = {"processed": 0, "skipped": 0, "failed": 0}
    pbar = tqdm(papers, desc="Extracting references", unit="paper")
    for paper in pbar:
        if not paper:
            continue
        pid = paper["_id"]
        ps = (paper.get("processing_status") or {})
        if ps.get("references_extracted") and not force:
            stats["skipped"] += 1
            continue

        try:
            pdf_path, st = ensure_local_pdf(paper, session)
            if st in ("no_url", "http_error", "not_pdf"):
                print(f"⏭️  {pid}: pdf {st}")
                stats["skipped"] += 1
                continue

            tei = grobid_client.process_fulltext(
                pdf_path=pdf_path, paper_id=pid, session=session, force=force
            )
            parsed = tei_parser.parse_tei(tei, pid)
            summary = tei_parser.summarize(parsed)

            # body_sentences 落 cache（不入 Mongo）
            with open(os.path.join(SENT_DIR, f"{pid}.json"), "w", encoding="utf-8") as f:
                json.dump(parsed["body_sentences"], f, ensure_ascii=False)

            detail = (
                f"{summary['n_refs']} refs, {summary['n_cited_refs']} cited, "
                f"{summary['n_occurrences']} occurrences, "
                f"{summary['n_unmatched']} unmatched"
            )
            update_paper_fields(
                pid,
                {"references": parsed["references"]},
                op="extract references+contexts via grobid",
                detail=detail,
                status_flag="references_extracted",
            )
            stats["processed"] += 1
            pbar.set_postfix_str(detail)
        except GrobidError as e:
            print(f"⚠️  {pid}: GROBID error -> {e}")
            stats["failed"] += 1
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  {pid}: unexpected -> {type(e).__name__}: {e}")
            stats["failed"] += 1

        if sleep:
            time.sleep(sleep)

    pbar.close()
    print(
        f"🎉 Done. processed={stats['processed']} "
        f"skipped={stats['skipped']} failed={stats['failed']}"
    )
