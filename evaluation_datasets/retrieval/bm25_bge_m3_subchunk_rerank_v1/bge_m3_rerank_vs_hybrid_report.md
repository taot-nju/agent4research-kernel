# Retrieval Suite v1：bge-m3 Rerank 实验记录

## 1. 实验设置

输入为当前推荐的：

```text
bm25_bge_m3_subchunk_hybrid_w070_030
```

rerank 过程为：

```text
hybrid top-10 papers
→ 展开 BM25 / bge-m3 evidence
→ 按 source chunk ID 去重
→ 超长 chunk 按 3200 + 3200 + ... 分段（overlap 200）
→ bge-m3 /v1/rerank（batch size 16）
→ 每篇论文取最高的 3 个不同原始 chunk 分数平均
```

## 2. Suite-level 对比

| metric | recommended hybrid | bge-m3 rerank | rerank - hybrid |
|---|---:|---:|---:|
| macro_MRR | 0.9375 | 0.8750 | -0.0625 |
| macro_AP | 0.8228 | 0.7713 | -0.0514 |
| macro_P@5 | 0.6250 | 0.6750 | +0.0500 |
| macro_R@5 | 0.7333 | 0.7750 | +0.0417 |
| macro_nDCG@5 | 0.8235 | 0.7337 | -0.0898 |

参考：standalone bge-m3 subchunk vector 的 macro_AP 为
`0.7734`，macro_nDCG@5 为
`0.7397`。当前 rerank 的整体结果与它接近，
尚未表现出足够独立的排序增益。

## 3. Per-case：rerank 与 recommended hybrid

| case_id | hybrid AP | rerank AP | ΔAP | hybrid nDCG@5 | rerank nDCG@5 | ΔnDCG@5 |
|---|---:|---:|---:|---:|---:|---:|
| agent-memory-trajectory | 0.8875 | 0.8042 | -0.0833 | 0.9017 | 0.7541 | -0.1476 |
| dialogue-trajectory-clustering | 0.7417 | 0.8262 | +0.0845 | 0.5732 | 0.5722 | -0.0010 |
| agent-trajectory-failure-detection | 0.6278 | 0.7783 | +0.1506 | 0.5992 | 0.7548 | +0.1557 |
| multi-agent-planning-execution | 0.7802 | 0.6681 | -0.1121 | 0.8552 | 0.5983 | -0.2568 |
| multi-agent-failure-attribution | 0.7272 | 0.8218 | +0.0946 | 0.8034 | 0.8828 | +0.0794 |
| question-storming | 1.0000 | 0.7500 | -0.2500 | 1.0000 | 0.8550 | -0.1450 |
| recursive-inquiry-refinement | 0.8179 | 0.8833 | +0.0655 | 0.8552 | 0.6639 | -0.1913 |
| markup-color-highlighting | 1.0000 | 0.6389 | -0.3611 | 1.0000 | 0.7884 | -0.2116 |

## 4. 结论

当前 bge-m3 rerank **不替代** recommended hybrid：

```text
recommended hybrid:
BM25 0.7 + bge-m3 subchunk vector 0.3
```

原因是 rerank 虽提高了 macro_P@5 与 macro_R@5，但降低了：

- macro_MRR；
- macro_AP；
- macro_nDCG@5。

它在以下 case 有明确改善：

- `agent-trajectory-failure-detection`
- `multi-agent-failure-attribution`

但在以下 case 退化明显：

- `multi-agent-planning-execution`
- `markup-color-highlighting`
- `question-storming`

因此当前定位为：

```text
bge_m3_rerank = experimental_not_recommended
```

## 5. 后续建议

如后续要继续探索 rerank，优先做小而可比较的实验：

1. 将已保存的 hybrid 与 rerank paper ranking 做保守融合，而不是让 rerank 完全覆盖 hybrid；
2. 使用同一 8-case suite 扫描少量固定权重；
3. 只有 suite-level 指标优于 recommended hybrid，才考虑更新默认策略。
