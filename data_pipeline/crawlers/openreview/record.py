"""
论文记录数据类与富化装配（从 openreview_scraper.py 原样移植）。

- PaperRecord       : 上游“论文画像”schema 的数据类。
- build_base_record : 从一条 OpenReview note 构建基础 PaperRecord。
- apply_enrichment  : 把 arXiv / Semantic Scholar / GitHub 富化结果写回 record。
- apply_profiles    : 把作者主页 / 单位写回 record。
"""

from __future__ import annotations

import dataclasses
from collections import OrderedDict
from typing import Any, List, Optional

from ai4research.data_pipeline.crawlers.openreview.helpers import (
    cval,
    dt_to_dot,
    extract_repo_url,
    keyword_to_tag,
    ms_to_yyyymm,
    _aff_key,
)
from ai4research.data_pipeline.crawlers.openreview.source import (
    OpenReviewSource,
    ProfileResolver,
)


# =========================================================================== #
# Paper record (the schema)
# =========================================================================== #
SCHEMA_KEYS = [
    "title", "aliases", "time_start", "time_end", "AcceptBy", "tags",
    "url(Official)", "url(arXiv)", "url(Github)", "url(OR)", "url(Others)",
    "Baselines", "Benchmarks", "Metrics", "CitedBy",
    "Authors", "1stAuthorHP", "Affiliations", "Creator", "EditLogs",
]
# fields a human curates by hand — preserved across re-runs
MANUAL_KEYS = {"aliases", "tags", "Baselines", "Benchmarks", "Metrics", "Creator"}
LIST_KEYS = {"aliases", "tags", "url(Others)", "Baselines", "Benchmarks", "Metrics",
             "CitedBy", "Authors", "Affiliations", "EditLogs"}


@dataclasses.dataclass
class PaperRecord:
    title: str = ""
    aliases: List[str] = dataclasses.field(default_factory=list)
    time_start: str = ""
    time_end: str = ""
    accept_by: str = ""
    tags: List[str] = dataclasses.field(default_factory=list)
    url_official: str = ""
    url_arxiv: str = ""
    url_github: str = ""
    url_or: str = ""
    url_others: List[str] = dataclasses.field(default_factory=list)
    baselines: List[str] = dataclasses.field(default_factory=list)
    benchmarks: List[str] = dataclasses.field(default_factory=list)
    metrics: List[str] = dataclasses.field(default_factory=list)
    cited_by: List[str] = dataclasses.field(default_factory=list)
    authors: List[str] = dataclasses.field(default_factory=list)
    first_author_hp: str = ""
    affiliations: List[str] = dataclasses.field(default_factory=list)
    creator: str = ""
    edit_logs: List[str] = dataclasses.field(default_factory=list)

    # --- extras (kept in frontmatter below the schema block, for provenance) ---
    forum_id: str = ""
    number: Optional[int] = None
    presentation_type: str = ""
    primary_area: str = ""
    authorids: List[str] = dataclasses.field(default_factory=list)
    keywords: List[str] = dataclasses.field(default_factory=list)
    doi: str = ""
    corpus_id: str = ""
    s2_paper_id: str = ""
    arxiv_id: str = ""
    openreview_pdf: str = ""
    auto_extracted: List[str] = dataclasses.field(default_factory=list)

    # --- body content ---
    tldr: str = ""
    abstract: str = ""

    def schema_items(self) -> "OrderedDict[str, Any]":
        od: "OrderedDict[str, Any]" = OrderedDict()
        od["title"] = self.title
        od["aliases"] = self.aliases
        od["time_start"] = self.time_start
        od["time_end"] = self.time_end
        od["AcceptBy"] = self.accept_by
        od["tags"] = self.tags
        od["url(Official)"] = self.url_official
        od["url(arXiv)"] = self.url_arxiv
        od["url(Github)"] = self.url_github
        od["url(OR)"] = self.url_or
        od["url(Others)"] = self.url_others
        od["Baselines"] = self.baselines
        od["Benchmarks"] = self.benchmarks
        od["Metrics"] = self.metrics
        od["CitedBy"] = self.cited_by
        od["Authors"] = self.authors
        od["1stAuthorHP"] = self.first_author_hp
        od["Affiliations"] = self.affiliations
        od["Creator"] = self.creator
        od["EditLogs"] = self.edit_logs
        return od

    def extra_items(self) -> "OrderedDict[str, Any]":
        od: "OrderedDict[str, Any]" = OrderedDict()
        od["forum_id"] = self.forum_id
        od["number"] = self.number
        od["presentation_type"] = self.presentation_type
        od["primary_area"] = self.primary_area
        od["keywords"] = self.keywords
        od["authorids"] = self.authorids
        od["arxiv_id"] = self.arxiv_id
        od["doi"] = self.doi
        od["corpus_id"] = self.corpus_id
        od["s2_paper_id"] = self.s2_paper_id
        od["openreview_pdf"] = self.openreview_pdf
        if self.auto_extracted:
            od["auto_extracted"] = self.auto_extracted   # which fields an LLM filled
        return od


# =========================================================================== #
# Record building & enrichment wiring
# =========================================================================== #
def build_base_record(note, source: "OpenReviewSource", cfg) -> PaperRecord:
    rec = PaperRecord()
    rec.forum_id = getattr(note, "forum", None) or getattr(note, "id", "")
    rec.number = getattr(note, "number", None)
    rec.title = (cval(note, "title") or "").strip()
    rec.authors = list(cval(note, "authors", default=[]) or [])
    rec.authorids = list(cval(note, "authorids", default=[]) or [])
    rec.keywords = list(cval(note, "keywords", default=[]) or [])
    rec.tags = [t for t in (keyword_to_tag(k) for k in rec.keywords) if t]
    rec.primary_area = (cval(note, "primary_area") or "").strip()
    rec.tldr = (cval(note, "TLDR", "TL;DR") or "").strip()
    rec.abstract = (cval(note, "abstract") or "").strip()

    # GitHub/code link straight from the paper text (reliable & free); a code
    # content field, if the venue has one, takes precedence.
    code_field = cval(note, "code")
    rec.url_github = (code_field if code_field and "github" in str(code_field).lower() else None) \
        or extract_repo_url(rec.abstract, rec.tldr) or ""

    venue = cval(note, "venue") or ""
    accept_by, ptype = OpenReviewSource.split_venue(venue)
    rec.accept_by = accept_by
    rec.presentation_type = ptype

    rec.url_or = "https://openreview.net/forum?id=%s" % rec.forum_id
    pdf = cval(note, "pdf")
    if pdf:
        rec.openreview_pdf = pdf if str(pdf).startswith("http") else "https://openreview.net" + str(pdf)

    # url(Others): collect provenance links (OR pdf, supplementary)
    others: List[str] = []
    if rec.openreview_pdf:
        others.append(rec.openreview_pdf)
    supp = cval(note, "supplementary_material")
    if supp:
        supp_url = supp if str(supp).startswith("http") else "https://openreview.net" + str(supp)
        others.append(supp_url)
    rec.url_others = others

    # dates from OpenReview (fallback if arXiv not matched).
    # time_start = note creation; time_end = the real publication date (pdate) only.
    # mdate/tmdate are 'last metadata edit' timestamps (can be years after the paper
    # on stale maintenance touches) and must NOT masquerade as a publication date —
    # for pdate-less notes (submissions/withdrawn/rejected) leave time_end == time_start.
    start_ms = getattr(note, "cdate", None) or getattr(note, "tcdate", None)
    pdate_ms = getattr(note, "pdate", None)
    rec.time_start = ms_to_yyyymm(start_ms) or ""
    rec.time_end = (ms_to_yyyymm(pdate_ms) if pdate_ms else None) or rec.time_start

    rec.creator = cfg.creator
    return rec


def apply_enrichment(rec: PaperRecord, arxiv_rec, s2_rec, github_url, run_date) -> None:
    # arXiv: URL + first/last version dates (override OR-derived dates when present)
    if arxiv_rec:
        rec.arxiv_id = arxiv_rec.get("arxiv_id") or rec.arxiv_id
        if arxiv_rec.get("abs_url"):
            rec.url_arxiv = arxiv_rec["abs_url"]
        if arxiv_rec.get("first_ym"):
            rec.time_start = arxiv_rec["first_ym"]
        if arxiv_rec.get("last_ym"):
            rec.time_end = arxiv_rec["last_ym"]
        # arXiv may supply only one endpoint (partial feed); the other stays
        # OR-derived from a different source. Keep the interval ordered.
        # YYYYMM strings are fixed-width, so lexicographic compare is chronological.
        if rec.time_start and rec.time_end and rec.time_end < rec.time_start:
            rec.time_end = rec.time_start
    # Semantic Scholar: citations snapshot + DOI + official url
    if s2_rec:
        rec.s2_paper_id = s2_rec.get("paperId") or ""
        rec.corpus_id = str(s2_rec.get("corpusId") or "")
        if s2_rec.get("doi"):
            rec.doi = s2_rec["doi"]
            # an arXiv DOI is not an "official" venue/proceedings link — skip it
            if not rec.url_official and not str(s2_rec["doi"]).lower().startswith("10.48550/arxiv"):
                rec.url_official = "https://doi.org/%s" % s2_rec["doi"]
        cc = s2_rec.get("citationCount")
        if cc is not None:
            rec.cited_by = ["%d@%s" % (int(cc), dt_to_dot(run_date))]
        if s2_rec.get("url") and s2_rec["url"] not in rec.url_others:
            rec.url_others = rec.url_others + [s2_rec["url"]]
        if not rec.arxiv_id and s2_rec.get("arxiv"):
            rec.arxiv_id = s2_rec["arxiv"]
            if not rec.url_arxiv:
                rec.url_arxiv = "https://arxiv.org/abs/%s" % s2_rec["arxiv"]
    # GitHub (Papers-with-Code only fills in when the paper text had no repo link)
    if github_url and not rec.url_github:
        rec.url_github = github_url


def apply_profiles(rec: PaperRecord, resolver: ProfileResolver) -> None:
    if not resolver.enabled:
        return
    # paper-time year (when the work was done) drives affiliation selection
    ystr = (rec.time_start or rec.time_end or "")[:4]
    year = int(ystr) if ystr.isdigit() else None
    # first author homepage
    if rec.authorids:
        info = resolver.get(rec.authorids[0])
        if info and info.get("homepage"):
            rec.first_author_hp = info["homepage"]
    # affiliations (unique by normalised key, in author order, paper-time)
    affs: List[str] = []
    seen_keys = set()
    for aid in rec.authorids:
        info = resolver.get(aid)
        a = ProfileResolver.affiliation_for_year(info, year) if info else None
        if a:
            k = _aff_key(a)
            if k and k not in seen_keys:
                seen_keys.add(k)
                affs.append(a)
    if affs:
        rec.affiliations = affs
