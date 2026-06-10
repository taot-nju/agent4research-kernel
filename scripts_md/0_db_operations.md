# 切换到根目录
cd ~

# 按照标题关键词，查询记录，并返回简要信息
> `默认模式`：打印完整 doc
> 
> `--brief`：打印核心字段，适合快速看结果
> 
> `--show-abstract`：打印结果中展示/不展示摘要信息

```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --title "abstention competence" \
  --limit 3 \
  --brief
```

# 按照某个字段不为空来查询
```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --non-empty arxiv_obj.arxiv_id \
  --limit 3 \
  --brief
```

# 展示不展示摘要信息
```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --non-empty abstract \
  --limit 2 \
  --brief \
  --show-abstract
```

# 测试多个字段同时非空
```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --non-empty abstract arxiv_obj.arxiv_id \
  --limit 3 \
  --brief \
  --show-abstract
```

```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --non-empty openreview_obj.forum_id arxiv_obj.arxiv_id \
  --limit 3 \
  --brief \
  --show-abstract
```

# 按照具体的字段 + 值进行查询


`accept_by: arXiv`  DB真实记录信息："accepted_by": "arXiv"
```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --field accepted_by \
  --value arXiv \
  --limit 3 \
  --brief
```

```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --field _id \
  --value 9067cdbb36d9a5c2a2f4a7cfc8004ee2a7d93191 \
  --limit 3 \
  --brief
```

`accept_by: ICLR 2026`  DB真实记录信息："accepted_by": "ICLR 2026"
```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --field accepted_by \
  --value "ICLR 2023" \
  --limit 20 \
  --brief
```

```json
...,
"arxiv_obj": {
        "arxiv_id": "2606.02965",
        ...
},
...
```

```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --field arxiv_obj.arxiv_id \
  --value 2606.02965 \
  --limit 3 \
  --brief \
  --show-abstract
```

# 质检测试（检查某1个或n个字段是否都存在）

检查 ICML 2022

```bash
python -m ai4research.data_pipeline.scripts_py.check_fields \
  --accepted-by "ICML 2022" \
  --source PMLR \
  --field abstract \
  --field base_urls.pmlr_abs_url \
  --field base_urls.pmlr_pdf_url \
  --field more_urls.pmlr_publication_date \
  --field more_urls.pmlr_firstpage \
  --field more_urls.pmlr_lastpage
```


检查 OpenReview

```bash
python -m ai4research.data_pipeline.scripts_py.check_fields \
  --accepted-by "ICML 2025" \
  --source OpenReview \
  --field abstract \
  --field base_urls.openreview_pdf_url \
  --field openreview_obj.forum_url \
  --field openreview_obj.accept_type
```