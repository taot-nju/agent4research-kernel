
# 17. Research Topic 到全文论文证据闭环

本文档说明如何从一个 Research Topic 出发，完成：

```text
MongoDB 元数据粗筛
→ PDF 下载或复用
→ OCR Markdown 生成或复用
→ 文档质量检查
→ Markdown chunk 生成或复用
→ 候选集合内 BM25 全文二次检索
→ chunk 证据聚合为论文排名
→ 返回 Top N 论文、页码证据和资产路径
```

---

## 1. 功能定位

入口：

```bash
PYTHONPATH="$HOME" python -m \
  ai4research.research_pipeline.scripts_py.process_research_topic_evidence
```

这是当前项目第一条完整的论文证据检索闭环。

它不是只根据标题和摘要返回论文，而是先用元数据粗筛，再读取候选论文全文进行二次检索。

---

## 2. 两阶段检索

### 第一阶段：元数据粗筛

检索字段包括：

```text
title
abstract
keywords
tags
OpenReview keywords
OpenReview TLDR
ICML official keywords
```

第一阶段输出 `metadata_candidate_k` 篇候选论文。

### 第二阶段：全文检索

对候选论文执行或复用：

```text
PDF
→ OCR Markdown
→ chunk
```

然后在候选集合的全部 chunk 中执行 BM25，并将最佳 chunk 聚合为论文级排名。

最终输出 `final_paper_k` 篇论文。

通常：

```text
final_paper_k < metadata_candidate_k
```

---

## 3. 默认参数

```text
metadata_candidate_k:        30
final_paper_k:                5
candidate_scan_limit:       100
candidate_pool_size:       1000

chunk_recall_k:             300
evidence_chunks_per_paper:    3
top_chunks_for_score:         3

target_chars:              2400
max_chars:                 3200
overlap_chars:              300

bm25_k1:                    1.5
bm25_b:                    0.75
section_term_multiplier:      2
```

---

## 4. 只预览🟢元数据候选

预览不会下载 PDF、不会执行 OCR、不会生成 chunk，也不会修改数据库：

```bash
PYTHONPATH="$HOME" python -m \
  ai4research.research_pipeline.scripts_py.process_research_topic_evidence \
  --topic "Agent memory，trajectory" \
  --metadata-candidate-k 5 \
  --final-paper-k 3 \
  --candidate-scan-limit 30 \
  --preview  # 🟢
```

中文逗号会被规范化为空格。上述查询的有效词项为：

```text
agent
memory
trajectory
```

当前检索器主要支持英文和数字词项，不支持纯中文 Topic。

---

## 5. 执行完整闭环

```bash
PYTHONPATH="$HOME" python -m \
  ai4research.research_pipeline.scripts_py.process_research_topic_evidence \
  --topic "Agent memory，trajectory" \
  --metadata-candidate-k 5 \
  --final-paper-k 3 \
  --candidate-scan-limit 30
```

前置条件：

```text
MongoDB 可用
GLM-OCR 服务可用
AI4RESEARCH_DATA_ROOT 已正确配置
```

即使候选论文已有 OCR 资产，当前完整命令仍会先检查 OCR 服务健康状态。

---

# 6. 已真实运行的闭环 Demo

## 6.1 Demo 输入

```text
Research Topic:
Agent memory，trajectory

元数据粗筛论文数:
5

最终返回论文数:
3
```

对应命令：

```bash
PYTHONPATH="$HOME" python -m \
  ai4research.research_pipeline.scripts_py.process_research_topic_evidence \
  --topic "Agent memory，trajectory" \
  --metadata-candidate-k 5 \
  --final-paper-k 3 \
  --candidate-scan-limit 30
```

---

## 6.2 第一阶段真实输出：元数据粗筛

```text
1. Dual-Scale World Memory for LLM Agents towards Hard-Exploration Problems
   metadata_score: 32.5000

2. Synapse: Trajectory-as-Exemplar Prompting with Memory for Computer Control
   metadata_score: 30.0000

3. MemGen: Weaving Generative Latent Memory for Self-Evolving Agents
   metadata_score: 27.5000

4. THOMAS: Trajectory Heatmap Output with learned Multi-Agent Sampling
   metadata_score: 27.5000

5. MIRA: Memory-Integrated Reinforcement Learning Agent with Limited LLM Guidance
   metadata_score: 25.0000
```

注意：此时 MIRA 仅排第 5。

---

## 6.3 首次运行的资产准备结果

PDF 阶段：

```text
claimed:   3
success:   3
failed:    0
```

OCR 阶段：

```text
claimed:   3
success:   3
failed:    0
```

质量检查：

```text
checked:   3
passed:    3
warning:   0
rejected:  0
```

三篇新 OCR 文档的真实处理结果：

```text
Dual-Scale World Memory
pages:     26
chars:     77,302
duration:  53.19 seconds

MIRA
pages:     37
chars:     126,308
duration:  80.53 seconds

THOMAS
pages:     18
chars:     48,087
duration:  38.12 seconds
```

另外两篇已有 PDF/OCR 资产被直接复用。

---

## 6.4 chunk 真实结果

```text
Dual-Scale World Memory
status: written
chunks: 38

Synapse
status: written
chunks: 47

MemGen
status: reused
chunks: 54

THOMAS
status: written
chunks: 26

MIRA
status: written
chunks: 64
```

候选集合总计：

```text
papers: 5
chunks: 229
missing chunk papers: 0
```

---

## 6.5 第二阶段真实输出：全文论文排名

### Rank 1：MIRA

```text
paper_id:
e29263ebf02f67ba70425395fc307d2de84e4220

raw_score:
6.7851

relative_score:
100.0 / 100.0

query_coverage:
1.0000
```

最佳证据：

```text
pages 28-28
E MEMORY GRAPH CONSTRUCTION DETAILS
→ E.2 AGENT-INDUCED UPDATES

pages 28-29
F UTILITY COMPUTATION
→ F.1 SIMILARITY SCORE

pages 4-5
2 METHODOLOGY
→ 2.3 UTILITY SIGNAL COMPUTATION
```

资产：

```text
PDF:
/data/ai4research_assets/pdf/e2/92/e29263ebf02f67ba70425395fc307d2de84e4220.pdf

OCR Markdown:
/data/ai4research_assets/documents/e2/92/e29263ebf02f67ba70425395fc307d2de84e4220/document.md

Chunks:
/data/ai4research_assets/chunks/e2/92/e29263ebf02f67ba70425395fc307d2de84e4220/markdown-block-splitter/1-4ecc5f86be65f06e/chunks.jsonl
```

### Rank 2：MemGen

```text
paper_id:
193441da66abb762a59d0b26797d2d30970ee42b

raw_score:
6.1418

relative_score:
90.5 / 100.0

query_coverage:
1.0000
```

最佳证据页：

```text
pages 3-3
pages 1-1
pages 32-33
```

### Rank 3：Synapse

```text
paper_id:
080f386e2413ba0523f32b83d5d8e0a70b005731

raw_score:
5.8899

relative_score:
86.8 / 100.0

query_coverage:
1.0000
```

最佳证据页：

```text
pages 3-4
pages 9-9
pages 30-31
```

---

## 6.6 Demo 证明了什么

元数据阶段：

```text
MIRA rank = 5
```

全文二次检索后：

```text
MIRA rank = 1
```

说明全文检索不是重复元数据排序，而是能够根据正文证据重新判断论文相关性。

最终 Top 3 也不是元数据 Top 3 的简单复制。

---

## 6.7 重复执行的幂等结果

相同命令第二次执行：

```text
PDF claimed:       0
Document claimed:  0
Quality checked:   0
```

五篇 chunk：

```text
Dual-Scale World Memory: reused
Synapse:                 reused
MemGen:                  reused
THOMAS:                  reused
MIRA:                    reused
```

最终论文排名、分数和页码证据保持一致：

```text
1. MIRA
2. MemGen
3. Synapse
```

因此整条链路已验证：

```text
PDF 幂等
OCR 幂等
质量检查幂等
chunk 幂等
BM25 排名稳定
论文聚合稳定
```

---

## 7. 分数语义

### raw_score

```text
BM25 派生的原始排序分
无固定上限
不能跨查询或候选集合直接比较
```

因此不能表示为：

```text
6.7851 / 10
```

### relative_score

```text
本次候选集合最高论文 = 100
其他论文 = raw_score / top_raw_score × 100
```

示例：

```text
MIRA:     100.0 / 100.0
MemGen:    90.5 / 100.0
Synapse:   86.8 / 100.0
```

该分数只适用于当前查询和当前候选集合，不是概率。

---

## 8. 过程可见性

命令会显示：

```text
元数据候选排名
paper ID
元数据命中字段
PDF 下载状态
OCR 页数、字符数和耗时
质量状态
每篇论文的 chunk 数量
chunk written / reused 状态
全文论文排名
raw score
relative score
query coverage
证据页码
章节路径
证据原文预览
PDF 路径
OCR Markdown 路径
chunks.jsonl 路径
manifest.json 路径
```

---

## 9. 保存完整 JSON

```bash
PYTHONPATH="$HOME" python -m \
  ai4research.research_pipeline.scripts_py.process_research_topic_evidence \
  --topic "Agent memory，trajectory" \
  --metadata-candidate-k 5 \
  --final-paper-k 3 \
  --candidate-scan-limit 30 \
  --save-json "$HOME/agent_memory_trajectory_evidence.json"
```

JSON 包括：

```text
元数据候选
PDF/OCR/质量阶段统计
chunk 处理结果
全文 chunk 命中
论文级排名
分数组成
页码证据
chunk ID
资产路径
缺失与错误信息
```

---

## 10. 当前边界

当前完整闭环使用：

```text
元数据词法粗筛
+
chunk BM25 全文检索
+
规则型论文聚合
```

尚未实现：

```text
向量 embedding
向量数据库
BM25 + 向量混合召回
Cross-Encoder rerank
LLM rerank
查询分解
科研事实抽取
Idea 生成与校验
实验设计 Agent
```

下一阶段可以在不修改 PDF、OCR 和 chunk 主链路的前提下增加 embedding 和混合检索。
