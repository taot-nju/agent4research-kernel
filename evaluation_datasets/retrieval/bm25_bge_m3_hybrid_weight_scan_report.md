# Retrieval Suite v1：BM25 + bge-m3 Hybrid Weight Scan

本报告记录 `retrieval_suite_v1` 上 BM25、bge-m3 vector，以及多组固定权重 hybrid 的对比结果。

## 0. 当前结论

当前推荐默认 hybrid 权重为：

```text
BM25 weight = 0.7
bge-m3 weight = 0.3
```

原因：它在保持 BM25 的 macro_MRR 水平的同时，提高了 macro_AP、macro_P@5、macro_R@5 和 macro_nDCG@5，是当前固定权重扫描中最均衡的一组。

## 1. 重要工程说明

本轮 bge-m3 vector 使用了：

```text
--embedding-input-max-chars 3200
```

这是临时截断保护，用于避免超长 chunk 超过 bge-m3 的 8192 token 输入限制。后续必须升级为：

```text
超长 chunk → 3200 + 3200 + 3200 + ... → subchunk embeddings → 聚合回原 paper
```

因此，本报告是第一版 hybrid baseline，不是最终最优版本。

## 2. Suite-level 对比

| run | MRR | AP | P@5 | R@5 | nDCG@5 | 观察 |
|---|---:|---:|---:|---:|---:|---|
| BM25 baseline | 0.9375 | 0.8052 | 0.6000 | 0.7125 | 0.8071 | 词面检索基线，MRR 稳 |
| bge-m3 vector | 0.8750 | 0.7734 | 0.6750 | 0.7750 | 0.7397 | 真实向量基线，召回更强但排序不稳 |
| Hybrid 0.5 / 0.5 | 0.8750 | 0.8230 | 0.6500 | 0.7542 | 0.8146 | 权重扫描候选 |
| Hybrid 0.6 / 0.4 | 0.8750 | 0.8144 | 0.6500 | 0.7542 | 0.8147 | 权重扫描候选 |
| Hybrid 0.65 / 0.35 | 0.8750 | 0.8144 | 0.6500 | 0.7542 | 0.8170 | 权重扫描候选 |
| Hybrid 0.7 / 0.3 | 0.9375 | 0.8228 | 0.6250 | 0.7333 | 0.8235 | 当前推荐默认权重 |
| Hybrid 0.75 / 0.25 | 0.9375 | 0.7975 | 0.6250 | 0.7333 | 0.8165 | 权重扫描候选 |
| Hybrid 0.8 / 0.2 | 0.9375 | 0.7937 | 0.6250 | 0.7333 | 0.8158 | 权重扫描候选 |

## 3. 为什么推荐 0.7 / 0.3

| metric | BM25 | bge-m3 | recommended hybrid 0.7/0.3 | hybrid - BM25 |
|---|---:|---:|---:|---:|
| MRR | 0.9375 | 0.8750 | 0.9375 | 0.0000 |
| AP | 0.8052 | 0.7734 | 0.8228 | 0.0175 |
| P@5 | 0.6000 | 0.6750 | 0.6250 | 0.0250 |
| R@5 | 0.7125 | 0.7750 | 0.7333 | 0.0208 |
| nDCG@5 | 0.8071 | 0.7397 | 0.8235 | 0.0164 |

观察：

- 0.7/0.3 的 macro_MRR 与 BM25 持平。
- 0.7/0.3 的 macro_AP、P@5、R@5、nDCG@5 均超过 BM25。
- 0.5/0.5 虽然 AP 也高，但 MRR 掉到 0.8750，说明 vector 权重过高会拉偏部分 case 的第一名。
- 0.8/0.2 太偏 BM25，vector 增益不足，AP 低于 0.7/0.3。

## 4. Per-case：推荐 hybrid 与 BM25 对比

| case_id | BM25 AP | hybrid AP | ΔAP | BM25 nDCG@5 | hybrid nDCG@5 | ΔnDCG@5 |
|---|---:|---:|---:|---:|---:|---:|
| agent-memory-trajectory | 1.0000 | 0.8875 | -0.1125 | 0.9506 | 0.9017 | -0.0489 |
| dialogue-trajectory-clustering | 0.7644 | 0.7417 | -0.0228 | 0.7193 | 0.5732 | -0.1461 |
| agent-trajectory-failure-detection | 0.6167 | 0.6278 | 0.0111 | 0.5992 | 0.5992 | 0.0000 |
| multi-agent-planning-execution | 0.7329 | 0.7802 | 0.0472 | 0.6224 | 0.8552 | 0.2328 |
| multi-agent-failure-attribution | 0.7045 | 0.7272 | 0.0227 | 0.8034 | 0.8034 | 0.0000 |
| question-storming | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 0.0000 |
| recursive-inquiry-refinement | 0.8179 | 0.8179 | 0.0000 | 0.8711 | 0.8552 | -0.0160 |
| markup-color-highlighting | 0.8056 | 1.0000 | 0.1944 | 0.8908 | 1.0000 | 0.1092 |

## 5. 后续任务

1. 将 0.7/0.3 作为当前默认 hybrid baseline。
2. 后续实现 subchunk embedding，替代当前 3200 字符截断保护。
3. 后续可以尝试 query-aware / case-aware 动态权重，而不是固定全局权重。
4. 后续可以尝试 reranker，对 hybrid top-k 结果进行二阶段重排。

