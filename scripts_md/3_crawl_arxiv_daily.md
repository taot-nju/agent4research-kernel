# 切换到根目录
```bash
cd ~
```
# 爬取今天的论文（默认）
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily
```

# 默认爬配置文件里的所有 categories
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01
```

# 只爬一个 category
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01 \
  --categories cs.AI
```

# 调试时限制每类最多 2 篇
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01 \
  --categories cs.AI \
  --max-results 2
```