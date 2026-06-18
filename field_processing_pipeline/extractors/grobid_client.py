"""
GROBID 客户端：把一篇 PDF 交给 GROBID 的 processFulltextDocument，拿回 TEI XML。

- 不解析 TEI（解析在 tei_parser）；这里只负责"调用 + 缓存 + 错误归一化"。
- 服务地址由 configs.reference_config.GROBID_URL 决定（可用环境变量覆盖，
  既可指向本地 docker，也可指向托管的 HF Space）。
"""

import os

from ai4research.field_processing_pipeline.configs.reference_config import (
    GROBID_FORM_PARAMS,
    GROBID_FULLTEXT_API,
    GROBID_ISALIVE_API,
    GROBID_TIMEOUT,
    TEI_DIR,
    build_session,
    ensure_dirs,
)


class GrobidError(Exception):
    """GROBID 处理失败（服务不可用 / NO_BLOCKS / 空响应等），供 pipeline 优雅跳过。"""


def is_alive(session=None) -> bool:
    """GET /api/isalive，返回 True/False（不抛异常）。"""
    sess = session or build_session()
    try:
        resp = sess.get(GROBID_ISALIVE_API, timeout=30)
        return resp.status_code == 200 and resp.text.strip().lower() == "true"
    except Exception:  # noqa: BLE001
        return False


# GROBID 在出错时会返回纯文本错误码，例如 [NO_BLOCKS] / [GENERAL] / [TIMEOUT]。
_ERROR_MARKERS = ("[NO_BLOCKS]", "[GENERAL]", "[TIMEOUT]", "[TOO_MANY_BLOCKS]")


def process_fulltext(
    pdf_path: str = None,
    pdf_bytes: bytes = None,
    filename: str = "paper.pdf",
    paper_id: str = None,
    session=None,
    use_cache: bool = True,
    force: bool = False,
) -> str:
    """
    把 PDF 交给 GROBID，返回 TEI XML 字符串。

    入参二选一：pdf_path（磁盘路径）或 pdf_bytes（字节）。
    若 paper_id 给定且 use_cache=True：
        - 非 force 且缓存存在 -> 直接读 cache/store/grobid_tei/<paper_id>.tei.xml
        - 调用成功后写入该缓存（兼作重解析缓存，避免重复 POST）

    失败时抛 GrobidError（服务不可用 / HTTP 非 200 / 空响应 / 错误码）。
    """
    ensure_dirs()
    tei_cache_path = (
        os.path.join(TEI_DIR, f"{paper_id}.tei.xml") if (paper_id and use_cache) else None
    )

    if tei_cache_path and not force and os.path.exists(tei_cache_path):
        with open(tei_cache_path, "r", encoding="utf-8") as f:
            return f.read()

    if pdf_bytes is None:
        if not pdf_path or not os.path.exists(pdf_path):
            raise GrobidError(f"PDF not found: {pdf_path}")
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        filename = os.path.basename(pdf_path)

    sess = session or build_session()
    if not is_alive(sess):
        raise GrobidError(
            f"GROBID not alive at {GROBID_ISALIVE_API} "
            f"(start docker: `docker run --rm --init -p 8070:8070 <grobid-image>`, "
            f"or set GROBID_URL to a hosted endpoint)"
        )

    try:
        resp = sess.post(
            GROBID_FULLTEXT_API,
            files={"input": (filename, pdf_bytes, "application/pdf")},
            data=GROBID_FORM_PARAMS,
            timeout=GROBID_TIMEOUT,
        )
    except Exception as e:  # noqa: BLE001
        raise GrobidError(f"GROBID request failed: {e}") from e

    if resp.status_code != 200:
        raise GrobidError(
            f"GROBID HTTP {resp.status_code}: {resp.text[:200]!r}"
        )

    tei = resp.text or ""
    stripped = tei.lstrip()
    if not stripped or any(stripped.startswith(m) for m in _ERROR_MARKERS):
        raise GrobidError(f"GROBID returned error/empty body: {stripped[:120]!r}")

    if tei_cache_path:
        with open(tei_cache_path, "w", encoding="utf-8") as f:
            f.write(tei)

    return tei
