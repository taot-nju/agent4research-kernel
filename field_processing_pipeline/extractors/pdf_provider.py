"""
PDF 获取：功能②的硬前置。从 base_urls 里挑一个 PDF 链接下载到本地，
回填 local_pdf_path + processing_status.pdf_downloaded。幂等。

（当前仓库的采集层只写 base_urls.*_pdf_url，从不下载 PDF；这里补上这一环。）
"""

import os

from ai4research.field_processing_pipeline.configs.reference_config import (
    PDF_DIR,
    PDF_URL_PRIORITY,
    build_session,
    download_pdf_bytes,
    ensure_dirs,
)
from ai4research.field_processing_pipeline.db_ops.field_writer import update_paper_fields


def pick_pdf_url(paper: dict) -> str:
    """按优先级从 base_urls 选一个 PDF 链接（ACL/官网优先，解析质量最好）。"""
    base = paper.get("base_urls") or {}
    for key in PDF_URL_PRIORITY:
        url = base.get(key)
        if url:
            return url
    return ""


def _sync_pdf_status(paper: dict, path: str) -> None:
    """文件已在磁盘但 Mongo 记录可能滞后（spike/中断的运行直接落盘）——对齐回填。
    已一致则跳过，不做多余写库。"""
    ps = paper.get("processing_status") or {}
    if paper.get("local_pdf_path") == path and ps.get("pdf_downloaded") is True:
        return
    update_paper_fields(
        paper["_id"],
        {"local_pdf_path": path},
        op="sync pdf path",
        detail="file already on disk; backfilled local_pdf_path/pdf_downloaded",
        status_flag="pdf_downloaded",
    )


def ensure_local_pdf(paper: dict, session=None):
    """
    保证 paper 有可用的本地 PDF。

    返回 (local_pdf_path | None, status):
        status ∈ {"ok", "already", "no_url", "http_error", "not_pdf"}
    """
    ensure_dirs()
    pid = paper["_id"]
    pdf_path = os.path.join(PDF_DIR, f"{pid}.pdf")

    # 幂等：已下载且文件在。注意文件可能由 spike(test_grobid) 或上次中断的运行
    # 直接落盘，那种情况下 Mongo 的 local_pdf_path/pdf_downloaded 还没回填——
    # 这里补写，保证磁盘与库一致（否则查询"哪些论文有 PDF"会漏报）。
    existing = paper.get("local_pdf_path")
    if existing and os.path.exists(existing):
        _sync_pdf_status(paper, existing)
        return existing, "already"
    if os.path.exists(pdf_path):
        _sync_pdf_status(paper, pdf_path)
        return pdf_path, "already"

    url = pick_pdf_url(paper)
    if not url:
        return None, "no_url"

    sess = session or build_session()
    pdf_bytes, status = download_pdf_bytes(url, sess)
    if status != "ok":
        return None, status

    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    update_paper_fields(
        pid,
        {"local_pdf_path": pdf_path},
        op="download pdf",
        detail=url,
        status_flag="pdf_downloaded",
    )
    return pdf_path, "ok"
