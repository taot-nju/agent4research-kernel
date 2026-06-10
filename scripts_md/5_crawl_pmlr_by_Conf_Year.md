# 切换到根目录
```bash
cd ~
```



# ICML (2022)

## ICML 2022的稳定数据源：PMLR v162

```bash
# 通过PMLR页面爬取数据：只爬3条
python -m ai4research.data_pipeline.scripts_py.crawl_pmlr \
  --venue ICML \
  --year 2022 \
  --max-results 3 \
  --fetch-details
```


```bash
# 通过PMLR页面爬取数据：全量入库
python -m ai4research.data_pipeline.scripts_py.crawl_pmlr \
  --venue ICML \
  --year 2022 \
  --fetch-details
```