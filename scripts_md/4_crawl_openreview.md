# 切换到根目录
cd ~

# ============================================================
# 0. 前置准备
# ============================================================

# 安装依赖（新增 openreview-py；pypdf / PyYAML 为可选）
pip install -r requirements.txt

# schema 已升级到 v2（新增 openreview_obj 字段）。
# 先迁移旧库并重建索引（已有 arXiv 数据会自动补全 openreview_obj 空字段）：
python -m ai4research.data_pipeline.scripts_py.migrate_schema
python -m ai4research.data_pipeline.scripts_py.init_db

# 可选：配置环境变量（都不是必须的）
#   OpenReview 匿名即可抓取；提供账号只是为了更快地批量解析作者画像
export OPENREVIEW_USERNAME="you@example.com"
export OPENREVIEW_PASSWORD="********"
#   Semantic Scholar / LLM 等外部 key（均可选）
export SEMANTIC_SCHOLAR_API_KEY="********"
export ANTHROPIC_API_KEY="********"        # 仅 --llm-provider anthropic 时需要
export SCRAPER_MAILTO="you@example.com"     # OpenAlex 礼貌池联系邮箱

# ============================================================
# 1. 冒烟测试（不写库、不富化、只抓 3 篇，验证连通性与映射）
# ============================================================
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference \
  --enrich none \
  --no-profiles --no-github --no-cited-history --no-llm-extract \
  --limit 3 \
  --dry-run

# ============================================================
# 2. 小规模真实入库（核心字段，最快）
# ============================================================
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference \
  --enrich none \
  --no-profiles --no-github --no-cited-history --no-llm-extract \
  --limit 5

# ============================================================
# 3. 默认档位（Full + LLM 抽取）—— 开启全部富化
#    arXiv 匹配 + Semantic Scholar 引用/DOI + 作者主页/单位 +
#    Papers-with-Code GitHub + OpenAlex 引用历史 + LLM 抽取四要素
#    （LLM 默认用本机 claude-cli，走 Claude 订阅、无需 API key）
# ============================================================
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference \
  --limit 10

# ============================================================
# 4. 富化档位（--enrich 控制 arXiv / Semantic Scholar）
# ============================================================
# 只做 arXiv 匹配
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference --enrich arxiv --limit 5

# arXiv + Semantic Scholar
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference --enrich s2 --limit 5

# 全部外部源
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference --enrich all --limit 5

# ============================================================
# 5. 单项富化开关（默认全开，可用 --no-xxx 关闭）
# ============================================================
# 关闭作者画像（最快）
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference --enrich all --no-profiles --limit 5

# 只解析第一作者单位
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference --enrich all --no-affiliations-all --limit 5

# 开启 OpenAlex 多时间戳引用历史（快照间隔默认 3 个月）
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference --enrich all --cited-history --cited-cadence 3 --limit 5

# ============================================================
# 6. LLM 抽取 Baselines / Benchmarks / Metrics
# ============================================================
# 本机 Claude 订阅（默认，无需 key）
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference --llm-extract --llm-provider claude-cli --limit 3

# Anthropic API（需要 ANTHROPIC_API_KEY；默认模型 claude-sonnet-4-6）
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference --llm-extract --llm-provider anthropic --limit 3

# 关闭 LLM 抽取
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference --no-llm-extract --limit 3

# ============================================================
# 7. 额外输出 Obsidian Markdown 论文画像（vault）
#    主存储仍是 MongoDB，vault 是可选的第二份产物
# ============================================================
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference --limit 5 \
  --vault --vault-dir openreview_vault

# ============================================================
# 8. 其它常用参数
# ============================================================
# 指定 API 版本（默认 auto 自动探测 v2/v1）
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue NeurIPS.cc/2022/Conference --api 1 --limit 5

# 抓取指定状态（accepted / all / 逗号分隔列表）
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference --categories accepted,withdrawn,rejected --limit 5

# 只更新指定的 forum id（--venue 仍用于选择 API 版本）
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference --ids Ny150AblPu,_VjQlMeSB_J

# 认证（也可用环境变量 OPENREVIEW_USERNAME / OPENREVIEW_PASSWORD）
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference --profiles \
  --username you@example.com --password ******** --limit 20

# 查看全部参数
python -m ai4research.data_pipeline.scripts_py.crawl_openreview --help
