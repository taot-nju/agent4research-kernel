"""
OpenReview 爬虫：把移植过来的抓取/富化引擎接入本仓库的 Crawler 架构。

语义与 BaseCrawler 一致：
    crawl() 是 generator，每次 yield (paper_data, source_context)，
    其中 paper_data 形状符合 paper_schema.DEFAULT_PAPER_FIELDS，
    source_context 为规范化后的 venue（例如 "ICLR 2026"），供 pipeline 作为 source 写库。

设计要点：
- 复用 openreview 引擎的 collect_records（连接 → 抓取 → 多源富化），保留其批量
  Semantic Scholar、作者画像批量预取、OpenAlex 引用历史等正确且高效的逻辑；
- record_to_paper_data 把引擎的 PaperRecord 映射为 MongoDB 文档；
- _id 复用 utils.text_utils.paper_id_from_title（标题哈希），从而与 arXiv 抓取
  天然去重：同一篇论文若先来自 arXiv、后被会议接收，会落到同一个 _id 上；
- arxiv_obj 仅在 arXiv 富化命中时填充，否则保持 schema 默认空值，避免覆盖已有的 arXiv 信息；
- 原始 PaperRecord 以瞬时键 ``_openreview_record`` 挂在 paper_data 上，供 pipeline 在
  入库前弹出，并在开启 vault 时写 Markdown（绝不会写入 MongoDB）。
"""

from __future__ import annotations

import copy
import re
from types import SimpleNamespace
from typing import List, Optional

from rich import print

from ai4research.data_pipeline.crawlers.base import BaseCrawler
from ai4research.data_pipeline.crawlers.openreview.collect import collect_records
from ai4research.data_pipeline.schemas.paper_schema import DEFAULT_PAPER_FIELDS
from ai4research.data_pipeline.utils.text_utils import normalize_title, paper_id_from_title
from ai4research.data_pipeline.source_configs import openreview_config as orc


def venue_label_from_id(venue_id: str) -> str:
    """从 venue id 推导一个规范的会议标签作为兜底。

    例如 "ICLR.cc/2026/Conference" -> "ICLR 2026"；"NeurIPS.cc/2025/Conference" -> "NeurIPS 2025"。
    无法解析时原样返回 venue_id。
    """
    if not venue_id:
        return ""
    parts = [p for p in venue_id.split("/") if p]
    if not parts:
        return venue_id
    name = parts[0].split(".")[0]  # "ICLR.cc" -> "ICLR"
    year = None
    for p in parts[1:]:
        if re.fullmatch(r"(19|20)\d{2}", p):
            year = p
            break
    return ("%s %s" % (name, year)).strip() if year else venue_id


def record_to_paper_data(rec, venue_label: str) -> dict:
    """把引擎的 PaperRecord 映射为符合 DEFAULT_PAPER_FIELDS 的 MongoDB 文档。

    注意：仅写入“有值”的字段；arxiv_obj 在未匹配到 arXiv 时保持默认空值，
    以便跨源合并 upsert 不会用空值覆盖已存在的 arXiv 信息。
    原始 PaperRecord 以 ``_openreview_record`` 挂载，供 pipeline 写 vault 后弹出。
    """
    pd = copy.deepcopy(DEFAULT_PAPER_FIELDS)
    pd["_id"] = paper_id_from_title(rec.title)

    pd["title"] = rec.title
    pd["abstract"] = rec.abstract
    if rec.keywords:
        pd["keywords"] = list(rec.keywords)
    if rec.tags:
        pd["tags"] = list(rec.tags)
    if rec.tldr:
        pd["summary_short"] = rec.tldr

    # authors：引擎的 affiliations 是“去重后的机构列表”（非逐作者对齐），因此这里
    # 逐作者只填 name + 第一作者主页；完整的机构列表与作者 id 放进 openreview_obj。
    authors = []
    for i, name in enumerate(rec.authors):
        authors.append({
            "name": name,
            "affiliation": "",
            "homepage": rec.first_author_hp if i == 0 else "",
        })
    if authors:
        pd["authors"] = authors

    # 录用信息：会议覆盖 arXiv
    pd["accepted_by"] = venue_label

    # arXiv 专有字段：仅在命中时填充
    if rec.arxiv_id:
        pdf_url = "https://arxiv.org/pdf/%s" % rec.arxiv_id
        pd["arxiv_obj"] = {
            "arxiv_id": rec.arxiv_id,
            "arxiv_url": rec.url_arxiv or ("https://arxiv.org/abs/%s" % rec.arxiv_id),
            "arxiv_pdf_url": pdf_url,
            "arxiv_categories": [],
            "comment": "",
            "doi": rec.doi or "",
            "submission_history": [{
                "version": "v1",
                "date": _yyyymm_to_date(rec.time_start),
            }],
        }

    # openreview 专有字段（与 arxiv_obj 平行的来源对象）
    pd["openreview_obj"] = {
        "forum_id": rec.forum_id,
        "number": rec.number,
        "openreview_url": rec.url_or,
        "openreview_pdf": rec.openreview_pdf,
        "venue": venue_label,
        "presentation_type": rec.presentation_type,
        "primary_area": rec.primary_area,
        "keywords": list(rec.keywords),
        "authorids": list(rec.authorids),
        "first_author_hp": rec.first_author_hp,
        "affiliations": list(rec.affiliations),
        "s2_paper_id": rec.s2_paper_id,
        "corpus_id": rec.corpus_id,
        "doi": rec.doi,
        "arxiv_id": rec.arxiv_id,
        "auto_extracted": list(rec.auto_extracted),
        "time_start": rec.time_start,
        "time_end": rec.time_end,
    }

    # URLs
    base_urls = {"openreview_url": rec.url_or}
    if rec.url_arxiv:
        base_urls["arxiv_url"] = rec.url_arxiv
    if rec.arxiv_id:
        base_urls["arxiv_pdf_url"] = "https://arxiv.org/pdf/%s" % rec.arxiv_id
    pd["base_urls"] = base_urls

    more_urls = {}
    if rec.url_github:
        more_urls["code"] = rec.url_github
    if rec.url_official:
        more_urls["official"] = rec.url_official
    if rec.openreview_pdf:
        more_urls["openreview_pdf"] = rec.openreview_pdf
    if rec.url_others:
        more_urls["others"] = list(rec.url_others)
    pd["more_urls"] = more_urls

    # 引用数（["<count>@<YYYY.MM.DD>", ...]）
    if rec.cited_by:
        pd["cite_numbers"] = list(rec.cited_by)

    # 论文四要素（仅在 LLM 抽取开启且命中时有值）
    if rec.baselines:
        pd["baselines"] = list(rec.baselines)
    if rec.benchmarks:
        pd["benchmarks"] = list(rec.benchmarks)
    if rec.metrics:
        pd["metrics"] = list(rec.metrics)

    # 瞬时挂载原始记录（pipeline 写 vault 后会弹出，绝不入库）
    pd["_openreview_record"] = rec
    return pd


def _yyyymm_to_date(ym: Optional[str]) -> str:
    """'202406' -> '2024-06-01'；无法解析时返回空串。"""
    if ym and len(ym) >= 6 and ym[:6].isdigit():
        return "%s-%s-01" % (ym[:4], ym[4:6])
    return ""


class OpenReviewCrawler(BaseCrawler):
    """使用移植的 OpenReview 引擎抓取某个 venue，并产出符合 paper_schema 的 paper_data。"""

    def __init__(
        self,
        venue,
        *,
        api="auto",
        categories="accepted",
        enrich=orc.ENRICH_DEFAULT,
        github=orc.GITHUB_DEFAULT,
        profiles=orc.PROFILES_DEFAULT,
        affiliations_all=True,
        s2_title_fallback=orc.S2_TITLE_FALLBACK_DEFAULT,
        cited_history=orc.CITED_HISTORY_DEFAULT,
        cited_cadence=3,
        llm_extract=orc.LLM_EXTRACT_DEFAULT,
        llm_provider=orc.LLM_PROVIDER_DEFAULT,
        llm_model=None,
        llm_api_key=None,
        llm_base_url=None,
        llm_source="pdf",
        llm_passes=3,
        username=None,
        password=None,
        s2_api_key=None,
        mailto=None,
        creator=orc.CREATOR_DEFAULT,
        limit=0,
        ids=None,
        as_of=None,
        out=orc.VAULT_DIR_DEFAULT,
        name_len=80,
        force=False,
        refresh_body=False,
        dry_run=False,
        intervals=None,
        min_sims=None,
    ):
        import datetime as _dt

        intervals = {**orc.THROTTLES, **(intervals or {})}
        min_sims = {**orc.MIN_SIMS, **(min_sims or {})}

        self.venue = venue
        self.cfg = SimpleNamespace(
            venue=venue,
            api=api,
            categories=categories,
            enrich=enrich,
            github=github,
            profiles=profiles,
            affiliations_all=affiliations_all,
            s2_title_fallback=s2_title_fallback,
            cited_history=cited_history,
            cited_cadence=cited_cadence,
            llm_extract=llm_extract,
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_source=llm_source,
            llm_passes=llm_passes,
            username=username if username is not None else orc.env_openreview_username(),
            password=password if password is not None else orc.env_openreview_password(),
            s2_api_key=s2_api_key if s2_api_key is not None else orc.env_s2_api_key(),
            mailto=mailto if mailto is not None else orc.env_mailto(),
            creator=creator,
            limit=limit,
            ids=ids,
            as_of=as_of or _dt.date.today(),
            out=out,
            # 单 venue 的 vault 子目录（与上游一致：根目录/venue_slug）
            out_venue_dir=_venue_out_dir(out, venue),
            name_len=name_len,
            force=force,
            refresh_body=refresh_body,
            dry_run=dry_run,
            # throttles
            arxiv_interval=intervals["arxiv"],
            s2_interval=intervals["s2"],
            pwc_interval=intervals["pwc"],
            profile_interval=intervals["profile"],
            openalex_interval=intervals["openalex"],
            llm_interval=intervals["llm"],
            # min similarities
            arxiv_min_sim=min_sims["arxiv"],
            openalex_min_sim=min_sims["openalex"],
        )

        # 抓取后填充，供 pipeline 写 vault 使用
        self.records: List = []
        self.source = None
        self.api_version: Optional[str] = None

    def crawl(self, start_date=None, end_date=None):
        """连接并抓取一个 venue。start_date/end_date 对 OpenReview 不适用（按 venue 抓全量），
        保留参数仅为符合 BaseCrawler 接口。"""
        print(f"🚀 [bold]OpenReview[/bold] crawling venue=[cyan]{self.venue}[/cyan] "
              f"(enrich={self.cfg.enrich}, profiles={self.cfg.profiles}, "
              f"llm_extract={self.cfg.llm_extract})")

        records, source = collect_records(self.cfg)
        self.records = records
        self.source = source
        self.api_version = getattr(source, "version", None)

        venue_fallback = venue_label_from_id(self.venue)
        for rec in records:
            if not rec.title or not normalize_title(rec.title):
                print(f"⚠️ Skipping note {rec.forum_id}: empty/whitespace title (cannot make _id).")
                continue
            venue_label = rec.accept_by or venue_fallback
            paper_data = record_to_paper_data(rec, venue_label)
            yield paper_data, venue_label


def _venue_out_dir(out_root: str, venue: str) -> str:
    """vault 根目录下的 venue 子目录（与上游 slug 规则一致）。"""
    import os

    from ai4research.data_pipeline.crawlers.openreview.helpers import slugify
    return os.path.join(out_root, slugify(venue.replace("/", "_"), 120))
