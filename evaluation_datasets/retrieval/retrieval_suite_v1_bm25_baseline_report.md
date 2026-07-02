# Retrieval Suite v1：BM25 Baseline 阶段报告

本报告记录 `ai4research` 当前检索评估基线的状态。它的作用是：在进入 embedding / vector / hybrid retrieval 之前，先把 BM25 的表现固定下来，作为后续比较的“尺子”。

## 1. 当前主线位置

当前项目主线是：

1. 从数据库元数据中按 topic 粗筛候选论文；
2. 对候选论文补齐 PDF、OCR markdown、chunk；
3. 在候选论文全文 chunk 中做二次检索；
4. 聚合为论文级排序，并返回页码、section、证据 chunk；
5. 用人工标注评估检索质量；
6. 下一阶段引入 embedding / hybrid / reranker，并与 BM25 baseline 对比。

所以，本阶段不是最终检索系统，而是在为下一阶段 embedding 做可量化准备。

## 2. 已冻结的评估资产

### Suite manifest

- `evaluation_datasets/retrieval/retrieval_suite_v1.json`

这个文件登记了 8 个真实检索评估案例，每个案例都包含：

- 人工标注 dataset；
- 已保存的全文检索输出；
- 已计算的 metrics；
- 当前使用的 relevance threshold。

### BM25 baseline summary

- `evaluation_datasets/retrieval/retrieval_suite_v1_bm25_baseline_summary.json`

这个文件汇总了 8 个案例的 BM25 基线表现。

### 汇总 CLI

```bash
PYTHONPATH="$HOME" python -m ai4research.indexing_pipeline.scripts_py.summarize_retrieval_suite \
  --suite ~/ai4research/evaluation_datasets/retrieval/retrieval_suite_v1.json \
  --save-json ~/ai4research/evaluation_datasets/retrieval/retrieval_suite_v1_bm25_baseline_summary.json
```

### 测试状态

当前全量测试通过：

```text
38 passed
```

## 3. 8 个评估案例

| case_id | 主题含义 | 严格相关论文数 |
|---|---|---:|
| agent-memory-trajectory | agent memory 与 trajectory 的结合 | 4 |
| dialogue-trajectory-clustering | 多轮对话 / 会话轨迹 / 轨迹聚类 | 5 |
| agent-trajectory-failure-detection | agent trajectory 异常检测、失败诊断 | 5 |
| multi-agent-planning-execution | 多智能体规划、分工、执行 | 6 |
| multi-agent-failure-attribution | 多智能体失败归因、credit assignment | 6 |
| question-storming | 主动提问、问题风暴、研究构思 | 2 |
| recursive-inquiry-refinement | 递归追问、反思、批判、 refinement | 6 |
| markup-color-highlighting | markup / color / highlight / salience 对提示和多轮对话的作用 | 3 |

其中：

- `question-storming` 和 `markup-color-highlighting` 更像 research-gap 案例；
- 它们没有特别直接的 grade-3 论文，但能检验系统是否能找到相邻研究方向；
- `agent-trajectory-failure-detection` 是当前 BM25 最弱案例，后续 embedding 应优先观察它是否改善。

## 4. BM25 baseline 指标

| case_id | rel | MRR | AP | P@5 | R@5 | nDCG@5 |
|---|---:|---:|---:|---:|---:|---:|
| agent-memory-trajectory | 4 | 1.0000 | 1.0000 | 0.8000 | 1.0000 | 0.9506 |
| dialogue-trajectory-clustering | 5 | 1.0000 | 0.7644 | 0.6000 | 0.6000 | 0.7193 |
| agent-trajectory-failure-detection | 5 | 0.5000 | 0.6167 | 0.6000 | 0.6000 | 0.5992 |
| multi-agent-planning-execution | 6 | 1.0000 | 0.7329 | 0.6000 | 0.5000 | 0.6224 |
| multi-agent-failure-attribution | 6 | 1.0000 | 0.7045 | 0.4000 | 0.3333 | 0.8034 |
| question-storming | 2 | 1.0000 | 1.0000 | 0.4000 | 1.0000 | 1.0000 |
| recursive-inquiry-refinement | 6 | 1.0000 | 0.8179 | 0.8000 | 0.6667 | 0.8711 |
| markup-color-highlighting | 3 | 1.0000 | 0.8056 | 0.6000 | 1.0000 | 0.8908 |

Macro 指标：

| metric | value |
|---|---:|
| macro_MRR | 0.9375 |
| macro_AP | 0.8052 |
| macro_P@5 | 0.6000 |
| macro_R@5 | 0.7125 |
| macro_nDCG@5 | 0.8071 |

最弱案例：

- weakest_AP_case: `agent-trajectory-failure-detection`
- weakest_nDCG@5_case: `agent-trajectory-failure-detection`

## 5. 如何理解这些指标

### MRR

MRR 衡量第一个严格相关结果出现得有多早。

当前 macro MRR = 0.9375，说明多数案例第 1 名就是严格相关论文。只有 `agent-trajectory-failure-detection` 的第 1 名不是严格相关，所以它的 MRR 是 0.5。

### AP

AP 衡量严格相关论文在整个排序中的整体位置。

当前 macro AP = 0.8052，说明 BM25 排序整体还不错，但不是天花板。特别是 agent 失败诊断、多智能体 failure attribution 等语义更复杂的主题，BM25 会被字面关键词误导。

### P@5 与 R@5

P@5 = 0.6000，表示前 5 篇里平均 60% 是严格相关。

R@5 = 0.7125，表示前 5 篇平均能找回约 71% 的严格相关论文。

这说明 top-5 已经有可用价值，但仍会漏掉一部分相关论文。后续 embedding / hybrid 的目标之一，就是提高 top-5 的召回与排序质量。

### nDCG@5

nDCG@5 = 0.8071，说明前 5 的分级排序总体还可以，但仍有改善空间。尤其是当 grade-3 高相关论文没有排在前面时，nDCG 会明显下降。

## 6. 当前 BM25 baseline 的局限

1. 这是候选集内的全文二次检索评估，不是全库 8w 篇论文的全局召回评估。
2. 当前第一阶段仍依赖 metadata 粗筛，metadata 漏掉的论文不会进入后续全文检索。
3. BM25 擅长关键词匹配，但对语义等价、任务意图、概念组合、研究 gap 的理解有限。
4. 复杂主题中，BM25 容易被表面词汇误导，例如把普通 anomaly detection 排到 agent failure diagnosis 前面。
5. 当前人工标注规模还小，但已经足够作为下一阶段 embedding 的早期回归测试集。

## 7. 下一阶段目标

下一阶段建议进入 embedding / hybrid retrieval：

1. 为 chunk 建立 embedding 表征；
2. 支持按候选论文内的 vector search；
3. 将 BM25 与 vector score 做 hybrid fusion；
4. 对同一套 8-case suite 重新跑 metrics；
5. 对比 BM25 baseline：
   - macro_AP 是否提升；
   - macro_R@5 是否提升；
   - weakest case 是否改善；
   - research-gap 类案例是否能找到更语义接近的论文。

最重要的是：以后每次检索策略变更，都不再只凭感觉判断“好像更准了”，而是用这套 suite 做可复现评估。