"""
外部富化客户端（从 openreview_scraper.py 原样移植）。

- ArxivClient            : 通过 export.arxiv.org 的 Atom feed 按标题匹配 arXiv id/url 与版本日期。
- SemanticScholarClient  : graph v1 的 batch / title-match / citations。
- PapersWithCodeClient   : paperswithcode.com api v1，按 arXiv id 找官方 GitHub。
- OpenAlexClient         : api.openalex.org，按引用文献发表日期重建多时间戳引用序列。
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Sequence

import requests

from ai4research.data_pipeline.crawlers.openreview.helpers import (
    JsonCache,
    Throttle,
    TransientLookupError,
    chunked,
    log,
    norm_title,
    title_similarity,
)


# =========================================================================== #
# arXiv enrichment
# =========================================================================== #
class ArxivClient:
    ENDPOINT = "https://export.arxiv.org/api/query"
    NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

    def __init__(self, session: requests.Session, throttle: Throttle, cache: JsonCache,
                 min_similarity: float = 0.9):
        self.session = session
        self.throttle = throttle
        self.cache = cache
        self.min_similarity = min_similarity

    def lookup(self, title: str, authors: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        if not title:
            return None
        ck = "arxiv::" + norm_title(title)
        if ck in self.cache:
            return self.cache.get(ck) or None
        try:
            result = self._query(title)          # None == definitive miss
        except TransientLookupError as exc:
            log.debug("arxiv transient for %r: %s; not caching", title[:50], exc)
            return None                          # leave key absent -> retry next run
        self.cache.set(ck, result or {})         # only cache a definitive hit/miss
        return result or None

    def _query(self, title: str) -> Optional[Dict[str, Any]]:
        q = 'ti:"%s"' % re.sub(r'["\\]', " ", title)
        params = {"search_query": q, "start": 0, "max_results": 5}
        self.throttle.wait()
        try:
            r = self.session.get(self.ENDPOINT, params=params, timeout=40)
        except Exception as exc:
            raise TransientLookupError("request: %s" % exc)
        if r.status_code != 200 or not r.content:
            raise TransientLookupError("http %s / empty" % r.status_code)
        try:
            root = ET.fromstring(r.content)
        except Exception as exc:
            raise TransientLookupError("xml parse: %s" % exc)
        best = None
        best_score = 0.0
        for e in root.findall("a:entry", self.NS):
            etitle = e.findtext("a:title", default="", namespaces=self.NS)
            etitle = " ".join((etitle or "").split())
            score = title_similarity(title, etitle)
            if score > best_score:
                best_score = score
                best = e
        if best is None or best_score < self.min_similarity:
            log.debug("arxiv: no confident match for %r (best=%.2f)", title[:50], best_score)
            return None
        raw_id = best.findtext("a:id", default="", namespaces=self.NS) or ""
        m = re.search(r"arxiv\.org/abs/([^\s]+)$", raw_id)
        arxiv_id = m.group(1) if m else raw_id.rsplit("/", 1)[-1]
        arxiv_id_nov = re.sub(r"v\d+$", "", arxiv_id)
        published = best.findtext("a:published", default="", namespaces=self.NS)
        updated = best.findtext("a:updated", default="", namespaces=self.NS)
        def ym(s):
            try:
                return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%Y%m")
            except Exception:
                return None
        return {
            "arxiv_id": arxiv_id_nov,
            "abs_url": "https://arxiv.org/abs/%s" % arxiv_id_nov,
            "first_ym": ym(published),
            "last_ym": ym(updated),
            "matched_title": " ".join(best.findtext("a:title", default="",
                                                     namespaces=self.NS).split()),
            "score": round(best_score, 3),
        }


# =========================================================================== #
# Semantic Scholar enrichment (citations + DOI)
# =========================================================================== #
class SemanticScholarClient:
    BATCH = "https://api.semanticscholar.org/graph/v1/paper/batch"
    MATCH = "https://api.semanticscholar.org/graph/v1/paper/search/match"
    CITES = "https://api.semanticscholar.org/graph/v1/paper/%s/citations"
    FIELDS = "title,citationCount,externalIds,url,year"

    def __init__(self, session: requests.Session, throttle: Throttle, cache: JsonCache,
                 api_key: Optional[str]):
        self.session = session
        self.throttle = throttle
        self.cache = cache
        self.api_key = api_key

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["x-api-key"] = self.api_key
        return h

    def batch_by_arxiv(self, arxiv_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        """Return {arxiv_id: record} for all that S2 knows about."""
        out: Dict[str, Dict[str, Any]] = {}
        todo = []
        for aid in dict.fromkeys(arxiv_ids):
            if not aid:
                continue
            ck = "s2arxiv::" + aid
            if ck in self.cache:
                cached = self.cache.get(ck)
                if cached:
                    out[aid] = cached
            else:
                todo.append(aid)
        for batch in chunked(todo, 100):
            ids = ["ARXIV:%s" % a for a in batch]
            self.throttle.wait()
            try:
                r = self.session.post(self.BATCH, params={"fields": self.FIELDS},
                                      headers=self._headers(),
                                      data=json.dumps({"ids": ids}), timeout=45)
                if r.status_code != 200:
                    log.debug("s2 batch http %s", r.status_code)
                    continue
                rows = r.json()
            except Exception as exc:
                log.debug("s2 batch failed: %s", exc)
                continue
            # S2 can return an error-envelope dict with HTTP 200 under rate-limit;
            # zip over a dict iterates its keys (strings) and crashes _row. Skip it
            # (don't cache) so these ids are retried next run.
            if not isinstance(rows, list):
                log.warning("s2 batch returned non-list body (%s); skipping batch of %d",
                            type(rows).__name__, len(batch))
                continue
            if len(rows) != len(batch):
                log.warning("s2 batch length mismatch: %d rows for %d ids",
                            len(rows), len(batch))
            for aid, row in zip(batch, rows):
                rec = self._row(row) if isinstance(row, dict) else None
                self.cache.set("s2arxiv::" + aid, rec or {})
                if rec:
                    out[aid] = rec
        self.cache.flush()
        return out

    def match_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        if not title:
            return None
        ck = "s2title::" + norm_title(title)
        if ck in self.cache:
            return self.cache.get(ck) or None
        self.throttle.wait()
        rec = None
        definitive = False                       # only a clean HTTP 200 is conclusive
        try:
            r = self.session.get(self.MATCH, params={"query": title, "fields": self.FIELDS},
                                 headers=self._headers(), timeout=40)
            if r.status_code == 200:
                definitive = True
                data = r.json().get("data") or []
                # S2 relevance ranking can place the exact paper *below* a longer title
                # that contains it (e.g. "Ross3D: <title> With 3D ..." outranking the
                # plain "<title>"), so scan the top candidates and take the best
                # confident (>=0.9) title match rather than blindly trusting data[0].
                best = None
                for cand in data[:5]:
                    sim = title_similarity(title, cand.get("title", ""))
                    if sim >= 0.9 and (best is None or sim > best[0]):
                        best = (sim, cand)
                if best:
                    rec = self._row(best[1])
            # non-200 (429/5xx): definitive stays False -> not cached -> retried
        except Exception as exc:
            log.debug("s2 title match failed for %r: %s", title[:40], exc)
        if definitive:
            self.cache.set(ck, rec or {})
        return rec

    def citing_dates(self, paper_id: str, asof: _dt.date) -> Optional[List[str]]:
        """Publication dates (ISO) of every paper that cites `paper_id` — used to
        reconstruct a multi-timestamp CitedBy series (same idea as OpenAlex, but with
        S2's far better venue coverage). When a citing paper exposes only a year, the
        date is estimated as <year>-07-01. Cached per (paper, asof-day). Returns None on
        a transient error (so it isn't cached and is retried)."""
        if not paper_id:
            return None
        ck = "s2cites::%s::%s" % (paper_id, asof.isoformat())
        if ck in self.cache:
            return self.cache.get(ck)
        dates: List[str] = []
        offset = 0
        try:
            while offset < 10000:                  # S2 caps offset+limit at 10000
                self.throttle.wait()
                r = self.session.get(self.CITES % paper_id,
                                     params={"fields": "publicationDate,year",
                                             "limit": 1000, "offset": offset},
                                     headers=self._headers(), timeout=45)
                if r.status_code != 200:
                    log.debug("s2 citations http %s for %s", r.status_code, paper_id)
                    return None                    # transient: don't cache
                body = r.json()
                rows = body.get("data") or []
                for it in rows:
                    cp = it.get("citingPaper") or {}
                    d = cp.get("publicationDate")
                    if not d and cp.get("year"):
                        d = "%d-07-01" % int(cp["year"])
                    if d:
                        dates.append(d)
                nxt = body.get("next")
                if nxt is None or not rows:
                    break
                offset = nxt
        except Exception as exc:
            log.debug("s2 citing-dates failed for %s: %s", paper_id, exc)
            return None
        self.cache.set(ck, dates)
        return dates

    @staticmethod
    def _row(row: Dict[str, Any]) -> Dict[str, Any]:
        ext = row.get("externalIds") or {}
        return {
            "paperId": row.get("paperId"),
            "citationCount": row.get("citationCount"),
            "doi": ext.get("DOI"),
            "arxiv": ext.get("ArXiv"),
            "corpusId": ext.get("CorpusId"),
            "dblp": ext.get("DBLP"),
            "url": row.get("url"),
            "year": row.get("year"),
        }


# =========================================================================== #
# Papers-with-Code enrichment (GitHub)
# =========================================================================== #
class PapersWithCodeClient:
    BASE = "https://paperswithcode.com/api/v1"

    def __init__(self, session: requests.Session, throttle: Throttle, cache: JsonCache):
        self.session = session
        self.throttle = throttle
        self.cache = cache

    def github_for_arxiv(self, arxiv_id: str) -> Optional[str]:
        if not arxiv_id:
            return None
        ck = "pwc::" + arxiv_id
        if ck in self.cache:
            return self.cache.get(ck) or None
        url = None
        definitive = False                       # only cache on a conclusive answer
        try:
            self.throttle.wait()
            r = self.session.get(self.BASE + "/papers/", params={"arxiv_id": arxiv_id},
                                 timeout=30, allow_redirects=True)
            if r.status_code == 200:
                results = r.json().get("results") or []
                if not results:
                    definitive = True            # paper genuinely not in PwC
                else:
                    pid = results[0].get("id")
                    if not pid:
                        definitive = True
                    else:
                        self.throttle.wait()
                        r2 = self.session.get(self.BASE + "/papers/%s/repositories/" % pid,
                                              timeout=30, allow_redirects=True)
                        if r2.status_code == 200:
                            definitive = True
                            repos = r2.json().get("results") or []
                            official = [x for x in repos if x.get("is_official")]
                            pick = (official or repos)
                            if pick:
                                url = pick[0].get("url")
                        # r2 non-200 -> transient, leave definitive False
            # r non-200 -> transient
        except Exception as exc:
            log.debug("pwc lookup failed for %s: %s", arxiv_id, exc)
        if definitive:
            self.cache.set(ck, url or "")
        return url


# =========================================================================== #
# OpenAlex citation-history enrichment (multi-timestamp CitedBy)
# =========================================================================== #
def gen_snapshot_dates(start_ym: Optional[str], asof: _dt.date,
                       cadence_months: int) -> List[_dt.date]:
    """Calendar-aligned snapshot dates (1st of the month at `cadence` intervals)
    from the paper's start month through `asof`, always ending exactly at `asof`."""
    if start_ym and len(start_ym) >= 6 and start_ym[:6].isdigit():
        sy, sm = int(start_ym[:4]), int(start_ym[4:6])
    else:
        sy, sm = asof.year, 1
    cadence = max(1, cadence_months)
    start_idx = sy * 12 + (sm - 1)
    asof_idx = asof.year * 12 + (asof.month - 1)
    first = (start_idx // cadence) * cadence
    if first < start_idx:
        first += cadence
    snaps: List[_dt.date] = []
    i = first
    while i <= asof_idx:
        yy, mm = divmod(i, 12)
        d = _dt.date(yy, mm + 1, 1)
        if d <= asof:
            snaps.append(d)
        i += cadence
    if not snaps or snaps[-1] != asof:
        snaps.append(asof)
    return sorted(set(snaps))


def reconstruct_series(dates: Sequence[str], start_ym: Optional[str], asof: _dt.date,
                       cadence_months: int) -> List[str]:
    """Turn a list of citing-work publication dates (ISO strings) into the demo's
    multi-timestamp CitedBy series: at each calendar-aligned snapshot, count the
    citing works published on or before it. Source-agnostic (OpenAlex or S2)."""
    snaps = gen_snapshot_dates(start_ym, asof, cadence_months)
    out = []
    for d in snaps:
        iso = d.isoformat()
        out.append("%d@%s" % (sum(1 for x in dates if x <= iso), d.strftime("%Y.%m.%d")))
    return out


class OpenAlexClient:
    """Reconstructs a citation-count time series from the publication dates of
    citing works (OpenAlex is free, well-deduplicated for recent papers, and not
    aggressively rate-limited when a mailto is supplied)."""

    BASE = "https://api.openalex.org/works"

    def __init__(self, session: requests.Session, throttle: Throttle, cache: JsonCache,
                 mailto: str, min_similarity: float = 0.9, max_pages: int = 60):
        self.session = session
        self.throttle = throttle
        self.cache = cache
        self.mailto = mailto or ""
        self.min_similarity = min_similarity
        self.max_pages = max_pages

    def _params(self, **kw):
        if self.mailto:
            kw["mailto"] = self.mailto
        return kw

    def resolve(self, title: str, year: Optional[int]) -> Optional[Dict[str, Any]]:
        """Best OpenAlex work for a title (highest cited_by_count among confident
        title matches, to survive duplicate/preprint fragments)."""
        if not title:
            return None
        ck = "oa_resolve::" + norm_title(title)
        if ck in self.cache:
            return self.cache.get(ck) or None
        best = None
        try:
            self.throttle.wait()
            r = self.session.get(self.BASE, params=self._params(
                filter="title.search:%s" % title, per_page=10), timeout=40)
            if r.status_code == 200:
                cands = []
                for w in r.json().get("results", []) or []:
                    sim = title_similarity(title, w.get("title") or "")
                    if sim >= self.min_similarity:
                        cands.append((w.get("cited_by_count") or 0, sim, w))
                if cands:
                    cands.sort(key=lambda t: (t[0], t[1]), reverse=True)
                    w = cands[0][2]
                    best = {"id": w.get("id", "").split("/")[-1],
                            "cited_by_count": w.get("cited_by_count"),
                            "counts_by_year": w.get("counts_by_year"),
                            "title": w.get("title")}
            else:
                log.debug("openalex resolve http %s for %r", r.status_code, title[:40])
                return None                       # transient: don't cache
        except Exception as exc:
            log.debug("openalex resolve failed for %r: %s", title[:40], exc)
            return None                           # transient: don't cache
        self.cache.set(ck, best or {})
        return best

    def citing_dates(self, work_id: str, asof: _dt.date) -> Optional[List[str]]:
        """All citing-work publication dates (ISO strings). Cached per (work, asof-day)."""
        if not work_id:
            return None
        ck = "oa_cites::%s::%s" % (work_id, asof.isoformat())
        if ck in self.cache:
            return self.cache.get(ck)
        dates: List[str] = []
        cursor = "*"
        pages = 0
        try:
            while cursor and pages < self.max_pages:
                self.throttle.wait()
                r = self.session.get(self.BASE, params=self._params(
                    filter="cites:%s" % work_id, select="publication_date",
                    per_page=200, cursor=cursor), timeout=40)
                if r.status_code != 200:
                    log.debug("openalex cites http %s for %s", r.status_code, work_id)
                    return None                   # transient: don't cache
                body = r.json()
                results = body.get("results", []) or []
                dates += [w["publication_date"] for w in results if w.get("publication_date")]
                cursor = (body.get("meta") or {}).get("next_cursor")
                pages += 1
                if not results:
                    break
        except Exception as exc:
            log.debug("openalex cites failed for %s: %s", work_id, exc)
            return None
        self.cache.set(ck, dates)
        return dates

    def history_series(self, title: str, year: Optional[int], start_ym: Optional[str],
                       asof: _dt.date, cadence_months: int,
                       s2_count: Optional[int] = None) -> Optional[List[str]]:
        """Return CitedBy snapshots ['<count>@<YYYY.MM.DD>', ...] reconstructed from
        citing-work dates, or None if the paper can't be resolved / has no data.

        Returns None (so the caller uses the Semantic Scholar single-snapshot fallback)
        not only when OpenAlex can't resolve the paper, but also when it resolves yet
        its total `cited_by_count` is materially below what S2 reports: OpenAlex's
        citation index lags for recent papers, so a resolved-but-undercounted work would
        otherwise yield a bogus all-/mostly-zero series (e.g. OpenAlex 0 vs S2 10)."""
        work = self.resolve(title, year)
        if not work or not work.get("id"):
            return None
        oa_total = work.get("cited_by_count") or 0
        if s2_count is not None and s2_count >= 3 and oa_total < s2_count * 0.5:
            log.debug("openalex undercounts %r (OA=%d vs S2=%d); using S2 fallback",
                      title[:40], oa_total, s2_count)
            return None
        dates = self.citing_dates(work["id"], asof)
        if dates is None:
            return None
        return reconstruct_series(dates, start_ym, asof, cadence_months)
