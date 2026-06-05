"""
OpenReview 数据源配置：默认 venue、默认富化档位、限流间隔、相似度阈值，
以及各外部服务读取的环境变量名。

说明：
- OpenReview 匿名即可抓取；提供账号（环境变量 OPENREVIEW_USERNAME / OPENREVIEW_PASSWORD）
  只是为了更快地批量解析作者画像。
- 各外部 API key 均为可选，通过环境变量读取（与上游一致，不引入新依赖）。
- 默认档位为「Full + LLM 抽取」：开启 arXiv / Semantic Scholar / 作者画像 / GitHub /
  OpenAlex 引用历史 / LLM 抽取（默认 provider 为本机 `claude-cli`，走 Claude 订阅、无需 key）。
"""

import os

# 默认抓取的 venue（可在 CLI 用 --venue 覆盖）
DEFAULT_VENUES = [
    "ICLR.cc/2026/Conference",
]

# 富化默认档位（用户选择：Full + LLM extraction）
ENRICH_DEFAULT = "all"           # none | arxiv | s2 | all
GITHUB_DEFAULT = True            # Papers-with-Code 找官方 GitHub（需要 arXiv id）
PROFILES_DEFAULT = True          # 解析作者主页 / 单位
S2_TITLE_FALLBACK_DEFAULT = True  # 没有 arXiv id 时用标题匹配 Semantic Scholar
CITED_HISTORY_DEFAULT = True     # OpenAlex 多时间戳引用历史
LLM_EXTRACT_DEFAULT = True       # LLM 抽取 Baselines / Benchmarks / Metrics
LLM_PROVIDER_DEFAULT = "claude-cli"  # 本机 Claude 订阅（无需 API key）

CREATOR_DEFAULT = "agent4research-openreview"

# vault（Markdown 论文画像）输出根目录；缓存放在 <vault>/.cache 下
VAULT_DIR_DEFAULT = "openreview_vault"

# 各外部源的最小调用间隔（秒）—— 与上游默认一致
THROTTLES = {
    "arxiv": 3.0,
    "s2": 1.1,
    "pwc": 1.0,
    "profile": 3.2,     # OpenReview 匿名用户约 20 次/分钟
    "openalex": 0.12,   # polite pool 约 10 次/秒
    "llm": 0.3,
}

# 标题匹配的最小相似度
MIN_SIMS = {
    "arxiv": 0.9,
    "openalex": 0.9,
}

# 环境变量名（仅作记录/文档用途；实际读取见下方 env_* 函数）
ENV_VARS = {
    "openreview_username": "OPENREVIEW_USERNAME",
    "openreview_password": "OPENREVIEW_PASSWORD",
    "semantic_scholar_api_key": "SEMANTIC_SCHOLAR_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "mailto": "SCRAPER_MAILTO",
}


def env_openreview_username():
    return os.environ.get(ENV_VARS["openreview_username"])


def env_openreview_password():
    return os.environ.get(ENV_VARS["openreview_password"])


def env_s2_api_key():
    return os.environ.get(ENV_VARS["semantic_scholar_api_key"])


def env_mailto():
    return os.environ.get(ENV_VARS["mailto"], "")
