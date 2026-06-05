"""
通用工具与基础设施（从 openreview_scraper.py 原样移植）。

包含：限流器 Throttle、带退避重试的 requests.Session、时间/文本规范化、
JsonCache 磁盘缓存、版本无关的 OpenReview 字段访问 cval，以及瞬时错误判定。
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import sys
import threading
import time
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence

# --------------------------------------------------------------------------- #
# 硬依赖：requests（随 openreview-py 一起安装）
# --------------------------------------------------------------------------- #
try:
    import requests
    from requests.adapters import HTTPAdapter
    try:
        from urllib3.util.retry import Retry
    except Exception:  # pragma: no cover
        from requests.packages.urllib3.util.retry import Retry  # type: ignore
except Exception as exc:  # pragma: no cover
    print("FATAL: 'requests' is required (it ships with openreview-py): %s" % exc,
          file=sys.stderr)
    raise

try:
    import openreview
except Exception as exc:  # pragma: no cover
    print("FATAL: 'openreview-py' is required. Install with: pip install openreview-py\n%s"
          % exc, file=sys.stderr)
    raise


log = logging.getLogger("orscrape")


# =========================================================================== #
# Small utilities
# =========================================================================== #
def setup_logging(verbosity: int) -> None:
    level = logging.WARNING if verbosity <= 0 else logging.INFO if verbosity == 1 else logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    # keep noisy libraries quiet unless -vv
    if verbosity < 2:
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("openreview").setLevel(logging.WARNING)


class Throttle:
    """Enforce a minimum wall-clock interval between successive calls (thread-safe)."""

    def __init__(self, min_interval: float):
        self.min_interval = max(0.0, float(min_interval))
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
            self._last = time.monotonic()


def build_session(user_agent: str) -> "requests.Session":
    """A requests Session that retries on connection errors and 429/5xx with backoff."""
    s = requests.Session()
    retry = Retry(
        total=6,
        connect=6,
        read=6,
        status=6,
        backoff_factor=1.5,                       # 0,1.5,3,6,12,24s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=16)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": user_agent})
    return s


def ms_to_dt(ms: Optional[int]) -> Optional[_dt.datetime]:
    if not ms:
        return None
    try:
        return _dt.datetime.fromtimestamp(int(ms) / 1000.0, tz=_dt.timezone.utc)
    except Exception:
        return None


def ms_to_yyyymm(ms: Optional[int]) -> Optional[str]:
    d = ms_to_dt(ms)
    return d.strftime("%Y%m") if d else None


def dt_to_dot(d: _dt.date) -> str:
    return d.strftime("%Y.%m.%d")


def slugify(text: str, max_len: int = 80) -> str:
    """Filesystem- and Obsidian-safe slug. Keeps unicode letters, collapses spaces."""
    if not text:
        return "untitled"
    text = unicodedata.normalize("NFKC", text)
    # drop characters illegal on common filesystems / Obsidian
    text = re.sub(r'[\\/:*?"<>|#\^\[\]]+', " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .-_")
    if len(text) > max_len:
        text = text[:max_len].rstrip(" .-_")
    return text or "untitled"


def keyword_to_tag(kw: str) -> str:
    """Turn a free-text keyword into a compact tag token (no spaces)."""
    kw = unicodedata.normalize("NFKC", str(kw)).strip().lower()
    kw = re.sub(r"[^\w一-鿿\- ]+", "", kw)
    kw = re.sub(r"\s+", "-", kw).strip("-")
    return kw


# the many Unicode dash/hyphen/minus variants (‐ ‑ ‒ – — ― −) — map them to ASCII
# '-' BEFORE the ascii-ignore step below, otherwise `encode("ascii","ignore")` would
# silently DROP an en-dash and glue tokens ("Long–Range" -> "longrange", one token)
# while indexes store "Long-Range" -> "long range" (two tokens), tanking similarity.
_DASH_TRANS = {ord(c): "-" for c in "‐‑‒–—―−"}


def norm_title(t: str) -> str:
    """Aggressively normalise a title for fuzzy matching."""
    t = (t or "").translate(_DASH_TRANS)
    t = unicodedata.normalize("NFKD", t)
    t = t.encode("ascii", "ignore").decode("ascii")
    t = t.lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def title_similarity(a: str, b: str) -> float:
    """Token Jaccard on normalised titles — cheap, dependency-free."""
    na, nb = norm_title(a), norm_title(b)
    if not na or not nb:
        return 0.0
    # exact, or equal once spaces are removed — handles digit/LaTeX/hyphen spacing
    # differences like "Diffusion2" vs "Diffusion 2" or "Long-Range" vs "Long Range".
    if na == nb or na.replace(" ", "") == nb.replace(" ", ""):
        return 1.0
    sa, sb = set(na.split()), set(nb.split())
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def chunked(seq: Sequence[Any], n: int) -> Iterable[List[Any]]:
    for i in range(0, len(seq), n):
        yield list(seq[i:i + n])


_REPO_RE = re.compile(
    r'https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org)/'
    r'[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+', re.IGNORECASE)


def extract_repo_url(*texts: Optional[str]) -> Optional[str]:
    """Pull the first plausible code-repo URL out of free text (abstract/TLDR)."""
    for t in texts:
        if not t:
            continue
        m = _REPO_RE.search(t)
        if m:
            url = m.group(0).rstrip('.,;:)?\'">]')
            # ignore obvious non-repo paths (org/profile pages, issues, etc.)
            tail = url.split("github.com/")[-1].split("/") if "github.com" in url.lower() else []
            if tail and tail[-1].lower() in ("issues", "blob", "tree", "wiki"):
                continue
            return url
    return None


def _aff_key(name: str) -> str:
    """Normalise an affiliation string for dedup ('&' vs 'and', case, punctuation)."""
    s = str(name).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class TransientLookupError(Exception):
    """Raised by enrichment clients for retryable failures (network/429/empty/parse)
    so the caller can avoid permanently negative-caching a paper."""


class _EmptyPageError(Exception):
    """Internal: an empty notes page arrived before the reported total was reached.
    Retried by _retry_call; if it persists, pagination ends gracefully (partial)."""


def _is_transient_error(exc: Exception) -> bool:
    """True for rate-limit / connection / proxy errors that should be RETRIED
    (and therefore NOT negative-cached); False for authoritative 'not found'
    responses and deterministic errors."""
    if isinstance(exc, (requests.exceptions.ConnectionError,        # incl. SSLError
                        requests.exceptions.ChunkedEncodingError,
                        requests.exceptions.Timeout)):
        return True
    if isinstance(exc, openreview.OpenReviewException):
        info = exc.args[0] if exc.args else None
        status = info.get("status") if isinstance(info, dict) else None
        if status in (429, 500, 502, 503, 504):
            return True
        text = str(exc)
        return "429" in text or "Too Many Requests" in text
    return False


class JsonCache:
    """A tiny persistent key->json cache (single file, periodic flush)."""

    def __init__(self, path: str):
        self.path = path
        self.data: Dict[str, Any] = {}
        self._dirty = 0
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    self.data = json.load(fh)
            except Exception as exc:
                log.warning("could not read cache %s: %s", path, exc)
                self.data = {}

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.data

    def set(self, key: str, value: Any, flush_every: int = 50) -> None:
        self.data[key] = value
        self._dirty += 1
        if self._dirty >= flush_every:
            self.flush()

    def flush(self) -> None:
        if not self.path:
            return
        self._dirty = 0
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=0)
            os.replace(tmp, self.path)
        except Exception as exc:
            log.warning("could not write cache %s: %s", self.path, exc)


# =========================================================================== #
# Version-agnostic OpenReview note access
# =========================================================================== #
def cval(note, *field_names: str, default=None):
    """Return a content field, transparently handling v2 ({'value': x}) and v1 (x).

    Multiple names allow tolerating key variants, e.g. cval(n, 'TLDR', 'TL;DR').
    """
    content = getattr(note, "content", None) or {}
    for f in field_names:
        if f in content:
            v = content[f]
            if isinstance(v, dict) and "value" in v:
                return v["value"]
            return v
    return default
