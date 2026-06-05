"""
LLM 辅助抽取 Baselines / Benchmarks / Metrics（从 openreview_scraper.py 原样移植）。

这三个字段不在 OpenReview 的结构化元数据里，只能让 LLM 通读论文（PDF）后抽取，
因此结果会被标记为 ``auto_extracted`` 供人工复核。

本客户端有意保持「多 provider 的原始 HTTP 实现」（claude-cli / anthropic / openai /
deepseek / openrouter / openai-compatible），以便在不同后端间切换；其中 anthropic 的
默认模型已是当前的 `claude-sonnet-4-6`，默认 provider 为本机 `claude-cli`（走 Claude
订阅、无需 API key）。因此这里**不**改写为 Anthropic 官方 SDK（多 provider 客户端不应
被强制绑定到单一 SDK）。
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import requests

from ai4research.data_pipeline.crawlers.openreview.helpers import JsonCache, Throttle, log


# These three fields are NOT in OpenReview's structured metadata and the one
# structured database that had them (Papers-with-Code) is shut down. They live
# in the paper's experiments section and result tables, so the only automated
# path is to have an LLM read the full PDF. This is assisted extraction (it can
# omit or over-include), so results are flagged `auto_extracted` for human review
# — never presented as rigorously-scraped facts like title/authors/venue.
class LLMExtractClient:
    """Provider-pluggable extractor. Backends:
      * claude-cli  — the local `claude` CLI, i.e. your Claude *subscription* (no API key);
                      it reads the PDF itself via its Read tool.
      * anthropic   — Anthropic Messages API (key); sends the PDF natively (base64).
      * openai / deepseek / openai-compatible — any OpenAI-style /chat/completions
                      endpoint (key + base_url); sends extracted PDF text in JSON mode.
    All backends share one grounded prompt + schema, so results are consistent.
    """

    # provider -> (default base_url, default model, api-key env var)
    PROVIDERS = {
        "claude-cli":        (None, None, None),
        "anthropic":         ("https://api.anthropic.com/v1", "claude-sonnet-4-6", "ANTHROPIC_API_KEY"),
        "openai":            ("https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
        "deepseek":          ("https://api.deepseek.com", "deepseek-chat", "DEEPSEEK_API_KEY"),
        "openrouter":        ("https://openrouter.ai/api/v1", "deepseek/deepseek-v4-pro", "OPENROUTER_API_KEY"),
        "openai-compatible": (None, None, "LLM_API_KEY"),
    }
    ANTHROPIC_VERSION = "2023-06-01"
    TOOL = {
        "name": "record_paper_components",
        "description": "Record the baselines, benchmarks/datasets, and evaluation "
                       "metrics that THIS paper actually uses in its experiments.",
        "input_schema": {
            "type": "object",
            "properties": {
                "baselines": {"type": "array", "items": {"type": "string"}},
                "benchmarks": {"type": "array", "items": {"type": "string"}},
                "metrics": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["baselines", "benchmarks", "metrics"],
        },
    }
    PROMPT = (
        "You are extracting structured metadata from ONE research paper. Look ONLY at THIS "
        "paper's OWN experiments — its results tables and results figures (captions, legends, "
        "axis labels included). Be thorough within that scope: missing a real item is as bad "
        "as inventing one, but do NOT include things that are only cited or discussed in the "
        "introduction/related-work and never actually run in the experiments.\n"
        "- baselines: the prior methods/models/algorithms/codecs that THIS paper EMPIRICALLY "
        "COMPARES ITS OWN METHOD AGAINST (i.e. they appear as competing rows/curves in its "
        "results tables or plots). EXCLUDE the paper's own proposed method and its ablations, "
        "and EXCLUDE methods merely mentioned in related work but not run.\n"
        "- benchmarks: the datasets/benchmarks it actually EVALUATES ON (toy/synthetic count).\n"
        "- metrics: every evaluation metric it REPORTS in a results table or figure — include "
        "likelihood/rate metrics (e.g. NELBO, ELBO, bits-per-dim/bpd, perplexity) AND quality "
        "metrics (e.g. accuracy, F1, mAP, PSNR, SSIM, FID, BLEU, win rate). A quantity plotted "
        "on a results-figure axis counts.\n"
        "Use ONE canonical short name per item (e.g. 'CIFAR-10', not also 'CIFAR10'). Do NOT "
        "invent items absent from the paper, and do NOT list the same item twice."
    )
    JSON_INSTRUCTION = (
        '\n\nRespond with ONLY a JSON object, no prose, exactly:\n'
        '{"baselines": ["..."], "benchmarks": ["..."], "metrics": ["..."]}'
    )

    def __init__(self, session: requests.Session, provider: str, model: Optional[str],
                 api_key: Optional[str], base_url: Optional[str], cache: JsonCache,
                 throttle: Throttle, source: str = "pdf",
                 max_pdf_bytes: int = 28 * 1024 * 1024, cli_bin: str = "claude",
                 timeout: int = 180, passes: int = 3):
        if provider not in self.PROVIDERS:
            raise ValueError("unknown --llm-provider %r (choices: %s)"
                             % (provider, ", ".join(self.PROVIDERS)))
        d_base, d_model, key_env = self.PROVIDERS[provider]
        self.session = session
        self.provider = provider
        self.model = model or d_model
        self.base_url = (base_url or d_base or "").rstrip("/")
        self.api_key = api_key or (os.environ.get(key_env) if key_env else None)
        self.cache = cache
        self.throttle = throttle
        self.source = source
        self.max_pdf_bytes = max_pdf_bytes
        self.cli_bin = cli_bin
        self.timeout = timeout
        self.passes = max(1, int(passes))           # self-consistency: union over N passes

    # -- availability check -------------------------------------------------
    def available(self) -> Tuple[bool, str]:
        if self.provider == "claude-cli":
            import shutil
            if not shutil.which(self.cli_bin):
                return False, "the `%s` CLI is not on PATH" % self.cli_bin
            return True, ""
        if not self.api_key:
            return False, "no API key (set the provider's *_API_KEY env or --llm-api-key)"
        if not self.base_url:
            return False, "no base URL (set --llm-base-url for openai-compatible)"
        if not self.model:
            return False, "no model (set --llm-model)"
        return True, ""

    # -- PDF helpers --------------------------------------------------------
    def _pdf_bytes(self, rec) -> Optional[bytes]:
        if not rec.openreview_pdf:
            return None
        try:
            self.throttle.wait()
            r = self.session.get(rec.openreview_pdf, timeout=90)
            if r.status_code == 200 and r.content[:5] == b"%PDF-" \
                    and len(r.content) <= self.max_pdf_bytes:
                return r.content
        except Exception as exc:
            log.debug("pdf fetch failed for %s: %s", rec.forum_id, exc)
        return None

    @staticmethod
    def _pdf_to_text(pdf: bytes) -> str:
        """Best-effort PDF -> text (pypdf, else `pdftotext`, else '')."""
        try:
            import io, pypdf  # type: ignore
            reader = pypdf.PdfReader(io.BytesIO(pdf))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception:
            pass
        try:
            import subprocess, tempfile, shutil
            if shutil.which("pdftotext"):
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
                    fh.write(pdf)
                    path = fh.name
                out = subprocess.run(["pdftotext", "-q", path, "-"], capture_output=True,
                                     timeout=120)
                os.unlink(path)
                return out.stdout.decode("utf-8", "ignore")
        except Exception:
            pass
        return ""

    def _paper_text(self, rec) -> Optional[str]:
        """Plain-text paper content for text-only providers (full PDF, else abstract)."""
        text = ""
        if self.source == "pdf":
            pdf = self._pdf_bytes(rec)
            if pdf:
                text = self._pdf_to_text(pdf)
        if len(text) < 500:                       # PDF parse failed/empty -> abstract
            if not rec.abstract:
                return None
            text = "Title: %s\n\nTL;DR: %s\n\nAbstract: %s" % (rec.title, rec.tldr, rec.abstract)
        return text[:120000]                      # keep prompts bounded

    # -- response parsing ---------------------------------------------------
    @classmethod
    def _normalize(cls, obj: Any) -> Optional[Dict[str, List[str]]]:
        if not isinstance(obj, dict):
            return None
        return {k: [str(x).strip() for x in (obj.get(k) or []) if str(x).strip()]
                for k in ("baselines", "benchmarks", "metrics")}

    @staticmethod
    def _extract_json(s: str) -> Optional[Dict[str, Any]]:
        if not s:
            return None
        # last balanced {...} object in the string
        depth = 0
        start = -1
        best = None
        for i, ch in enumerate(s):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    best = s[start:i + 1]
        if not best:
            return None
        try:
            return json.loads(best)
        except Exception:
            return None

    # -- providers ----------------------------------------------------------
    def _call_anthropic(self, rec, temperature: float = 0.0) -> Optional[Dict[str, List[str]]]:
        content: List[Dict[str, Any]] = []
        if self.source == "pdf":
            pdf = self._pdf_bytes(rec)
            if pdf:
                import base64
                content.append({"type": "document", "source": {
                    "type": "base64", "media_type": "application/pdf",
                    "data": base64.standard_b64encode(pdf).decode("ascii")}})
        if not content:
            if not rec.abstract:
                return None
            content.append({"type": "text", "text":
                            "Title: %s\n\nAbstract: %s" % (rec.title, rec.abstract)})
        content.append({"type": "text", "text": self.PROMPT})
        payload = {"model": self.model, "max_tokens": 1024, "temperature": temperature,
                   "tools": [self.TOOL],
                   "tool_choice": {"type": "tool", "name": self.TOOL["name"]},
                   "messages": [{"role": "user", "content": content}]}
        self.throttle.wait()
        r = self.session.post(self.base_url + "/messages",
                              headers={"x-api-key": self.api_key,
                                       "anthropic-version": self.ANTHROPIC_VERSION,
                                       "content-type": "application/json"},
                              data=json.dumps(payload), timeout=self.timeout)
        if r.status_code != 200:
            log.warning("anthropic http %s for %s: %s", r.status_code, rec.forum_id, r.text[:160])
            return None
        for block in r.json().get("content", []) or []:
            if block.get("type") == "tool_use":
                return self._normalize(block.get("input"))
        return None

    def _call_openai_compat(self, rec, temperature: float = 0.0) -> Optional[Dict[str, List[str]]]:
        text = self._paper_text(rec)
        if not text:
            return None
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.PROMPT + self.JSON_INSTRUCTION},
                {"role": "user", "content": "PAPER:\n\n" + text},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "max_tokens": 1024,
        }
        headers = {"Authorization": "Bearer %s" % self.api_key,
                   "content-type": "application/json"}
        if self.provider == "openrouter":
            # optional OpenRouter attribution headers (used for its app rankings)
            headers["HTTP-Referer"] = "https://github.com/openreview-scraper"
            headers["X-Title"] = "OpenReview Scraper"
        self.throttle.wait()
        r = self.session.post(self.base_url + "/chat/completions",
                              headers=headers,
                              data=json.dumps(payload), timeout=self.timeout)
        if r.status_code != 200:
            log.warning("%s http %s for %s: %s", self.provider, r.status_code, rec.forum_id,
                        r.text[:160])
            return None
        try:
            msg = r.json()["choices"][0]["message"]["content"]
        except Exception:
            return None
        return self._normalize(self._extract_json(msg))

    def _call_claude_cli(self, rec) -> Optional[Dict[str, List[str]]]:
        """Drive the local `claude` CLI (the user's Claude subscription) as a pure
        text->JSON completion: feed the paper TEXT on stdin with ALL tools disabled.

        We deliberately do NOT have the CLI Read the PDF itself, and do NOT pass
        `--permission-mode bypassPermissions`:
          * no tool use  -> no permission prompt and no file side-channel are needed;
          * `--tools ""` keeps it a one-shot text generation (the reliable headless
            path — the tool-enabled path is fragile and, when `claude -p` is spawned
            from inside another Claude Code session, currently crashes in the CLI with
            "TypeError: ... 'effortLevel'"). At a normal top-level shell this runs fine.
        The PDF is turned into text exactly like the OpenAI/DeepSeek providers
        (`_paper_text`: pypdf/pdftotext, else the abstract)."""
        import subprocess
        text = self._paper_text(rec)
        if not text:
            return None
        prompt = self.PROMPT + self.JSON_INSTRUCTION + "\n\nPAPER:\n\n" + text
        cmd = [self.cli_bin, "-p",
               "--tools", "",                       # no tools => pure text, no permissions
               "--no-session-persistence",          # don't create/lock a session file
               "--output-format", "text"]
        if self.model:
            cmd += ["--model", self.model]
        try:
            self.throttle.wait()
            out = subprocess.run(cmd, input=prompt.encode("utf-8"),
                                 capture_output=True, timeout=self.timeout)
            txt = out.stdout.decode("utf-8", "ignore")
        except Exception as exc:
            log.warning("claude-cli failed for %s: %s", rec.forum_id, exc)
            return None
        parsed = self._extract_json(txt)
        if parsed is None and "Execution error" in txt:
            log.warning("claude-cli returned an execution error for %s (CLI/env issue; "
                        "try updating `claude`, or use --llm-provider anthropic).",
                        rec.forum_id)
            return None
        return self._normalize(parsed)

    def _call_once(self, rec, temperature: float) -> Optional[Dict[str, List[str]]]:
        if self.provider == "anthropic":
            return self._call_anthropic(rec, temperature)
        elif self.provider == "claude-cli":
            return self._call_claude_cli(rec)       # CLI text mode: temperature not plumbed
        return self._call_openai_compat(rec, temperature)

    @staticmethod
    def _dedup_key(s: str) -> str:
        """Punctuation/spacing/case-insensitive key so union passes don't keep variants
        of one item (e.g. 'CIFAR-10' == 'CIFAR10', 'ImageNet 64x64' == 'ImageNet-64x64')."""
        return re.sub(r"[^a-z0-9]+", "", str(s).lower())

    # -- public -------------------------------------------------------------
    def extract(self, rec) -> Optional[Dict[str, List[str]]]:
        """Self-consistency extraction: run `passes` independent passes and UNION their
        items (deduped by a punctuation-insensitive key). A single pass under-recalls and
        (for MoE models) varies run-to-run even at temperature 0 — e.g. dropping a metric
        that is plainly in a figure. Unioning a few grounded passes recovers those misses;
        the precision-focused prompt ('experiments only, not related work') keeps the union
        from drifting into cited-but-unused methods. Pass 0 runs at temperature 0 (stable
        base); extra passes use a small temperature purely to diversify coverage."""
        ck = "llm::%s::%s::%s::p%d::%s" % (self.provider, self.model or "_", self.source,
                                           self.passes, rec.forum_id)
        if ck in self.cache:
            return self.cache.get(ck) or None
        keys = ("baselines", "benchmarks", "metrics")
        merged: Dict[str, List[str]] = {k: [] for k in keys}
        seen: Dict[str, set] = {k: set() for k in keys}
        got_any = False
        for p in range(self.passes):
            try:
                out = self._call_once(rec, temperature=(0.0 if p == 0 else 0.2))
            except Exception as exc:
                log.warning("llm extract failed for %s (pass %d): %s", rec.forum_id, p, exc)
                continue                           # transient: skip this pass
            if out is None:
                continue
            got_any = True
            for k in keys:
                for item in out.get(k) or []:
                    key = self._dedup_key(item)
                    if key and key not in seen[k]:
                        seen[k].add(key)
                        merged[k].append(item)
        if not got_any:
            return None                            # every pass errored: don't cache
        self.cache.set(ck, merged)
        return merged
