"""
可选的 Obsidian Markdown “论文画像”输出（从 openreview_scraper.py 原样移植）。

主存储是 MongoDB；当开启 ``--vault`` 时，这里把每篇论文额外写为一个 .md 文件
（YAML frontmatter + 正文），并维护一个 ``_index.json``。重复运行是幂等的：
人工维护字段（aliases / tags / Baselines / ...）被保留，CitedBy 追加新的时间戳快照，
EditLogs 追加一条更新记录，手写的正文 Notes 不会被覆盖。
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from collections import OrderedDict
from typing import Any, Dict, List, Tuple

from ai4research.data_pipeline.crawlers.openreview.helpers import dt_to_dot, log, slugify
from ai4research.data_pipeline.crawlers.openreview.record import MANUAL_KEYS, PaperRecord

# --------------------------------------------------------------------------- #
# Optional dependency: pyyaml (falls back to a self-contained emitter/parser)
# --------------------------------------------------------------------------- #
try:
    import yaml  # type: ignore
    _HAS_YAML = True
except Exception:  # pragma: no cover
    yaml = None  # type: ignore
    _HAS_YAML = False


# =========================================================================== #
# Frontmatter read / write (pyyaml if available, else self-contained)
# =========================================================================== #
def _yaml_quote(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


_PLAIN_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _emit_key(k: str) -> str:
    return k if _PLAIN_KEY.match(k) else _yaml_quote(k)


def _emit_scalar(v: Any) -> str:
    if v is None:
        return '""'
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    s = str(v)
    if s == "":
        return '""'
    return _yaml_quote(s)


if _HAS_YAML:
    # Register an OrderedDict representer ONCE at import (re-registering a fresh
    # subclass on every call would leak representers and grow the registry).
    yaml.SafeDumper.add_representer(
        OrderedDict,
        lambda dumper, data: dumper.represent_mapping(
            "tag:yaml.org,2002:map", data.items()))


def emit_frontmatter(items: "OrderedDict[str, Any]") -> str:
    """Serialise an ordered mapping to a YAML frontmatter block (no fences)."""
    if _HAS_YAML:
        try:
            return yaml.safe_dump(OrderedDict(items), allow_unicode=True, sort_keys=False,
                                  default_flow_style=False, width=4096).rstrip("\n")
        except Exception as exc:
            log.debug("pyyaml dump failed (%s); using builtin emitter", exc)
    lines: List[str] = []
    for k, v in items.items():
        key = _emit_key(k)
        if isinstance(v, (list, tuple)):
            if len(v) == 0:
                lines.append("%s: []" % key)
            else:
                lines.append("%s:" % key)
                for item in v:
                    lines.append("  - %s" % _emit_scalar(item))
        else:
            lines.append("%s: %s" % (key, _emit_scalar(v)))
    return "\n".join(lines)


def parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """Return (frontmatter_dict, body). Robust to missing/invalid frontmatter."""
    if not text.startswith("---"):
        return {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, flags=re.DOTALL)
    if not m:
        return {}, text
    fm_text, body = m.group(1), m.group(2)
    if _HAS_YAML:
        try:
            data = yaml.safe_load(fm_text)
            if isinstance(data, dict):
                return data, body
        except Exception as exc:
            log.debug("pyyaml load failed (%s); using builtin parser", exc)
    # builtin tolerant parser (scalars + block lists only)
    data: Dict[str, Any] = {}
    cur_key = None
    for raw in fm_text.splitlines():
        if not raw.strip():
            continue
        if raw.lstrip().startswith("- ") and cur_key is not None:
            data.setdefault(cur_key, [])
            if isinstance(data[cur_key], list):
                data[cur_key].append(_unquote(raw.lstrip()[2:].strip()))
            continue
        mk = re.match(r"^([^:]+):\s*(.*)$", raw)
        if not mk:
            continue
        key = _unquote(mk.group(1).strip())
        val = mk.group(2).strip()
        if val == "":
            data[key] = []          # assume an upcoming block list
            cur_key = key
        elif val == "[]":
            data[key] = []
            cur_key = None
        else:
            data[key] = _unquote(val)
            cur_key = None
    return data, body


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        inner = s[1:-1]
        if s[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        elif s[0] == "'":
            # YAML single-quoted style escapes a literal apostrophe by doubling it.
            inner = inner.replace("''", "'")
        return inner
    return s


# =========================================================================== #
# Writing notes (idempotent merge)
# =========================================================================== #
def merge_existing(items: "OrderedDict[str, Any]", existing_fm: Dict[str, Any],
                   run_date: _dt.date) -> "OrderedDict[str, Any]":
    """Preserve human-curated fields; append CitedBy snapshot & EditLogs update."""
    merged = OrderedDict(items)

    # 1) preserve manual fields entirely
    for k in MANUAL_KEYS:
        if k in existing_fm and existing_fm.get(k) not in (None, "", []):
            merged[k] = existing_fm[k]

    # 2) make scraped/enriched fields STICKY: fall back to the existing saved
    #    value whenever this run produced nothing for it (a non-enriched re-run,
    #    or a transient enrichment/profile failure, or a hand-set url). Treats
    #    "" and [] as absent. This is what makes enrichment additive instead of
    #    destructive and keeps re-runs idempotent under the flaky network.
    for k in ("url(arXiv)", "url(Github)", "url(Official)",
              "1stAuthorHP", "Affiliations", "Authors"):
        if not merged.get(k) and existing_fm.get(k):
            merged[k] = existing_fm[k]

    # 2b) url(Others): union freshly-derived links with existing (incl. any the
    #     user hand-added), preserving order and de-duplicating.
    fresh_others = list(merged.get("url(Others)") or [])
    old_others = existing_fm.get("url(Others)") or []
    if isinstance(old_others, str):
        old_others = [old_others]
    seen_u, unioned = set(), []
    for u in fresh_others + list(old_others):
        if u and u not in seen_u:
            seen_u.add(u)
            unioned.append(u)
    merged["url(Others)"] = unioned

    # 2c) dates: OR-derived dates are a weak fallback. If THIS run found no arXiv
    #     URL (it was just inherited from the existing note), the existing note's
    #     dates are the arXiv-authoritative ones — keep them rather than clobbering
    #     with OR cdate/pdate. `items` (not `merged`) reflects what THIS run found.
    if not items.get("url(arXiv)") and existing_fm.get("url(arXiv)"):
        for k in ("time_start", "time_end"):
            if existing_fm.get(k):
                merged[k] = existing_fm[k]

    # 3) CitedBy: keep history, append today's snapshot if it's new
    old_cited = existing_fm.get("CitedBy") or []
    if isinstance(old_cited, str):
        old_cited = [old_cited]
    new_snaps = merged.get("CitedBy") or []
    combined = list(old_cited)
    for snap in new_snaps:
        snap_date = snap.split("@")[-1] if "@" in snap else None
        # replace an existing snapshot from the same date, else append
        existing_dates = {s.split("@")[-1] for s in combined if "@" in s}
        if snap_date in existing_dates:
            combined = [s for s in combined if s.split("@")[-1] != snap_date] + [snap]
        elif snap not in combined:
            combined.append(snap)
    merged["CitedBy"] = combined

    # 4) EditLogs: preserve creation, append an update entry for today
    old_logs = existing_fm.get("EditLogs") or []
    if isinstance(old_logs, str):
        old_logs = [old_logs]
    today = dt_to_dot(run_date)
    logs = list(old_logs)
    if not any(l.startswith(today) for l in logs):
        logs.append("%s更新" % today)
    merged["EditLogs"] = logs
    return merged


def render_body(rec: PaperRecord) -> str:
    lines: List[str] = []
    lines.append("# %s" % (rec.title or "Untitled"))
    lines.append("")
    if rec.tldr:
        lines.append("> [!tldr] TL;DR")
        lines.append("> %s" % rec.tldr.replace("\n", " "))
        lines.append("")
    if rec.authors:
        lines.append("**Authors:** " + ", ".join(rec.authors))
        lines.append("")
    if rec.abstract:
        lines.append("## Abstract")
        lines.append("")
        lines.append(rec.abstract)
        lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("<!-- your notes here; this section is preserved on re-scrape -->")
    lines.append("")
    return "\n".join(lines)


def write_note(rec: PaperRecord, out_dir: str, run_date: _dt.date, cfg) -> Tuple[str, str]:
    """Write/merge one markdown note. Returns (path, action)."""
    os.makedirs(out_dir, exist_ok=True)
    fname = "%s__%s.md" % (slugify(rec.title, cfg.name_len), rec.forum_id)
    path = os.path.join(out_dir, fname)

    items = rec.schema_items()
    # creation log (only used when the file is new)
    items["EditLogs"] = ["%s创建" % dt_to_dot(run_date)]

    existing_body = None
    action = "create"
    if os.path.exists(path):
        action = "update"
        try:
            with open(path, "r", encoding="utf-8") as fh:
                old_text = fh.read()
            existing_fm, existing_body = parse_frontmatter(old_text)
            if not existing_fm and not cfg.force:
                log.warning("could not parse existing frontmatter, skipping (use --force): %s",
                            path)
                return path, "skipped-unparseable"
            items = merge_existing(items, existing_fm, run_date)
        except Exception as exc:
            log.warning("failed to merge existing note %s: %s", path, exc)
            if not cfg.force:
                return path, "skipped-error"

    # append provenance extras below the schema block
    full = OrderedDict(items)
    for k, v in rec.extra_items().items():
        full[k] = v

    fm = emit_frontmatter(full)
    body = existing_body if (action == "update" and existing_body and not cfg.refresh_body) \
        else render_body(rec)
    content = "---\n%s\n---\n\n%s" % (fm, body.lstrip("\n"))

    if cfg.dry_run:
        return path, action + "-dry"

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.replace(tmp, path)
    return path, action


def write_vault(records: List[PaperRecord], venue: str, api_version: str,
                cfg) -> Dict[str, int]:
    """把所有 records 写为 Markdown 笔记并维护 _index.json。返回各动作计数。

    cfg 需要提供：out（vault 根目录）、out_venue_dir（本 venue 子目录）、
    name_len、force、refresh_body、dry_run、as_of。
    """
    counts = {"create": 0, "update": 0, "other": 0}
    out_dir = cfg.out_venue_dir
    run_date = cfg.as_of
    index: List[Dict[str, Any]] = []
    for rec in records:
        path, action = write_note(rec, out_dir, run_date, cfg)
        base = action.split("-")[0]
        counts[base] = counts.get(base, 0) + 1
        index.append({
            "title": rec.title,
            "forum_id": rec.forum_id,
            "file": os.path.relpath(path, cfg.out),
            "accept_by": rec.accept_by,
            "presentation_type": rec.presentation_type,
            "arxiv_id": rec.arxiv_id,
            "doi": rec.doi,
            "cited_by": rec.cited_by,
            "category": getattr(rec, "_category", "accepted"),
        })
        log.debug("%s %s", action, path)

    # write index (skipped on --dry-run so a dry run writes nothing at all)
    index_path = os.path.join(out_dir, "_index.json")
    if not cfg.dry_run:
        os.makedirs(out_dir, exist_ok=True)
        with open(index_path, "w", encoding="utf-8") as fh:
            json.dump({
                "venue": venue,
                "scraped_at": run_date.isoformat(),
                "api_version": api_version,
                "count": len(index),
                "papers": index,
            }, fh, ensure_ascii=False, indent=2)
    log.info("Vault: created=%d updated=%d other=%d -> %s",
             counts.get("create", 0), counts.get("update", 0), counts.get("other", 0), out_dir)
    return counts
