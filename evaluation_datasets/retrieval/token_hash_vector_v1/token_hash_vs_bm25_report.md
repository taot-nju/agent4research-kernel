# Token-hash Vector Demo vs BM25 Baseline

本报告比较两条检索链路在 `retrieval_suite_v1` 上的表现：

1. **BM25 baseline**
   - 当前正式基线；
   - 基于 chunk 文本 BM25 检索和论文级聚合；
   - 结果保存在 `evaluation_datasets/retrieval/retrieval_suite_v1_bm25_baseline_summary.json`。

2. **Token-hash vector demo**
   - 本地 demo vector baseline；
   - 使用 `TokenHashEmbeddingProvider`；
   - 不是语义 embedding，只是基于 token hashing trick 的词面向量；
   - 目标是验证 vector retrieval 能接入同一套 evaluation suite。

## 1. Suite-level 对比

| metric | BM25 baseline | token-hash vector demo | 观察 |
|---|---:|---:|---|
| macro_MRR | 0.9375 | 0.7708 | token-hash 更容易把第一个严格相关结果排低 |
| macro_AP | 0.8052 | 0.6930 | BM25 整体排序质量更好 |
| macro_P@5 | 0.6000 | 0.6000 | 前 5 准确率相同 |
| macro_R@5 | 0.7125 | 0.6333 | token-hash 前 5 漏掉更多相关论文 |
| macro_nDCG@5 | 0.8071 | 0.7335 | BM25 的分级排序更好 |

结论：

Token-hash vector demo 不如 BM25 baseline，这是预期内的。它并不具备真实语义理解，只能捕捉 token-level overlap。

但是它证明了一件关键事情：

```text
vector retrieval 已经能够接入同一套 retrieval suite 评估协议。
```

这意味着后续真实 embedding API / 本地 embedding 模型可以直接替换 token-hash provider，并与 BM25 做同台比较。

## 2. Per-case 对比

| case_id | BM25 AP | token-hash AP | BM25 nDCG@5 | token-hash nDCG@5 | 观察 |
|---|---:|---:|---:|---:|---|
| agent-memory-trajectory | 1.0000 | 0.8875 | 0.9506 | 0.8106 | token-hash 能找到相关，但排序不如 BM25 |
| dialogue-trajectory-clustering | 0.7644 | 0.9267 | 0.7193 | 0.9099 | token overlap 强，token-hash 反而更好 |
| agent-trajectory-failure-detection | 0.6167 | 0.5450 | 0.5992 | 0.5290 | 两者都弱，是后续真实 embedding 的重点观察 case |
| multi-agent-planning-execution | 0.7329 | 0.8486 | 0.6224 | 0.7543 | token-hash 在这个词面明确的 case 上更好 |
| multi-agent-failure-attribution | 0.7045 | 0.7885 | 0.8034 | 0.8846 | token-hash 排序较好，但仍是词面驱动 |
| question-storming | 1.0000 | 0.3750 | 1.0000 | 0.6157 | token-hash 对 research-gap case 很弱 |
| recursive-inquiry-refinement | 0.8179 | 0.8417 | 0.8711 | 0.8703 | 两者接近 |
| markup-color-highlighting | 0.8056 | 0.3313 | 0.8908 | 0.4940 | token-hash 最弱，说明跨概念/邻近研究需要真语义模型 |

## 3. 如何理解 token-hash 的价值

Token-hash 不是最终检索模型。

它的价值不是“更准”，而是：

1. 建立了 chunk embedding schema；
2. 建立了 embedding JSONL repository；
3. 建立了 vector chunk retriever；
4. 建立了 vector paper aggregation；
5. 建立了候选论文 vector search CLI；
6. 建立了 suite-level vector runner；
7. 证明 vector result 可以被现有 `evaluate_saved_retrieval` 评估。

换句话说，我们现在已经具备：

```text
BM25 baseline
vs
demo-vector baseline
```

的同台评估能力。

下一步只要把 token-hash provider 替换成真实 embedding provider，就能得到：

```text
BM25 baseline
vs
real-embedding vector baseline
vs
hybrid baseline
```

## 4. 当前最值得关注的 case

### agent-trajectory-failure-detection

BM25 和 token-hash 都弱。

这说明这个 case 需要的不是简单词面匹配，而是理解：

- agent trajectory；
- anomaly / outlier；
- failure diagnosis；
- root cause / attribution；
- step-level error localization；
- memory / process traces。

真实 embedding 如果有效，应该优先改善这个 case。

### markup-color-highlighting

Token-hash 最弱。

这说明它无法理解：

- HTML markup；
- color highlighting；
- instruction salience；
- multimodal prompt formatting；
- attention / focus / emphasis。

这个 case 很可能需要更强语义 embedding，甚至后续需要 multimodal / layout-aware retrieval。

### question-storming

Token-hash 很弱，但 BM25 很强。

这可能说明 BM25 正好抓住了 query 的关键词，而 token-hash 在相邻概念扩展上能力不足。真实 embedding 是否能保持或改善这个 case，是一个很好的观察点。

## 5. 下一阶段建议

下一阶段进入真实 embedding provider：

1. 新增真实 embedding provider 接口实现；
2. 暴露 standalone CLI：
   - `--help` 可查询；
   - 支持单文本 embedding；
   - 支持 chunk JSONL embedding；
3. 在小样本 chunk 上手工测试；
4. 在 8-case suite 上运行 real-embedding vector baseline；
5. 与 BM25 和 token-hash demo 进行三方对比。

验收标准不是“跑通 API”而是：

```text
真实 embedding 的 search output 可以被 evaluate_saved_retrieval 评估；
真实 embedding 的 suite summary 可以和 BM25 baseline 同台比较。
```