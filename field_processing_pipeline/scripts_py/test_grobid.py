"""
Phase-0 spike：在动手做 Function② 之前，先验证 GROBID 在"我们自己的语料"上效果如何。

它会：
  1. 从 MongoDB 选 2-3 篇 base_urls 里有 PDF 链接的论文（优先 ACL / 官网的 born-digital PDF）；
  2. 下载 PDF（带重试，不写库），存到 cache/store/pdfs/；
  3. 调 GROBID processFulltextDocument，TEI 存到 cache/store/grobid_tei/（可用在线 XML viewer 查看）；
  4. 从 TEI 计算质量指标，按"通过标准"给出 PASS/FAIL 判断。

只读 Mongo，不写任何论文字段；遇到坏 PDF 不崩，记为失败行。

运行（GROBID 在 localhost:8070 时）：
  PYTHONPATH=~/ai4research_ws ~/ai4research_ws/.venv/bin/python \
    -m ai4research.field_processing_pipeline.scripts_py.test_grobid --limit 3

  # 指向托管 GROBID（无需本地 docker）：
  GROBID_URL=https://kermitt2-grobid.hf.space python -m ai4research....test_grobid
"""

import argparse

from lxml import etree

from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.field_processing_pipeline.configs.reference_config import (
    PDF_DIR,
    PDF_URL_PRIORITY,
    build_session,
    download_pdf_bytes,
    ensure_dirs,
)
from ai4research.field_processing_pipeline.extractors import grobid_client
from ai4research.field_processing_pipeline.extractors.grobid_client import GrobidError

import os

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def pick_pdf_url(paper: dict) -> str:
    base = paper.get("base_urls") or {}
    for key in PDF_URL_PRIORITY:
        url = base.get(key)
        if url:
            return url
    return ""


def select_candidate_papers(limit: int):
    """挑 base_urls 里有任一 *_pdf_url 的论文，优先 ACL / 官网。"""
    papers = MongoDBClient.get_collection()
    or_clauses = [{f"base_urls.{k}": {"$nin": ["", None]}} for k in PDF_URL_PRIORITY]
    cursor = papers.find(
        {"$or": or_clauses},
        {"_id": 1, "title": 1, "base_urls": 1, "accepted_by": 1},
    )
    docs = list(cursor)

    # 优先级：ACL / official 的 PDF 解析最稳。
    def rank(p):
        base = p.get("base_urls") or {}
        for i, k in enumerate(PDF_URL_PRIORITY):
            if base.get(k):
                return i
        return len(PDF_URL_PRIORITY)

    docs.sort(key=rank)
    return docs[:limit]


def analyze_tei(tei: str) -> dict:
    """从 TEI 计算质量指标。"""
    root = etree.fromstring(tei.encode("utf-8"))

    biblstructs = root.findall(".//tei:listBibl/tei:biblStruct", TEI_NS)
    bib_ids = set()
    titled = 0
    for b in biblstructs:
        bid = b.get(XML_ID)
        if bid:
            bib_ids.add(bid)
        title_el = b.find(".//tei:title", TEI_NS)
        if title_el is not None and (title_el.text or "").strip():
            titled += 1

    sentences = root.findall(".//tei:body//tei:p/tei:s", TEI_NS)

    bibr = root.findall(".//tei:body//tei:ref[@type='bibr']", TEI_NS)
    resolvable = 0
    for r in bibr:
        target = (r.get("target") or "").lstrip("#")
        if target and target in bib_ids:
            resolvable += 1

    coords_present = any(s.get("coords") for s in sentences) or any(
        r.get("coords") for r in bibr
    )

    n_refs = len(biblstructs)
    n_bibr = len(bibr)
    return {
        "n_biblstruct": n_refs,
        "title_rate": (titled / n_refs) if n_refs else 0.0,
        "n_sentences": len(sentences),
        "n_bibr": n_bibr,
        "resolvable_target_rate": (resolvable / n_bibr) if n_bibr else 0.0,
        "coords_present": coords_present,
    }


def judge(m: dict) -> bool:
    """通过标准（见 PLAN）。"""
    return (
        m["n_biblstruct"] >= 20
        and m["title_rate"] >= 0.80
        and m["n_sentences"] > 0
        and m["resolvable_target_rate"] >= 0.70
    )


def main():
    parser = argparse.ArgumentParser(description="GROBID spike: 验证抽取质量")
    parser.add_argument("--limit", type=int, default=3, help="测试论文数")
    args = parser.parse_args()

    ensure_dirs()
    if MongoDBClient.ping():
        print("✅ MongoDB connected successfully.")

    session = build_session()
    print(f"🔎 GROBID isalive: {grobid_client.is_alive(session)}")

    candidates = select_candidate_papers(args.limit)
    if not candidates:
        print("⚠️  No papers with a base_urls.*_pdf_url found. Crawl some first.")
        return
    print(f"📄 Selected {len(candidates)} candidate paper(s).\n")

    results = []
    for idx, paper in enumerate(candidates, start=1):
        pid = paper["_id"]
        title = (paper.get("title") or "")[:70]
        url = pick_pdf_url(paper)
        print(f"[{idx}/{len(candidates)}] {title}\n    _id={pid}\n    pdf={url}")

        try:
            pdf_bytes, status = download_pdf_bytes(url, session)
            if status != "ok":
                print(f"    ❌ download: {status}\n")
                results.append((title, status, None))
                continue
            # 存 PDF 供复用/检查
            pdf_path = os.path.join(PDF_DIR, f"{pid}.pdf")
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)

            tei = grobid_client.process_fulltext(
                pdf_bytes=pdf_bytes, paper_id=pid, session=session, force=True
            )
            m = analyze_tei(tei)
            ok = judge(m)
            results.append((title, "ok", (m, ok)))
            print(
                f"    refs={m['n_biblstruct']}  title_rate={m['title_rate']:.2f}  "
                f"sentences={m['n_sentences']}  in-text-bibr={m['n_bibr']}  "
                f"resolvable_target={m['resolvable_target_rate']:.2f}  "
                f"coords={m['coords_present']}"
            )
            print(f"    -> {'✅ PASS' if ok else '⚠️  BELOW THRESHOLD'}\n")
        except GrobidError as e:
            print(f"    ❌ GROBID error: {e}\n")
            results.append((title, "grobid_error", None))
        except Exception as e:  # noqa: BLE001
            print(f"    ❌ unexpected: {e}\n")
            results.append((title, "error", None))

    # 汇总
    passed = [r for r in results if r[2] and r[2][1]]
    print("=" * 70)
    print(
        f"SUMMARY: {len(results)} processed, "
        f"{len(passed)} passed all thresholds. "
        f"TEI saved under cache/store/grobid_tei/ for inspection."
    )
    if passed:
        print("✅ GROBID is good enough on our corpus — proceed to Phase 1 integration.")
    else:
        print(
            "⚠️  No paper passed all thresholds. Inspect the TEI, try the full image "
            "(grobid/grobid:<ver>-full), or check whether PDFs are scanned."
        )


if __name__ == "__main__":
    main()
