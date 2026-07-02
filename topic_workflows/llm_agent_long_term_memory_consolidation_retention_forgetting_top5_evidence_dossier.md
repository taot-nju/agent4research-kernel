# Topic Evidence Dossier

## Scope

- Workflow topic: `LLM agent long-term memory consolidation retention forgetting`
- Retrieval query: `LLM agent long-term memory consolidation retention forgetting`
- Workflow JSON: `/home/tao/ai4research/topic_workflows/llm_agent_long_term_memory_consolidation_retention_forgetting_top5.json`
- Hybrid JSON: `/home/tao/ai4research/topic_workflows/llm_agent_long_term_memory_consolidation_retention_forgetting_top5_hybrid_search_output.json`
- Strategy: `bm25_bge_m3_subchunk_hybrid`
- Fusion weights: BM25=0.7; bge-m3=0.3
- Evidence policy: this dossier reports retrieved source text and metadata; it does not infer unsupported mechanisms, claims, or limitations.

## Ranked Paper Overview

| rank | paper | hybrid score | BM25 evidence section | bge-m3 evidence section |
|---:|---|---:|---|---|
| 1 | Cache What Lasts: Token Retention for Memory-Bounded KV Cache in LLMs | 1.000000 | 4 METHODOLOGY > 4.1 SELECTIVE IN-CONTEXT MEMORY VIA RETENTION-GATED ATTENTION | 4 METHODOLOGY > 4.2 TRAINING |
| 2 | RMAAT: Astrocyte-Inspired Memory Compression and Replay for Efficient Long-Context Transformers | 0.780300 | 3 THE RMAAT MODEL > 3.3 ASTROCYTE-INSPIRED MEMORY MECHANISM | 4 EXPERIMENTS > 4.2 ABLATION STUDIES |
| 3 | Beyond a Million Tokens: Benchmarking and Enhancing Long-Term Memory in LLMs | 0.475353 | A DETAILED RELATED WORK | ABSTRACT |
| 4 | GraphPlanner: Graph Memory-Augmented Agentic Routing for Multi-Agent LLMs | 0.189623 | 1 INTRODUCTION | ABSTRACT |
| 5 | AgentGym-RL: An Open-Source Framework to Train LLM Agents for Long-Horizon Decision Making via Multi-Turn RL | 0.120155 | H COMPARATIVE CASE ANALYSIS | F ANALYSIS ABOUT THE INSTABILITY OF LONG-HORIZON TRAINING |

## Paper Evidence

### 1. Cache What Lasts: Token Retention for Memory-Bounded KV Cache in LLMs

- Paper ID: `e8452a87398ee3eacb8dd1b622e2eb91a2da3f26`
- Hybrid score: `1.000000`
- Topic workflow status: PDF=`success`; document=`success`; quality=`passed`
- Venue / source: `ICLR 2026`

#### Retrieved Evidence

##### bm25 evidence 1

- Chunk score: `17.009647`
- Location: pages `5`-`5`; section `4 METHODOLOGY > 4.1 SELECTIVE IN-CONTEXT MEMORY VIA RETENTION-GATED ATTENTION`
- Chunk ID: `16e753ff3dcfcd6e1185c8e031e207e8b8de1686d0aa6af0f0177c6939463dd2`

> attention. By incorporating the retention score into the exponential term, the attention weight can be written as $\exp\left(\mathbf{q}_t^\top \mathbf{k}_i + (t - i) \log \beta_i\right)$, which reveals that the retention score acts as an additive bias on the attention logits (Press et al., 2021). Token Retention vs. Attention Scores. In standard self-attention, the importance of a past token $i$ at decoding step $t$ is given by $a_{ti} \propto \exp\left(\mathbf{q}_t^\top \mathbf{k}_i\right)$, which depends explicitly on the current query $\mathbf{q}_t$. These scores capture short-term utility ...

##### bge-m3 evidence 1

- Chunk score: `0.617069`
- Location: pages `5`-`6`; section `4 METHODOLOGY > 4.2 TRAINING`
- Chunk ID: `55aaedb0c620c7503d3c67b8e9f87d333bc49ec3e71302b4a831a018ac90fdcb`

> into attention, enabling dynamic prioritization of recent or salient tokens while discarding less useful context, akin to human memory. Unlike prior work that applies the forgetting curve to retrieval-augmented generation (Zhong et al., 2024), we integrate it directly into the attention mechanism. 4.2 TRAINING Our goal is to train the retention gate $g$ so that the LLM can preserve response quality under a memory constraint, thereby bridging the gap with the inference stage. Instead of training a separate gate for each layer and head, as formulated in Problem (2), we optimize all retention gat...

#### Analyst Notes

- Mechanism hypothesis (to verify against the cited evidence):
- Relevance to the topic:
- Limitations / open questions:

### 2. RMAAT: Astrocyte-Inspired Memory Compression and Replay for Efficient Long-Context Transformers

- Paper ID: `b8560728b739f3788fc9639b1db240b201f71f0e`
- Hybrid score: `0.780300`
- Topic workflow status: PDF=`success`; document=`success`; quality=`passed`
- Venue / source: `ICLR 2026`

#### Retrieved Evidence

##### bm25 evidence 1

- Chunk score: `15.266655`
- Location: pages `6`-`7`; section `3 THE RMAAT MODEL > 3.3 ASTROCYTE-INSPIRED MEMORY MECHANISM`
- Chunk ID: `a3d75c2e1b3e51902042fd8d08198d69ab456a7393271234686385bd3c2deb84`

> as described in the first paragraph). Calculating $H_{astro} = \frac{1}{m} \phi(R)^T V$ (Eq. 4) thus integrates a form of spatial context whose use is directly motivated by its analogy to simulated astrocyte STP behavior. This offers a flexible, learnable, and biologically-grounded method for incorporating relative positional context, distinct from standard approaches lacking this neuro-glial justification. Having addressed this spatially-informed component of attention, we now turn to the temporal memory mechanisms essential for processing long sequences. 3.3 ASTROCYTE-INSPIRED MEMORY MECHANI...

##### bge-m3 evidence 1

- Chunk score: `0.591062`
- Location: pages `10`-`10`; section `4 EXPERIMENTS > 4.2 ABLATION STUDIES`
- Chunk ID: `3ad43ff23dff73768c52874cd96ec9f2c96b4d4a0d45859395f29ee8e756d7aa`

> to RMT’s standard BPTT and $O(N^2)$ attention. To validate the contributions of RMAAT’s core components, we performed several ablation studies, primarily focusing on the long-context Byte-Level Document Retrieval ($8K$) task, supplemented by sensitivity analysis on other tasks (See Appendix F). 4.2 ABLATION STUDIES **Memory Retention Factor (Contributions 1 & 2):** Removing the retention factor significantly reduced accuracy on the Retrieval task ($83.2\% \rightarrow 80.5\%$) without changing memory usage ($3.4$ GB), confirming its vital role in context compression derived from the LTP macro m...

#### Analyst Notes

- Mechanism hypothesis (to verify against the cited evidence):
- Relevance to the topic:
- Limitations / open questions:

### 3. Beyond a Million Tokens: Benchmarking and Enhancing Long-Term Memory in LLMs

- Paper ID: `310c7455f4cb768645a3ac1b8e44af51c8394501`
- Hybrid score: `0.475353`
- Topic workflow status: PDF=`success`; document=`success`; quality=`passed`
- Venue / source: `ICLR 2026`

#### Retrieved Evidence

##### bm25 evidence 1

- Chunk score: `10.274303`
- Location: pages `17`-`17`; section `A DETAILED RELATED WORK`
- Chunk ID: `f03618f98e89e5d93633ab663457b42565c465858f85398bcbcc9402be91568d`

> 2024)) further expand capabilities, while inference optimizations such as PagedAttention (Kwon et al., 2023), KV-cache compression (H2O, SnapKV; (Zhang et al., 2023; Li et al., 2024)) and distributed approaches (Ring Attention; (Liu et al., 2023)) enable practical deployment at scale. Long-Term Memory Methods. Researchers have developed approaches to enhance long-term memory beyond simply extending context windows. Architectural modifications include Transformer-XL (Dai et al., 2019), which introduced segment-level recurrence, and Compressive Transformer (Rae et al., 2019), which stored both r...

##### bge-m3 evidence 1

- Chunk score: `0.600187`
- Location: pages `1`-`1`; section `ABSTRACT`
- Chunk ID: `3ea0800cc97ce2fe04b15df1a4cdbd18965a0b4a82d718a62d915920795d19fe`

> BEYOND A MILLION TOKENS: BENCHMARKING AND ENHANCING LONG-TERM MEMORY IN LLMs Mohammad Tavakoli1, Alireza Salemi2, Carrie Ye1, Mohamed Abdalla1, Hamed Zamani2, J. Ross Mitchell1 1University of Alberta 2University of Massachusetts Amherst {tavakol5, cye, mabdall2, jmitche2}@ualberta.ca {asalemi, zamani}@cs.umass.edu ABSTRACT Evaluating the abilities of large language models (LLMs) for tasks that require long-term memory and thus long-context reasoning, for example in conversational settings, is hampered by the existing benchmarks, which often lack narrative coherence, cover narrow domains, and o...

#### Analyst Notes

- Mechanism hypothesis (to verify against the cited evidence):
- Relevance to the topic:
- Limitations / open questions:

### 4. GraphPlanner: Graph Memory-Augmented Agentic Routing for Multi-Agent LLMs

- Paper ID: `7b8c64311437786773b8cfea5f778e6acb61df5f`
- Hybrid score: `0.189623`
- Topic workflow status: PDF=`success`; document=`success`; quality=`passed`
- Venue / source: `ICLR 2026`

#### Retrieved Evidence

##### bm25 evidence 1

- Chunk score: `9.618850`
- Location: pages `2`-`2`; section `1 INTRODUCTION`
- Chunk ID: `775a72653f7a0d2ae3a4c7f4f6ca01cff19aa6fc5ca91a9c34bfb24ecd233276`

> GraphPlanner is a multi-agent coordination problem, where the router must decide not only which LLM backbone to invoke but also which agent role to activate at each step. This shift is crucial because agentic LLM routers can explicitly model specialization and cooperation across multiple agents, turning independent calls into structured workflows. Yet, building an effective agentic LLM router is far from trivial and comes with several challenges. First, the relations among queries, responses, and LLM candidates are highly diverse and complex in agentic settings. Unlike single-step assignments,...

##### bge-m3 evidence 1

- Chunk score: `0.552638`
- Location: pages `1`-`1`; section `ABSTRACT`
- Chunk ID: `cd644830a5234e74f666d5f4d1c15ba8b0caf558bd8360f4fef523cdd1c16525`

> GRAPHPLANNER: GRAPH MEMORY-AUGMENTED AGENTIC ROUTING FOR MULTI-AGENT LLMs Tao Feng, Haozhen Zhang, Zijie Lei, Peixuan Han, Jiaxuan You Department of Computer Science University of Illinois Urbana Champaign Urbana, IL, USA {taofeng2, jiaxuan}@illinois.edu ABSTRACT LLM routing has achieved promising results in integrating the strengths of diverse models while balancing efficiency and performance. However, to support more realistic and challenging applications, routing must extend into agentic LLM settings—where task planning, multi-round cooperation among heterogeneous agents, and memory utiliza...

#### Analyst Notes

- Mechanism hypothesis (to verify against the cited evidence):
- Relevance to the topic:
- Limitations / open questions:

### 5. AgentGym-RL: An Open-Source Framework to Train LLM Agents for Long-Horizon Decision Making via Multi-Turn RL

- Paper ID: `cd4eb31961a1eda5f2806c6d7d73e5c9de8b2a84`
- Hybrid score: `0.120155`
- Topic workflow status: PDF=`success`; document=`success`; quality=`passed`
- Venue / source: `ICLR 2026`

#### Retrieved Evidence

##### bm25 evidence 1

- Chunk score: `6.430790`
- Location: pages `33`-`34`; section `H COMPARATIVE CASE ANALYSIS`
- Chunk ID: `85c2824c09ea4f9577ac0281b2a14d73db2af609605be1c00e1652374427da54`

> navigating to the blue box while the base model fails to complete the task. H COMPARATIVE CASE ANALYSIS Figure 19 shows a case from the TextCraft environment. The short-horizon agent fails because it uses incorrect quantities (violating crafting constraints) and drifts from the goal of crafting an orange bed. In contrast, our agent succeeds by adhering to constraints and managing resources strategically: it proactively checks inventory, adaptively explores alternatives (e.g., crafting intermediate items), and efficiently acquires materials to resolve shortages. This showcases stronger long-ter...

##### bge-m3 evidence 1

- Chunk score: `0.578352`
- Location: pages `31`-`31`; section `F ANALYSIS ABOUT THE INSTABILITY OF LONG-HORIZON TRAINING`
- Chunk ID: `bb1581287bbf2b6ef307401e8ac5ebad7f1c51225a9c57ae5252f926d732e6fc`

> from 10 to 15 and then to 20, with each transition occurring every 200 step. We employ GRPO as the main RL algorithm with a learning rate of $1 \times 10^{-6}$, a KL coefficient of $1 \times 10^{-3}$, and a sampling temperature of 1.0. We sample 8 distinct trajectories for a single query. F ANALYSIS ABOUT THE INSTABILITY OF LONG-HORIZON TRAINING From a theoretical perspective, for a given query, an LLM agent performs multiple rounds of interaction, where each round is a ReAct step (Reasoning with an Action). Each step consists of multiple tokens, so the entire interaction produces a large volu...

#### Analyst Notes

- Mechanism hypothesis (to verify against the cited evidence):
- Relevance to the topic:
- Limitations / open questions:

## Cross-paper Analysis Prompts

- Which papers address persistent agent memory directly, and which address adjacent long-context or retention mechanisms?
- What information is retained, compressed, replayed, or selectively forgotten in each approach?
- Which claims have direct evidence above, and which would need additional targeted retrieval before synthesis?

