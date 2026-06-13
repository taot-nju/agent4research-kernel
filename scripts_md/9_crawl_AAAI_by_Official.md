# 切换到根目录
```bash
cd ~
```


# 爬取 AAAI 2026 （小规模测试 & 全量爬取）

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_aaai_official \
  --year 2026 \
  --max-results 3
```


```bash
python -m ai4research.data_pipeline.scripts_py.crawl_aaai_official \
  --year 2026 
```


# AAAI 2025 全量爬取
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_aaai_official \
  --year 2025
```


# AAAI 2024 全量爬取
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_aaai_official \
  --year 2024
```


# AAAI 2023 全量爬取
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_aaai_official \
  --year 2023
```


## AAAI 2022 (Wordpress)  （小规模测试 & 全量爬取）
```bash
python -m ai4research.data_pipeline.scripts_py.crawl_aaai_official \
  --year 2022 \
  --max-results 50
```


```bash
python -m ai4research.data_pipeline.scripts_py.crawl_aaai_official \
  --year 2022
```
