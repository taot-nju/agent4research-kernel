"""
collect_records —— 完整的 OpenReview 抓取 + 富化编排（从 openreview_scraper.py 的
``run()`` 移植），但**不写盘**：返回已经装配好所有富化结果的 PaperRecord 列表 + 数据源。

上层（OpenReviewCrawler / pipeline）拿到 records 后，既可以映射进 MongoDB schema，
也可以（可选）调用 vault_writer 写 Markdown。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from ai4research.data_pipeline.crawlers.openreview.helpers import (
    JsonCache,
    Throttle,
    build_session,
    log,
)
from ai4research.data_pipeline.crawlers.openreview.source import (
    OpenReviewSource,
    ProfileResolver,
)
from ai4research.data_pipeline.crawlers.openreview.enrichment import (
    ArxivClient,
    OpenAlexClient,
    PapersWithCodeClient,
    SemanticScholarClient,
    reconstruct_series,
)
from ai4research.data_pipeline.crawlers.openreview.record import (
    PaperRecord,
    apply_enrichment,
    apply_profiles,
    build_base_record,
)
from ai4research.data_pipeline.crawlers.openreview.llm_extract import LLMExtractClient


def collect_records(cfg) -> Tuple[List[PaperRecord], "OpenReviewSource"]:
    """连接 OpenReview → 抓取 notes → 多源富化 → 返回 (records, source)。

    cfg 是一个简单的命名空间（见 OpenReviewCrawler），需要包含 run() 所读取的全部字段。
    所有富化都是可选且独立的；任一外部源失败都不会阻断核心记录的产出。
    """
    run_date = cfg.as_of
    ua = "agent4research-openreview/1.0 (+https://openreview.net; mailto:%s)" % (cfg.mailto or "anonymous")
    session = build_session(ua)

    # caches —— 与上游一致，放在 vault 根目录的 .cache/ 下（可跨运行复用）
    cache_dir = os.path.join(cfg.out, ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    profile_cache = JsonCache(os.path.join(cache_dir, "profiles.json"))
    arxiv_cache = JsonCache(os.path.join(cache_dir, "arxiv.json"))
    s2_cache = JsonCache(os.path.join(cache_dir, "semanticscholar.json"))
    pwc_cache = JsonCache(os.path.join(cache_dir, "paperswithcode.json"))
    openalex_cache = JsonCache(os.path.join(cache_dir, "openalex.json"))

    # connect
    source = OpenReviewSource(cfg.api, cfg.username, cfg.password)
    source.connect_for_venue(cfg.venue)

    # fetch notes
    notes: List[Any] = []
    seen_ids = set()
    if cfg.ids:
        # targeted mode: only the given forum ids (e.g. update specific papers)
        id_list = [i.strip() for i in cfg.ids.split(",") if i.strip()]
        log.info("Targeted fetch of %d note id(s): %s", len(id_list), ", ".join(id_list))
        for n in source.fetch_by_ids(id_list):
            nid = getattr(n, "id", None)
            if nid in seen_ids:
                continue
            seen_ids.add(nid)
            n._category = "by-id"  # type: ignore
            notes.append(n)
    else:
        cat_map = source.category_venue_ids(cfg.venue)
        if cfg.categories == "accepted":
            wanted_cats = ["accepted"]
        elif cfg.categories == "all":
            wanted_cats = list(cat_map.keys())
        else:
            wanted_cats = [c.strip() for c in cfg.categories.split(",") if c.strip()]
        log.info("Categories: %s",
                 ", ".join("%s(%s)" % (c, cat_map.get(c, "?")) for c in wanted_cats))
        for cat in wanted_cats:
            vid = cat_map.get(cat)
            if not vid:
                log.warning("category %r not available for this venue; skipping", cat)
                continue
            for n in source.fetch_category(vid):
                nid = getattr(n, "id", None)
                if nid in seen_ids:
                    continue
                seen_ids.add(nid)
                n._category = cat  # type: ignore
                notes.append(n)

    notes.sort(key=lambda n: (getattr(n, "number", 0) or 0))
    if cfg.limit:
        notes = notes[: cfg.limit]
    log.info("Total notes to process: %d", len(notes))
    if not notes:
        log.error("No notes found for venue %s. Check the venue id.", cfg.venue)
        return [], source

    # ---- build base records ----
    records: List[PaperRecord] = []
    for n in notes:
        rec = build_base_record(n, source, cfg)
        # carry the discovery category (accepted/withdrawn/...) for the vault index
        rec._category = getattr(n, "_category", "accepted")  # type: ignore[attr-defined]
        records.append(rec)

    # ---- enrichment: arXiv ----
    enrich_arxiv = cfg.enrich in ("arxiv", "all")
    enrich_s2 = cfg.enrich in ("s2", "all")
    arxiv_throttle = Throttle(cfg.arxiv_interval)
    s2_throttle = Throttle(cfg.s2_interval)
    pwc_throttle = Throttle(cfg.pwc_interval)
    profile_throttle = Throttle(cfg.profile_interval)

    arxiv_client = ArxivClient(session, arxiv_throttle, arxiv_cache, cfg.arxiv_min_sim)
    s2_client = SemanticScholarClient(session, s2_throttle, s2_cache,
                                      cfg.s2_api_key)
    pwc_client = PapersWithCodeClient(session, pwc_throttle, pwc_cache)

    arxiv_results: Dict[str, Any] = {}
    if enrich_arxiv:
        log.info("arXiv enrichment for %d papers (interval %.1fs)...", len(records),
                 cfg.arxiv_interval)
        for i, rec in enumerate(records, 1):
            res = arxiv_client.lookup(rec.title, rec.authors)
            if res:
                arxiv_results[rec.forum_id] = res
                rec.arxiv_id = res.get("arxiv_id", "")
            if i % 25 == 0:
                log.info("  arXiv %d/%d", i, len(records))
        arxiv_cache.flush()

    # ---- enrichment: Semantic Scholar (batch by arxiv id, then title fallback) ----
    s2_by_forum: Dict[str, Any] = {}
    if enrich_s2:
        ids = [r.arxiv_id for r in records if r.arxiv_id]
        log.info("Semantic Scholar batch for %d arXiv ids...", len(ids))
        by_arxiv = s2_client.batch_by_arxiv(ids) if ids else {}
        for rec in records:
            if rec.arxiv_id and rec.arxiv_id in by_arxiv:
                s2_by_forum[rec.forum_id] = by_arxiv[rec.arxiv_id]
        # title fallback for those still missing
        if cfg.s2_title_fallback:
            missing = [r for r in records if r.forum_id not in s2_by_forum]
            log.info("Semantic Scholar title-match fallback for %d papers...", len(missing))
            for i, rec in enumerate(missing, 1):
                row = s2_client.match_by_title(rec.title)
                if row:
                    s2_by_forum[rec.forum_id] = row
                if i % 25 == 0:
                    log.info("  s2-title %d/%d", i, len(missing))
        s2_cache.flush()

    # ---- enrichment: GitHub via Papers-with-Code ----
    github_by_forum: Dict[str, str] = {}
    if cfg.github:
        log.info("Papers-with-Code GitHub lookup...")
        for rec in records:
            if rec.arxiv_id:
                gh = pwc_client.github_for_arxiv(rec.arxiv_id)
                if gh:
                    github_by_forum[rec.forum_id] = gh
        pwc_cache.flush()

    # ---- citation history via OpenAlex (multi-timestamp CitedBy) ----
    cited_history_by_forum: Dict[str, List[str]] = {}
    if cfg.cited_history:
        oa_client = OpenAlexClient(session, Throttle(cfg.openalex_interval), openalex_cache,
                                   cfg.mailto, cfg.openalex_min_sim)
        log.info("OpenAlex citation-history (cadence=%d months) for %d papers...",
                 cfg.cited_cadence, len(records))
        n_hist = 0
        n_fallback = 0
        for i, rec in enumerate(records, 1):
            # prefer the arXiv first-version month for the series start (apply_enrichment,
            # which sets rec.time_start to it, hasn't run yet at this point)
            ar = arxiv_results.get(rec.forum_id) or {}
            start_ym = ar.get("first_ym") or rec.time_start
            ys = (start_ym or "")[:4]
            yr = int(ys) if ys.isdigit() else None
            # S2 current count — used BOTH as the OpenAlex-undercount cross-check inside
            # history_series and as the single-snapshot fallback below. Reuse the row from
            # --enrich s2 if present; else match by title once (cached). Stash it so
            # apply_enrichment can also fill the S2-derived IDs/URLs at no extra cost.
            s2row = s2_by_forum.get(rec.forum_id)
            if s2row is None:
                s2row = s2_client.match_by_title(rec.title)
                if s2row:
                    s2_by_forum[rec.forum_id] = s2row
            cc = (s2row or {}).get("citationCount")
            series = oa_client.history_series(rec.title, yr, start_ym,
                                              run_date, cfg.cited_cadence, cc)
            if series:
                cited_history_by_forum[rec.forum_id] = series
                n_hist += 1
            elif cc is not None:
                # OpenAlex couldn't resolve the paper, OR resolved it but materially
                # undercounts vs S2 (its index lags recent papers). Reconstruct the
                # multi-timestamp series from S2's CITING-paper dates instead (S2 has far
                # better venue coverage); only if those dates are unavailable do we degrade
                # to a single current-count snapshot.
                s2id = (s2row or {}).get("paperId")
                s2dates = s2_client.citing_dates(s2id, run_date) if s2id else None
                if s2dates is not None and (s2dates or int(cc) == 0):
                    cited_history_by_forum[rec.forum_id] = reconstruct_series(
                        s2dates, start_ym, run_date, cfg.cited_cadence)
                else:
                    cited_history_by_forum[rec.forum_id] = [
                        "%d@%s" % (int(cc), _dt_dot(run_date))]
                n_fallback += 1
            if i % 25 == 0:
                log.info("  openalex %d/%d (%d resolved, %d via S2 fallback)",
                         i, len(records), n_hist, n_fallback)
        openalex_cache.flush()
        s2_cache.flush()
        log.info("OpenAlex citation history resolved for %d/%d papers "
                 "(%d via Semantic Scholar fallback).", n_hist, len(records), n_fallback)

    # ---- profiles ----
    resolver = ProfileResolver(source.client, profile_cache, source.authenticated,
                               profile_throttle, cfg.profiles)
    if cfg.profiles:
        # first-author HP needs authorids[0]; affiliations need all authors
        need: List[str] = []
        for rec in records:
            need.extend(rec.authorids if cfg.affiliations_all else rec.authorids[:1])
        if source.authenticated:
            log.info("Authenticated: profiles fetched in bulk (no per-id rate limit).")
        else:
            n_unique = len(set(need))
            est = n_unique * cfg.profile_interval
            if est > 120:
                log.warning("Anonymous profile resolution of ~%d authors at %.1fs each "
                            "(~%.0f min). Provide --username/--password for fast bulk fetch.",
                            n_unique, cfg.profile_interval, est / 60.0)
        resolver.prefetch(need)

    # ---- LLM-assisted Baselines / Benchmarks / Metrics extraction ----
    llm_by_forum: Dict[str, Dict[str, List[str]]] = {}
    if cfg.llm_extract:
        llm_client = LLMExtractClient(
            session, cfg.llm_provider, cfg.llm_model, cfg.llm_api_key, cfg.llm_base_url,
            JsonCache(os.path.join(cache_dir, "llm_extract.json")),
            Throttle(cfg.llm_interval), cfg.llm_source, passes=cfg.llm_passes)
        ok, why = llm_client.available()
        if not ok:
            log.warning("--llm-extract (provider=%s) unavailable: %s; skipping.",
                        cfg.llm_provider, why)
        else:
            log.info("LLM extraction via %s (model=%s, source=%s) for %d papers...",
                     cfg.llm_provider, llm_client.model or "default", cfg.llm_source, len(records))
            n_ex = 0
            for i, rec in enumerate(records, 1):
                res = llm_client.extract(rec)
                if res and any(res.get(k) for k in ("baselines", "benchmarks", "metrics")):
                    llm_by_forum[rec.forum_id] = res
                    n_ex += 1
                if i % 10 == 0:
                    log.info("  llm %d/%d (%d extracted)", i, len(records), n_ex)
            log.info("LLM extraction populated %d/%d papers.", n_ex, len(records))

    # ---- apply all enrichment onto the records (no file writes here) ----
    for rec in records:
        apply_enrichment(rec,
                         arxiv_results.get(rec.forum_id),
                         s2_by_forum.get(rec.forum_id),
                         github_by_forum.get(rec.forum_id),
                         run_date)
        # OpenAlex multi-timestamp series overrides the single S2 snapshot
        if rec.forum_id in cited_history_by_forum:
            rec.cited_by = cited_history_by_forum[rec.forum_id]
        # LLM-extracted components (flagged auto_extracted for review)
        ex = llm_by_forum.get(rec.forum_id)
        if ex:
            filled = []
            if ex.get("baselines"):
                rec.baselines = ex["baselines"]; filled.append("Baselines")
            if ex.get("benchmarks"):
                rec.benchmarks = ex["benchmarks"]; filled.append("Benchmarks")
            if ex.get("metrics"):
                rec.metrics = ex["metrics"]; filled.append("Metrics")
            rec.auto_extracted = filled
        apply_profiles(rec, resolver)

    return records, source


def _dt_dot(d) -> str:
    """Local alias to avoid importing dt_to_dot just for one fallback line."""
    return d.strftime("%Y.%m.%d")
