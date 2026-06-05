"""
OpenReview 抓取引擎（从 StevenWang-CY/openreview-paper-portrait 移植）。

设计说明
--------
本子包把原始的单文件抓取器（``scraper/openreview_scraper.py``，约 2500 行）
按职责拆分为多个模块，类的实现尽量保持与上游一致，以复用其经过实战检验的
网络层（限流 / 重试退避 / 磁盘缓存）与多源富化逻辑：

- ``helpers``    : 通用工具与基础设施（Throttle / JsonCache / 重试 / 文本规范化 / cval）。
- ``source``     : OpenReview v1/v2 客户端、版本自动探测、分类解析、分页抓取、作者主页/单位解析。
- ``enrichment`` : arXiv / Semantic Scholar / Papers-with-Code / OpenAlex 富化客户端。
- ``llm_extract``: 多provider（claude-cli / anthropic / openai / deepseek / openrouter）
                   的 Baselines/Benchmarks/Metrics 抽取（原样移植）。
- ``record``     : PaperRecord 数据类、build_base_record、apply_enrichment、apply_profiles。
- ``vault_writer``: 可选的 Obsidian Markdown “论文画像”输出（frontmatter + 幂等合并）。
- ``collect``    : collect_records —— 完整 run() 编排（连接 → 抓取 → 富化），但不写盘。

上层适配（OpenReviewCrawler、record_to_paper_data 映射、pipeline、CLI）位于
本子包之外，负责把 PaperRecord 映射为 paper_schema.DEFAULT_PAPER_FIELDS 并写入 MongoDB。
"""

from ai4research.data_pipeline.crawlers.openreview.helpers import (
    Throttle,
    JsonCache,
    build_session,
    setup_logging,
    cval,
    norm_title,
    title_similarity,
    slugify,
    ms_to_yyyymm,
    dt_to_dot,
)
from ai4research.data_pipeline.crawlers.openreview.source import (
    OpenReviewSource,
    ProfileResolver,
)
from ai4research.data_pipeline.crawlers.openreview.record import (
    PaperRecord,
    build_base_record,
    apply_enrichment,
    apply_profiles,
)
from ai4research.data_pipeline.crawlers.openreview.collect import collect_records

__all__ = [
    "Throttle",
    "JsonCache",
    "build_session",
    "setup_logging",
    "cval",
    "norm_title",
    "title_similarity",
    "slugify",
    "ms_to_yyyymm",
    "dt_to_dot",
    "OpenReviewSource",
    "ProfileResolver",
    "PaperRecord",
    "build_base_record",
    "apply_enrichment",
    "apply_profiles",
    "collect_records",
]
