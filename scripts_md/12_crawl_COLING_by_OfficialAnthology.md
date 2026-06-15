# 切换到根目录
```bash
cd ~
```


# 爬取 COLING 2025 main （小规模测试 & 全量爬取）

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue COLING \
  --year 2025 \
  --subtype main \
  --max-results 3 \
  --delay-seconds 0
```

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue COLING \
  --year 2025 \
  --subtype main \
  --delay-seconds 0.5
```

# 爬取 LREC-COLING 2024 main （小规模测试 & 全量爬取）
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue COLING \
  --year 2024 \
  --subtype main \
  --max-results 3 \
  --delay-seconds 0
```

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue COLING \
  --year 2024 \
  --subtype main \
  --delay-seconds 0.5
```

# 爬取 COLING 2023 1 （小规模测试 & 全量爬取）
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue COLING \
  --year 2022 \
  --subtype main \
  --max-results 3 \
  --delay-seconds 0
```

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue COLING \
  --year 2022 \
  --subtype main \
  --delay-seconds 0.5
```