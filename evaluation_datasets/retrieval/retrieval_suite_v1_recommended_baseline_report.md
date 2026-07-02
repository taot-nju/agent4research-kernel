# Retrieval Suite v1：Recommended Baseline 固化报告

## 1. 当前推荐策略

当前推荐默认检索策略为：

```text
bm25_bge_m3_subchunk_hybrid_w070_030
```

具体为：

```text
BM25 weight = 0.7
bge-m3 subchunk vector weight = 0.3
```

其中，vector baseline 使用：

```text
model: bge-m3
provider: openai-compatible
subchunk_max_chars: 3200
subchunk_overlap_chars: 200
embedding_dimension: 1024
```

## 2. Suite-level 指标

| metric | BM25 baseline | bge-m3 subchunk vector | recommended hybrid | hybrid - BM25 |
|---|---:|---:|---:|---:|
| macro_MRR | 0.9375 | 0.8750 | 0.9375 | 0.0000 |
| macro_AP | 0.8052 | 0.7734 | 0.8228 | 0.0176 |
| macro_P@5 | 0.6000 | 0.6750 | 0.6250 | 0.0250 |
| macro_R@5 | 0.7125 | 0.7750 | 0.7333 | 0.0208 |
| macro_nDCG@5 | 0.8071 | 0.7397 | 0.8235 | 0.0164 |

## 3. 结论

当前 recommended hybrid 在保持 BM25 macro_MRR 的同时，提升了：

- macro_AP
- macro_P@5
- macro_R@5
- macro_nDCG@5

因此，它是当前 `retrieval_suite_v1` 上最适合作为默认检索策略的 baseline。

## 4. 资产位置

### Registry

```text
evaluation_datasets/retrieval/retrieval_suite_v1_experiment_registry.json
```

### BM25 baseline

```text
evaluation_datasets/retrieval/retrieval_suite_v1_bm25_baseline_summary.json
```

### bge-m3 subchunk vector baseline

```text
evaluation_datasets/retrieval/bge_m3_vector_v1_subchunk_3200/retrieval_suite_v1_bge_m3_subchunk_3200_summary.json
```

### recommended hybrid baseline

```text
evaluation_datasets/retrieval/bm25_bge_m3_subchunk_hybrid_v1_w070_030/retrieval_suite_v1_bm25_bge_m3_subchunk_w070_030_summary.json
```

## 5. 后续方向

1. 增加 embedding audit，记录每个 case 的原始 chunk 数、embedding 数、subchunk 数。
2. 在 recommended hybrid top-k 上接入 reranker。
3. 探索 query-aware / case-aware 动态权重。
