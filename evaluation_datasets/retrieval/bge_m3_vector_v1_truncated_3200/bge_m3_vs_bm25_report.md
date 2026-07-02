# Retrieval Suite v1：BM25 vs bge-m3 Vector Baseline

本报告比较 `retrieval_suite_v1` 上两条检索链路的表现：

1. **BM25 baseline**：当前词面检索基线。
2. **bge-m3 vector baseline**：通过 OpenAI-compatible vLLM embedding 服务运行的真实向量检索。

## 0. 重要说明

本轮 bge-m3 使用了：

```text
--embedding-input-max-chars 3200
```

这只是为了避免超长 chunk 超过 bge-m3 的 8192 token 输入限制。当前策略是“截断前 3200 字符”，不是最终方案。后续必须升级为：

```text
超长 chunk → 3200 + 3200 + 3200 + ... → subchunk embeddings → 聚合回原 paper
```

因此，本报告是第一版真实 embedding baseline，不是最终最优向量检索结果。

## 1. Suite-level 对比

| metric | BM25 baseline | bge-m3 vector | 变化 |
|---|---:|---:|---:|
| macro_MRR | 0.9375 | 0.8750 | -0.0625 |
| macro_AP | 0.8052 | 0.7734 | -0.0318 |
| macro_P@5 | 0.6000 | 0.6750 | 0.0750 |
| macro_R@5 | 0.7125 | 0.7750 | 0.0625 |
| macro_nDCG@5 | 0.8071 | 0.7397 | -0.0674 |

结论：

- BM25 的整体排序稳定性仍然更好，尤其体现在 macro_AP 和 macro_nDCG@5。
- bge-m3 的前 5 召回更强，macro_P@5 与 macro_R@5 均高于 BM25。
- 这说明当前最自然的下一步不是用 vector 替代 BM25，而是做 BM25 + bge-m3 hybrid。

## 2. Per-case 对比

| case_id | BM25 AP | bge-m3 AP | ΔAP | BM25 nDCG@5 | bge-m3 nDCG@5 | ΔnDCG@5 | 观察 |
|---|---:|---:|---:|---:|---:|---:|---|
| agent-memory-trajectory | 1.0000 | 0.8042 | -0.1958 | 0.9506 | 0.7541 | -0.1965 | BM25 排序更稳 |
| dialogue-trajectory-clustering | 0.7644 | 0.8762 | 0.1117 | 0.7193 | 0.5993 | -0.1200 | bge-m3 AP 改善 |
| agent-trajectory-failure-detection | 0.6167 | 0.7117 | 0.0950 | 0.5992 | 0.7293 | 0.1301 | bge-m3 明显改善 |
| multi-agent-planning-execution | 0.7329 | 0.6829 | -0.0500 | 0.6224 | 0.5824 | -0.0400 | BM25 排序更稳 |
| multi-agent-failure-attribution | 0.7045 | 0.8819 | 0.1774 | 0.8034 | 0.9156 | 0.1122 | bge-m3 明显改善 |
| question-storming | 1.0000 | 0.7500 | -0.2500 | 1.0000 | 0.8550 | -0.1450 | BM25 排序更稳 |
| recursive-inquiry-refinement | 0.8179 | 0.8417 | 0.0238 | 0.8711 | 0.6400 | -0.2312 | BM25 nDCG 更好 |
| markup-color-highlighting | 0.8056 | 0.6389 | -0.1667 | 0.8908 | 0.8421 | -0.0487 | BM25 排序更稳 |

## 3. 关键观察

### bge-m3 双指标改善的 case

- `agent-trajectory-failure-detection`：AP 0.6167 → 0.7117，nDCG@5 0.5992 → 0.7293。
- `multi-agent-failure-attribution`：AP 0.7045 → 0.8819，nDCG@5 0.8034 → 0.9156。

### bge-m3 AP 改善但排序质量下降的 case

- `dialogue-trajectory-clustering`：AP 0.7644 → 0.8762，nDCG@5 0.7193 → 0.5993。说明它找到了更多相关论文，但高等级相关论文排序不如 BM25。

### BM25 仍然更稳的 case

- `agent-memory-trajectory`：AP 1.0000 → 0.8042，nDCG@5 0.9506 → 0.7541。
- `dialogue-trajectory-clustering`：AP 0.7644 → 0.8762，nDCG@5 0.7193 → 0.5993。
- `multi-agent-planning-execution`：AP 0.7329 → 0.6829，nDCG@5 0.6224 → 0.5824。
- `question-storming`：AP 1.0000 → 0.7500，nDCG@5 1.0000 → 0.8550。
- `recursive-inquiry-refinement`：AP 0.8179 → 0.8417，nDCG@5 0.8711 → 0.6400。
- `markup-color-highlighting`：AP 0.8056 → 0.6389，nDCG@5 0.8908 → 0.8421。

## 4. 下一步

建议进入 hybrid suite：

```text
BM25 baseline
+
bge-m3 vector baseline
→ hybrid ranking
→ 8-case suite evaluation
```

同时保留一个后续工程任务：把当前的超长输入截断保护升级为 subchunk embedding，避免丢弃超长 chunk 后半部分信息。

