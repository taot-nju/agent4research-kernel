# 切换到根目录
```bash
cd ~
```


# ICML (2026)

## IMCL 2026测试断网续传功能
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_icml_official \
  --year 2026 \
  --max-results 120 \
  --fetch-details
```

## ICML 2026全量入库
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_icml_official \
  --year 2026 \
  --fetch-details
```

