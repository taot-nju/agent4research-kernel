"""
功能② (references + 引用上下文) 的配置项与共享 HTTP 工具。

集中放置：GROBID 服务地址 / 调用参数、本地缓存目录、PDF 链接优先级、
窗口默认值、参考文献章节识别规则，以及一个带重试的 requests.Session
和一个"只下载、不写库"的 PDF 抓取函数（spike 与 pdf_provider 共用）。
"""

import os
import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ---------------------------------------------------------------------------
# GROBID 服务
# ---------------------------------------------------------------------------
# 可用环境变量 GROBID_URL 覆盖（例如指向远程/HF 部署）。
GROBID_URL = os.environ.get("GROBID_URL", "http://localhost:8070").rstrip("/")
GROBID_FULLTEXT_API = f"{GROBID_URL}/api/processFulltextDocument"
GROBID_ISALIVE_API = f"{GROBID_URL}/api/isalive"

# processFulltextDocument 的表单参数（与 spike 验证过的口径保持一致）：
#   segmentSentences=1     -> 正文 <p> 内切出 <s> 句子元素（窗口的基础）
#   teiCoordinates=...     -> 给 ref/biblStruct/s 加 PDF 坐标
#   includeRawCitations=1  -> 保留每条参考文献的原始字符串
#   consolidateCitations=0 -> 离线，不外呼 CrossRef（快、稳）
#   consolidateHeader=0    -> 同上
GROBID_FORM_PARAMS = {
    "segmentSentences": "1",
    "teiCoordinates": "ref,biblStruct,s",
    "includeRawCitations": "1",
    "consolidateCitations": "0",
    "consolidateHeader": "0",
}

# GROBID 处理一篇全文可能较慢，给足超时。
GROBID_TIMEOUT = int(os.environ.get("GROBID_TIMEOUT", "300"))
HTTP_TIMEOUT = int(os.environ.get("FP_HTTP_TIMEOUT", "60"))


# ---------------------------------------------------------------------------
# 本地缓存目录（全部 .gitignore）
# ---------------------------------------------------------------------------
_MODULE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_STORE_DIR = os.path.join(_MODULE_ROOT, "cache", "store")
PDF_DIR = os.path.join(CACHE_STORE_DIR, "pdfs")
TEI_DIR = os.path.join(CACHE_STORE_DIR, "grobid_tei")
SENT_DIR = os.path.join(CACHE_STORE_DIR, "body_sentences")


def ensure_dirs():
    """创建所有缓存子目录（幂等）。"""
    for d in (PDF_DIR, TEI_DIR, SENT_DIR):
        os.makedirs(d, exist_ok=True)


# ---------------------------------------------------------------------------
# PDF 链接选取 & 正文切分
# ---------------------------------------------------------------------------
# 从 base_urls 里挑 PDF 链接的优先级：ACL/官网的 born-digital PDF 解析质量最好。
PDF_URL_PRIORITY = [
    "acl_anthology_pdf_url",
    "official_pdf_url",
    "arxiv_pdf_url",
    "pdf_url",
    "openreview_pdf_url",
]

# 窗口默认参数（前 N 句 + 本句 + 后 N 句）。
WINDOW_N_DEFAULT = 2

# 识别"参考文献/致谢"等正文之后的章节：这些章节内的句子不进入正文句子流，
# 避免窗口溢进参考文献区。匹配 <div><head> 文本（允许前导编号）。
REFERENCES_HEAD_RE = re.compile(
    r"^\s*[0-9.\s]*(references?|bibliography|acknowledg|appendix)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# HTTP：带重试的 Session（沿用 aaai_official_crawler 的策略）
# ---------------------------------------------------------------------------
_USER_AGENT = (
    "Mozilla/5.0 (compatible; ai4research/1.0; "
    "+https://github.com/taot-nju/agent4research-kernel)"
)


def build_session() -> requests.Session:
    """构造一个带指数退避重试的 requests.Session（GET + POST 均重试）。"""
    session = requests.Session()
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": _USER_AGENT})
    return session


def _looks_like_pdf(content: bytes, content_type: str) -> bool:
    if "application/pdf" in (content_type or "").lower():
        return True
    return content[:5].startswith(b"%PDF")


def download_pdf_bytes(url: str, session: requests.Session = None):
    """
    下载一个 PDF，仅返回字节，不写任何数据库。

    返回 (pdf_bytes, status)：
        status ∈ {"ok", "no_url", "http_error", "not_pdf"}
        失败时 pdf_bytes 为 None。
    """
    if not url:
        return None, "no_url"
    sess = session or build_session()
    try:
        resp = sess.get(url, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001 - 任何网络错误都温和降级
        print(f"⚠️  PDF download failed: {url} -> {e}")
        return None, "http_error"

    if not _looks_like_pdf(resp.content, resp.headers.get("Content-Type", "")):
        print(f"⚠️  Not a PDF (got {resp.headers.get('Content-Type')}): {url}")
        return None, "not_pdf"

    return resp.content, "ok"
