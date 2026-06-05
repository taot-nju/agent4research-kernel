"""
OpenReview 数据源（v1/v2 兼容、版本自动探测、分类解析、分页抓取）以及作者画像解析。

从 openreview_scraper.py 原样移植：OpenReviewSource、ProfileResolver。
"""

from __future__ import annotations

import re
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Sequence, Tuple

import openreview
from openreview import api as or_api  # v2 client
from openreview import tools as or_tools

from ai4research.data_pipeline.crawlers.openreview.helpers import (
    JsonCache,
    Throttle,
    _aff_key,
    _EmptyPageError,
    _is_transient_error,
    chunked,
    log,
)


# =========================================================================== #
# OpenReview source (handles v1/v2 + venue category resolution)
# =========================================================================== #
class OpenReviewSource:
    V2_BASE = "https://api2.openreview.net"
    V1_BASE = "https://api.openreview.net"

    # presentation-type tokens that may trail a venue string ("ICLR 2026 Poster")
    PRESENTATION_TOKENS = (
        "oral", "poster", "spotlight", "notable top 25%", "notable top 5%",
        "notable", "findings", "highlight", "honorable mention",
        "best paper", "outstanding paper",
    )
    # acceptance words to strip ("NeurIPS 2022 Accept" -> "NeurIPS 2022")
    ACCEPT_WORDS = ("accepted", "accept")

    def __init__(self, version: str, username: Optional[str], password: Optional[str]):
        self.requested_version = version          # "auto" | "1" | "2"
        self.username = username
        self.password = password
        self.version: Optional[str] = None
        self.client = None
        self.authenticated = False

    # -- client construction -------------------------------------------------
    def _make_v2(self):
        kwargs = dict(baseurl=self.V2_BASE)
        if self.username and self.password:
            kwargs.update(username=self.username, password=self.password)
        c = or_api.OpenReviewClient(**kwargs)
        return c

    def _make_v1(self):
        kwargs = dict(baseurl=self.V1_BASE)
        if self.username and self.password:
            kwargs.update(username=self.username, password=self.password)
        c = openreview.Client(**kwargs)
        return c

    def _probe(self, client, venue_id: str) -> int:
        """Return whether this client sees accepted notes (>0) for the venue."""
        try:
            return len(client.get_notes(content={"venueid": venue_id}, limit=1))
        except Exception as exc:
            log.debug("probe failed: %s", exc)
            return -1   # -1 == client/endpoint error (distinct from 0 notes)

    def _has_group(self, client, venue_id: str) -> bool:
        try:
            client.get_group(venue_id)
            return True
        except Exception:
            return False

    def connect_for_venue(self, venue_id: str) -> str:
        """Pick the API version that actually serves this venue's accepted notes.

        In 'auto' mode both v2 and v1 are probed and the one that actually
        returns notes wins (a venue group can exist on v2 while its notes still
        live on v1, e.g. pre-migration venues like NeurIPS 2022)."""
        makers = {"2": self._make_v2, "1": self._make_v1}
        if self.requested_version in ("1", "2"):
            ver = self.requested_version
            client = makers[ver]()
            n = self._probe(client, venue_id)
            self.client, self.version = client, ver
            self.authenticated = bool(self.username and self.password)
            log.info("Connected via API v%s%s (probe: %s accepted note(s))", ver,
                     " [authenticated]" if self.authenticated else " [anonymous]",
                     "error" if n < 0 else n)
            return ver

        # auto: probe both, prefer the one with notes (v2 first on tie)
        results = []
        last_err = None
        for ver in ("2", "1"):
            try:
                client = makers[ver]()
            except Exception as exc:
                last_err = exc
                log.debug("v%s client init failed: %s", ver, exc)
                continue
            n = self._probe(client, venue_id)
            grp = self._has_group(client, venue_id)
            results.append((ver, client, n, grp))
            log.debug("v%s probe: notes=%s group=%s", ver, n, grp)

        if not results:
            raise RuntimeError("Could not reach OpenReview for venue %r: %s"
                               % (venue_id, last_err))
        with_notes = [r for r in results if r[2] > 0]
        with_group = [r for r in results if r[3]]
        chosen = (with_notes or with_group or results)[0]
        ver, client, n, grp = chosen
        self.client, self.version = client, ver
        self.authenticated = bool(self.username and self.password)
        log.info("Connected via API v%s%s (probe: %s accepted note(s), group=%s)", ver,
                 " [authenticated]" if self.authenticated else " [anonymous]",
                 "error" if n < 0 else n, grp)
        if n <= 0:
            log.warning("No accepted notes detected yet for %s on the chosen API; "
                        "decisions may be pending or the venue id may be wrong.", venue_id)
        return ver

    # -- venue category venue-ids -------------------------------------------
    def category_venue_ids(self, venue_id: str) -> "OrderedDict[str, str]":
        """Map human category -> venueid using the venue group's metadata."""
        cats: "OrderedDict[str, str]" = OrderedDict()
        cats["accepted"] = venue_id
        try:
            group = self.client.get_group(venue_id)
            gc = getattr(group, "content", None) or {}

            def gv(k):
                v = gc.get(k)
                if isinstance(v, dict):
                    return v.get("value")
                return v
            for human, key in (
                ("withdrawn", "withdrawn_venue_id"),
                ("desk_rejected", "desk_rejected_venue_id"),
                ("rejected", "rejected_venue_id"),
                ("submission", "submission_venue_id"),
            ):
                vid = gv(key)
                if vid:
                    cats[human] = vid
            if self.version == "1" and len(cats) == 1:
                log.warning("API v1 venue group %s exposes no subcategory venue ids; "
                            "only 'accepted' is available. '--categories all' / "
                            "non-accepted categories return accepted papers only here.",
                            venue_id)
        except Exception as exc:
            log.debug("could not read venue group %s: %s", venue_id, exc)
        return cats

    # -- fetching ------------------------------------------------------------
    @staticmethod
    def _retry_call(fn, what: str, attempts: int = 6, base: float = 2.0):
        last = None
        for i in range(attempts):
            try:
                return fn()
            except Exception as exc:
                last = exc
                # Don't burn the backoff schedule on deterministic client errors
                # (4xx except 429) — they will never succeed on retry.
                status = None
                if isinstance(exc, openreview.OpenReviewException):
                    a = exc.args[0] if exc.args else None
                    if isinstance(a, dict):
                        status = a.get("status")
                if status in (400, 401, 403, 404):
                    log.error("%s failed with non-retryable status %s: %s",
                              what, status, str(exc)[:140])
                    raise
                if i == attempts - 1:        # no point sleeping after the last try
                    break
                wait = min(base * (2 ** i), 30.0)
                log.warning("%s failed (attempt %d/%d): %s; retrying in %.0fs",
                            what, i + 1, attempts, str(exc)[:140], wait)
                time.sleep(wait)
        raise last

    def fetch_category(self, venueid: str) -> List[Any]:
        """Robust offset-paginated fetch (avoids long-lived streaming responses
        that the proxy/network may cut mid-flight). Uses with_count to detect a
        transient empty/short page (HTTP-200 empty body from a flaky proxy) and
        retries the same offset instead of silently truncating the category."""
        log.info("Fetching notes for venueid=%s ...", venueid)
        notes: List[Any] = []
        limit = 1000
        expected = None

        # First page WITHOUT offset, so with_count returns (notes, count).
        # NOTE: both v1 and v2 only return the tuple when offset is omitted/None.
        first = self._retry_call(
            lambda: self.client.get_notes(
                content={"venueid": venueid}, limit=limit,
                sort="number:asc", with_count=True),
            what="get_notes(count, offset=0)")
        if isinstance(first, tuple):
            page, expected = first[0], first[1]
        else:                                  # defensive: some paths return a bare list
            page = first
        notes.extend(page)
        offset = len(page)
        log.info("  ... %d fetched%s", len(notes),
                 "" if expected is None else " of %d" % expected)

        while True:
            if expected is not None:
                if len(notes) >= expected:
                    break
            elif len(page) < limit:
                break

            def _fetch(o=offset):
                p = self.client.get_notes(
                    content={"venueid": venueid}, limit=limit, offset=o, sort="number:asc")
                # If we know the total, an empty page before reaching it is treated
                # as a (possibly transient) gap: raise so _retry_call retries the
                # SAME offset. A genuinely-transient empty-200 resolves within the
                # retries; a persistent count/actual mismatch does not.
                if expected is not None and not p and o < expected:
                    raise _EmptyPageError("empty page at offset=%d but expected %d" % (o, expected))
                return p

            try:
                page = self._retry_call(_fetch, what="get_notes(offset=%d)" % offset)
            except _EmptyPageError as exc:
                # The empty page persisted across all retries -> almost certainly a
                # real end-of-data (e.g. notes deleted after the count query), not a
                # transient blip. Degrade gracefully: log partial below and stop.
                log.warning("pagination stopped early at offset=%d: %s", offset, exc)
                break
            if not page:
                break
            notes.extend(page)
            offset += len(page)
            log.info("  ... %d fetched%s", len(notes),
                     "" if expected is None else " of %d" % expected)

        if expected is not None and len(notes) < expected:
            log.error("PARTIAL FETCH for venueid=%s: got %d of %d notes; "
                      "results are incomplete.", venueid, len(notes), expected)
        log.info("  -> %d notes", len(notes))
        return notes

    def fetch_by_ids(self, ids: Sequence[str]) -> List[Any]:
        """Fetch specific submission notes by forum/note id (version-agnostic)."""
        notes: List[Any] = []
        for fid in ids:
            try:
                if self.version == "1":
                    n = self._retry_call(lambda f=fid: self.client.get_note(f),
                                         what="get_note(%s)" % fid)
                else:
                    got = self._retry_call(lambda f=fid: self.client.get_notes(id=f),
                                           what="get_notes(id=%s)" % fid)
                    n = got[0] if got else None
                if n is not None:
                    notes.append(n)
                else:
                    log.warning("note %s not found", fid)
            except Exception as exc:
                log.error("could not fetch note %s: %s", fid, str(exc)[:140])
        log.info("Fetched %d note(s) by id", len(notes))
        return notes

    # -- venue string parsing ------------------------------------------------
    @classmethod
    def split_venue(cls, venue: Optional[str]) -> Tuple[str, str]:
        """'ICLR 2026 Poster' -> ('ICLR 2026', 'Poster');
        'NeurIPS 2022 Accept (Oral)' -> ('NeurIPS 2022', 'Oral'). (accept_by, ptype)."""
        if not venue:
            return "", ""
        v = venue.strip()
        ptype = ""
        # a trailing parenthetical usually IS the presentation type
        pm = re.search(r"\(([^)]*)\)\s*$", v)
        if pm:
            ptype = pm.group(1).strip()
            v = v[: pm.start()].strip()
        changed = True
        while changed and v:
            changed = False
            low = v.lower()
            for tok in cls.PRESENTATION_TOKENS:
                if low.endswith(tok):
                    if not ptype:
                        ptype = v[len(v) - len(tok):].strip()
                    v = v[: len(v) - len(tok)].strip(" -—|,")
                    changed = True
                    break
            if changed:
                continue
            for tok in cls.ACCEPT_WORDS:
                if low.endswith(tok):
                    v = v[: len(v) - len(tok)].strip(" -—|,")
                    changed = True
                    break
        return (v or venue), ptype


# =========================================================================== #
# Author profiles (homepage + affiliation)
# =========================================================================== #
class ProfileResolver:
    def __init__(self, client, cache: JsonCache, authenticated: bool, throttle: Throttle,
                 enabled: bool):
        self.client = client
        self.cache = cache
        self.authenticated = authenticated
        self.throttle = throttle
        self.enabled = enabled

    @staticmethod
    def _clean_affiliation(name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        # "Technion, Technion" -> "Technion"; dedupe comma-separated repeats
        parts = [p.strip() for p in str(name).split(",") if p.strip()]
        out: List[str] = []
        for p in parts:
            if not out or out[-1].lower() != p.lower():
                out.append(p)
        # also drop later parts that duplicate the first (case-insensitive substring)
        if len(out) >= 2 and out[1].lower() in out[0].lower():
            out = [out[0]]
        return ", ".join(out) if out else None

    @classmethod
    def _extract(cls, profile) -> Dict[str, Any]:
        content = getattr(profile, "content", None) or {}
        # preferred display name
        name = None
        for nm in content.get("names", []) or []:
            if isinstance(nm, dict):
                if nm.get("preferred") and (nm.get("fullname") or nm.get("name")):
                    name = nm.get("fullname") or nm.get("name")
                    break
        if not name:
            for nm in content.get("names", []) or []:
                if isinstance(nm, dict):
                    name = nm.get("fullname") or nm.get("name")
                    if not name and (nm.get("first") or nm.get("last")):
                        name = " ".join(x for x in (nm.get("first"), nm.get("middle"),
                                                    nm.get("last")) if x)
                    if name:
                        break
        # build a normalised, year-tagged employment history so callers can pick
        # the affiliation that was active when a given paper was published.
        def _yr(v):
            try:
                return int(v)
            except Exception:
                return None
        hist: List[Dict[str, Any]] = []
        for h in content.get("history", []) or []:
            if not isinstance(h, dict):
                continue
            inst = h.get("institution") or {}
            nm = cls._clean_affiliation(inst.get("name"))
            if not nm:
                continue
            hist.append({"name": nm, "start": _yr(h.get("start")),
                         "end": _yr(h.get("end")), "position": h.get("position")})

        # default "current" affiliation: prefer an open-ended entry, else most recent
        affiliation = None
        position = None
        open_ended = [h for h in hist if h.get("end") in (None, 0)]
        pool = open_ended or hist
        if pool:
            best = max(pool, key=lambda h: (h.get("start") or 0))
            affiliation = best.get("name")
            position = best.get("position")
        return {
            "id": getattr(profile, "id", None),
            "name": name,
            "homepage": content.get("homepage"),
            "gscholar": content.get("gscholar"),
            "dblp": content.get("dblp"),
            "affiliation": affiliation,     # current/most-recent (fallback)
            "position": position,
            "history": hist,
        }

    @staticmethod
    def affiliation_for_year(info: Dict[str, Any], year: Optional[int]) -> Optional[str]:
        """The affiliation active in `year` (where the paper was written). Among
        entries spanning the year, prefer a CLOSED stint (a specific past
        employment) over the OPEN 'current' one, so a 2022 paper resolves to the
        author's 2022 employer rather than their present-day one. Falls back to
        the current/most-recent affiliation when nothing spans the year."""
        hist = (info or {}).get("history") or []
        if year and hist:
            spanning = [h for h in hist
                        if (h.get("start") or 0) <= year
                        and (h.get("end") is None or year <= h["end"])]
            if spanning:
                closed = [h for h in spanning if h.get("end")]
                pick = max(closed or spanning, key=lambda h: (h.get("start") or 0))
                return pick.get("name")
        return (info or {}).get("affiliation")

    def prefetch(self, ids: Sequence[str]) -> None:
        """Resolve a batch of (preferably ~) ids into the cache."""
        if not self.enabled:
            return
        wanted = [i for i in dict.fromkeys(ids) if i and i not in self.cache]
        if not wanted:
            return
        log.info("Resolving %d author profile(s) (%s)...", len(wanted),
                 "bulk/auth" if self.authenticated else "anonymous per-id")
        if self.authenticated:
            tilde = [i for i in wanted if str(i).startswith("~")]
            other = [i for i in wanted if not str(i).startswith("~")]
            for batch in chunked(tilde + other, 100):
                try:
                    # as_dict keys the result by EVERY requested id/email and by each
                    # profile's alias usernames, so non-canonical tilde aliases and
                    # emails map to the right profile (list mode drops that mapping).
                    mapping = or_tools.get_profiles(self.client, batch, as_dict=True)
                    for req, p in mapping.items():
                        info = self._extract(p) if p is not None else None
                        # drop synthesized content-less email stubs (no usable data)
                        if info is not None and not (info.get("name") or info.get("homepage")
                                                     or info.get("affiliation")):
                            info = None
                        self.cache.set(req, info)
                        if info is not None and info.get("id") and info["id"] != req:
                            self.cache.set(info["id"], info)   # also index canonical id
                    for req in batch:                          # safety net for omissions
                        if req not in self.cache:
                            self.cache.set(req, None)
                except Exception as exc:
                    log.warning("bulk profile fetch failed (%s); falling back per-id", exc)
                    for i in batch:
                        self._fetch_one(i)
        else:
            for i in wanted:
                self._fetch_one(i)
        self.cache.flush()

    def _fetch_one(self, ident: str) -> None:
        if ident in self.cache:
            return
        # anonymous email lookups are forbidden; only resolve tilde-ids w/o auth
        if not self.authenticated and not str(ident).startswith("~"):
            self.cache.set(ident, None)
            return
        self.throttle.wait()
        try:
            p = self.client.get_profile(ident)
            self.cache.set(ident, self._extract(p))
        except Exception as exc:
            if _is_transient_error(exc):
                # do NOT poison the cache — leave unresolved so a later run retries
                log.warning("profile %s transient error (not caching): %s",
                            ident, str(exc)[:140])
                if "429" in str(exc) or "Too Many Requests" in str(exc):
                    time.sleep(min(self.throttle.min_interval * 2 + 5.0, 30.0))
                return
            log.debug("profile %s not resolved: %s", ident, exc)
            self.cache.set(ident, None)   # authoritative 'not found'

    def get(self, ident: str) -> Optional[Dict[str, Any]]:
        if not ident:
            return None
        return self.cache.get(ident)
