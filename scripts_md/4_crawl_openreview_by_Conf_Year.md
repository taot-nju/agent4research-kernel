# 切换到根目录
```bash
cd ~
```



# ICLR (2022, 2023 | 2024, 2025, 2026)


## 参数说明
- `--venue ICLR`: 会议名称
- `--year 2025`: 会议年份
- `--max-results 3`: 爬取的最大条目数（调试用）

## 在OpenReview上爬取目标刊物 + 年份 + 条目数
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR \
  --year 2025 \
  --max-results 3
```


## 完整OpenReview刊物入库

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR \
  --year 2026
```

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR \
  --year 2025
```

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR \
  --year 2024
```


```bash
# 注意：2023年用的是OpenReview提供的v1版本API
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR \
  --year 2023
```

```bash
# 注意：2022年用的是OpenReview提供的v1版本API
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR \
  --year 2022 
```


# ICML (2023, 2024, 2025)

## 入库 ICML 2023–2025 (建议按年份从旧到新跑，方便检查)
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICML \
  --year 2023
```

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICML \
  --year 2024
```

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICML \
  --year 2025
```