# 切换到根目录
```bash
cd ~
```

# 在OpenReview上爬取目标刊物 + 年份 + 条目数
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR \
  --year 2026 \
  --max-results 3
```

# 完整OpenReview刊物入库
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR \
  --year 2026
```