"""
OpenReview 抓取 CLI 入口（对标 crawl_arxiv_daily.py）。

示例：
    cd ~
    # 冒烟测试（不写库、不富化、只抓 3 篇）
    python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
        --venue ICLR.cc/2026/Conference --enrich none --no-llm-extract --limit 3 --dry-run

    # 小规模真实入库（默认 Full + LLM 抽取）
    python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
        --venue ICLR.cc/2026/Conference --limit 3

完整选项见 `--help`。
"""

import argparse

from rich import print

from ai4research.data_pipeline.db_settings.mongo_client import MongoDBClient
from ai4research.data_pipeline.pipelines.openreview_venue import crawl_openreview
from ai4research.data_pipeline.source_configs import openreview_config as orc


def _add_bool(parser, name, default, help_text):
    """添加一个 --name / --no-name 布尔开关（默认值来自配置）。"""
    parser.add_argument(
        "--%s" % name,
        dest=name.replace("-", "_"),
        action=argparse.BooleanOptionalAction,
        default=default,
        help=help_text,
    )


def build_parser():
    p = argparse.ArgumentParser(
        description="把一个 OpenReview venue 抓取并写入 MongoDB（可选同时输出 Markdown vault）。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--venue", default=orc.DEFAULT_VENUES[0],
                   help="OpenReview venue id，例如 ICLR.cc/2026/Conference")
    p.add_argument("--api", choices=["auto", "1", "2"], default="auto",
                   help="OpenReview API 版本（默认 auto 自动探测）")
    p.add_argument("--categories", default="accepted",
                   help="'accepted' | 'all' | 逗号分隔的 "
                        "accepted,withdrawn,desk_rejected,rejected,submission")
    p.add_argument("--limit", type=int, default=0, help="最多处理 N 篇（0=全部）")
    p.add_argument("--ids", default=None,
                   help="逗号分隔的 forum/note id（只抓这些，--venue 仍用于选择 API 版本）")

    # 富化（默认 Full + LLM）
    p.add_argument("--enrich", choices=["none", "arxiv", "s2", "all"],
                   default=orc.ENRICH_DEFAULT,
                   help="外部富化档位：arXiv 和/或 Semantic Scholar")
    _add_bool(p, "github", orc.GITHUB_DEFAULT,
              "通过 Papers-with-Code 找官方 GitHub（需要 arXiv id）")
    _add_bool(p, "profiles", orc.PROFILES_DEFAULT,
              "解析作者主页 + 单位（OpenReview 画像）")
    _add_bool(p, "affiliations-all", True,
              "解析全部作者的单位（关闭则只解析第一作者）")
    _add_bool(p, "s2-title-fallback", orc.S2_TITLE_FALLBACK_DEFAULT,
              "没有 arXiv id 时用标题匹配 Semantic Scholar（慢）")
    _add_bool(p, "cited-history", orc.CITED_HISTORY_DEFAULT,
              "用 OpenAlex 重建多时间戳 CitedBy 序列")
    p.add_argument("--cited-cadence", type=int, default=3,
                   help="CitedBy 快照间隔（月）")

    # LLM 抽取
    _add_bool(p, "llm-extract", orc.LLM_EXTRACT_DEFAULT,
              "用 LLM 通读 PDF 抽取 Baselines/Benchmarks/Metrics（标记 auto_extracted）")
    p.add_argument("--llm-provider",
                   choices=["claude-cli", "anthropic", "openai", "deepseek",
                            "openrouter", "openai-compatible"],
                   default=orc.LLM_PROVIDER_DEFAULT,
                   help="LLM 后端：claude-cli 走本机 Claude 订阅（无需 key）；其余用对应 API")
    p.add_argument("--llm-model", default=None, help="模型 id（各 provider 有默认值）")
    p.add_argument("--llm-base-url", default=None, help="API base url（openai-compatible 必填）")
    p.add_argument("--llm-api-key", default=None, help="API key（或用对应 *_API_KEY 环境变量）")
    p.add_argument("--llm-source", choices=["pdf", "abstract"], default="pdf",
                   help="读全文 PDF（准）还是仅摘要（省）")
    p.add_argument("--llm-passes", type=int, default=3,
                   help="自洽抽取的轮数（取并集，默认 3；设 1 提速）")

    # 认证 / key（也可用环境变量）
    p.add_argument("--username", default=None,
                   help="OpenReview 账号（或环境变量 OPENREVIEW_USERNAME）")
    p.add_argument("--password", default=None,
                   help="OpenReview 密码（或环境变量 OPENREVIEW_PASSWORD）")
    p.add_argument("--s2-api-key", default=None,
                   help="Semantic Scholar API key（或环境变量 SEMANTIC_SCHOLAR_API_KEY）")
    p.add_argument("--mailto", default=None,
                   help="礼貌 User-Agent 用的联系邮箱（或环境变量 SCRAPER_MAILTO）")
    p.add_argument("--creator", default=orc.CREATOR_DEFAULT, help="Creator 字段值")

    # 输出 / vault
    _add_bool(p, "vault", False, "额外输出 Markdown 论文画像（vault）")
    p.add_argument("--vault-dir", default=orc.VAULT_DIR_DEFAULT, help="vault 根目录")
    p.add_argument("--as-of", default=None,
                   help="覆盖“今天”（YYYY-MM-DD），用于 CitedBy/EditLogs 的时间戳")

    # 限流
    p.add_argument("--arxiv-interval", type=float, default=orc.THROTTLES["arxiv"])
    p.add_argument("--s2-interval", type=float, default=orc.THROTTLES["s2"])
    p.add_argument("--pwc-interval", type=float, default=orc.THROTTLES["pwc"])
    p.add_argument("--profile-interval", type=float, default=orc.THROTTLES["profile"])
    p.add_argument("--openalex-interval", type=float, default=orc.THROTTLES["openalex"])
    p.add_argument("--llm-interval", type=float, default=orc.THROTTLES["llm"])

    # 行为
    p.add_argument("--dry-run", action="store_true", help="只抓取富化，不写库也不写文件")
    p.add_argument("-v", "--verbose", action="count", default=1,
                   help="-v info（默认），-vv debug")
    p.add_argument("--quiet", action="store_true", help="只输出警告/错误")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    import datetime as _dt

    from ai4research.data_pipeline.crawlers.openreview.helpers import setup_logging
    setup_logging(0 if args.quiet else args.verbose)

    as_of = _dt.date.fromisoformat(args.as_of) if args.as_of else None

    MongoDBClient.ping()
    print("✅ MongoDB connected successfully.")

    crawl_openreview(
        venue=args.venue,
        write_vault=args.vault,
        dry_run=args.dry_run,
        api=args.api,
        categories=args.categories,
        enrich=args.enrich,
        github=args.github,
        profiles=args.profiles,
        affiliations_all=args.affiliations_all,
        s2_title_fallback=args.s2_title_fallback,
        cited_history=args.cited_history,
        cited_cadence=args.cited_cadence,
        llm_extract=args.llm_extract,
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
        llm_base_url=args.llm_base_url,
        llm_api_key=args.llm_api_key,
        llm_source=args.llm_source,
        llm_passes=args.llm_passes,
        username=args.username,
        password=args.password,
        s2_api_key=args.s2_api_key,
        mailto=args.mailto,
        creator=args.creator,
        limit=args.limit,
        ids=args.ids,
        as_of=as_of,
        out=args.vault_dir,
        intervals={
            "arxiv": args.arxiv_interval,
            "s2": args.s2_interval,
            "pwc": args.pwc_interval,
            "profile": args.profile_interval,
            "openalex": args.openalex_interval,
            "llm": args.llm_interval,
        },
    )


if __name__ == "__main__":
    main()
