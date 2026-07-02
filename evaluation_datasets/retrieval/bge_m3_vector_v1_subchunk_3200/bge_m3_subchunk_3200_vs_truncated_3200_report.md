# Retrieval Suite v1：bge-m3 Subchunk Baseline 固化记录

## 1. 背景

上一版真实 embedding baseline 使用：

```text
--embedding-input-max-chars 3200
```

这能避免 bge-m3 超过 8192 token 输入限制，但语义上是临时方案：超长 chunk 的后半部分会被丢弃。

当前版本改为：

```text
--subchunk-max-chars 3200
--subchunk-overlap-chars 200
```

也就是：

```text
超长 chunk → 3200 + 3200 + ... → 多个 subchunk embedding
```

每个 subchunk embedding 都保留：

- `source_chunk_id`
- `subchunk_index`
- `subchunk_count`
- `char_start`
- `char_end`

因此它不会丢弃超长 chunk 的尾部信息。

## 2. Suite-level 对比

| metric | truncated_3200 | subchunk_3200 | 变化 |
|---|---:|---:|---:|
| macro_MRR | 0.8750 | 0.8750 | 0.0000 |
| macro_AP | 0.7734 | 0.7734 | 0.0000 |
| macro_P@5 | 0.6750 | 0.6750 | 0.0000 |
| macro_R@5 | 0.7750 | 0.7750 | 0.0000 |
| macro_nDCG@5 | 0.7397 | 0.7397 | 0.0000 |

## 3. 结论

本轮 `retrieval_suite_v1` 上，subchunk_3200 与 truncated_3200 的 suite-level 指标相同。

这不表示 subchunk 没有价值，而是说明：

1. 当前 8 个 case 中，超长 chunk 数量较少；
2. 被拆出的尾部 subchunk 没有改变最终 top paper ranking；
3. 但工程语义已经从“截断丢弃”升级为“完整覆盖”。

因此，从后续实验开始，推荐使用：

```text
bge_m3_vector_subchunk_3200
```

作为真实 embedding vector baseline。

## 4. 后续建议

1. 使用 subchunk_3200 重新跑 BM25 + bge-m3 hybrid weight scan，形成干净的最终 hybrid baseline。
2. 可增加 embedding audit 输出，记录每个 case 的原始 chunk 数、embedding 数、subchunk 数。
3. 后续 reranker 应基于 subchunk-aware evidence，而不是 truncated evidence。