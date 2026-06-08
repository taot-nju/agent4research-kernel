# 切换到根目录
cd ~

# 爬取今天的论文（默认）
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily


# 默认爬配置文件里的所有 categories
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01

# 只爬一个 category
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01 \
  --categories cs.AI

# 调试时限制每类最多 2 篇
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01 \
  --categories cs.AI \
  --max-results 2


这是测试！