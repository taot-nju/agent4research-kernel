# ai4research Capability Ledger

> 项目能力台账：记录已经交付、可手工调用、可验证的功能。
> 更新规则：每完成一个新功能或模块，就在本文件增加或更新一条记录。

## 当前主线

```text
候选论文 → PDF / OCR Markdown → chunk → BM25 / bge-m3 vector
→ hybrid ranking → retrieval suite evaluation → evidence output
```

当前默认检索策略：

```text
bm25_bge_m3_subchunk_hybrid_w070_030
```

- BM25 权重：0.7
- bge-m3 subchunk vector 权重：0.3
- 评估集：`retrieval_suite_v1`（8 cases）

## 已完成能力

| capability_id | 状态 | 功能 | 手工入口 | 验证 | 关键资产 |
|---|---|---|---|---|---|
| `ocr-to-markdown` | done | PDF 或单张图片经 GLM-OCR 转为 Markdown | `python -m ai4research.document_pipeline.scripts_py.ocr_to_markdown --help` | `tests/document_pipeline/test_ocr_to_markdown_cli.py` | OCR Markdown、OCR report JSON |
| `document-chunking` | done | Markdown 切分为带页码、section、稳定 ID 的 chunk | `python -m ai4research.indexing_pipeline.scripts_py.chunk_documents --help` | chunk 相关 tests | `chunks.jsonl`、manifest |
| `bm25-retrieval-baseline` | frozen | 候选论文全文 BM25 检索与论文级聚合 | `python -m ai4research.indexing_pipeline.scripts_py.search_candidate_fulltext --help` | retrieval suite | `retrieval_suite_v1_bm25_baseline_summary.json` |
| `retrieval-evaluation` | done | 对已保存论文排序计算 MRR、AP、P@k、R@k、nDCG@k | `python -m ai4research.indexing_pipeline.scripts_py.evaluate_saved_retrieval --help` | evaluation tests | 各 case metrics JSON |
| `token-hash-vector-demo` | done | 本地 token-hash embedding 与 vector search 验证链路 | `python -m ai4research.indexing_pipeline.scripts_py.run_vector_suite --help` | vector tests | token-hash suite outputs |
| `embed-text` | done | 单文本 embedding 的手工测试入口；支持 token-hash 与 OpenAI-compatible | `python -m ai4research.indexing_pipeline.scripts_py.embed_text --help` | `tests/indexing_pipeline/test_embed_text_cli.py` | embedding JSON demo |
| `bge-m3-vector-subchunk` | preferred | bge-m3 向量检索；超长 chunk 按 3200 字符 subchunk 覆盖 | `python -m ai4research.indexing_pipeline.scripts_py.run_vector_suite --help` | full 8-case suite | `bge_m3_vector_v1_subchunk_3200/` |
| `hybrid-ranking` | preferred | 融合 BM25 与 bge-m3 论文级结果 | `python -m ai4research.indexing_pipeline.scripts_py.fuse_saved_paper_rankings --help` | fusion tests | hybrid search JSON |
| `hybrid-suite` | preferred | 全 retrieval suite 的 hybrid 运行、指标与汇总 | `python -m ai4research.indexing_pipeline.scripts_py.run_hybrid_suite --help` | full 8-case suite | `bm25_bge_m3_subchunk_hybrid_v1_w070_030/` |
| `search-candidate-hybrid` | done | 对已有 chunk 资产的一组候选论文执行推荐 BM25 0.7 + bge-m3 subchunk vector 0.3 检索，并输出 evidence JSON | `python -m ai4research.indexing_pipeline.scripts_py.search_candidate_hybrid --help` | `tests/indexing_pipeline/test_search_candidate_hybrid_cli.py` | `hybrid_candidate_mvp_smoke/` |
| `search-topic-hybrid-bridge` | done | 读取 process_research_topic 保存的 workflow JSON，只选择 ready=True 论文并调用推荐 hybrid；不重跑 PDF/OCR | `python -m ai4research.indexing_pipeline.scripts_py.search_topic_hybrid --help` | `tests/indexing_pipeline/test_search_topic_hybrid_cli.py` | `topic_hybrid_bridge_smoke/` |
| `topic-evidence-dossier` | done | 读取真实 topic workflow JSON 与 hybrid JSON，生成带论文标题、排名、页码、section 与证据摘录的 Markdown dossier；不调用 LLM | `python -m ai4research.indexing_pipeline.scripts_py.build_topic_evidence_dossier --help` | `tests/indexing_pipeline/test_build_topic_evidence_dossier_cli.py` | `topic_workflows/llm_agent_long_term_memory_consolidation_retention_forgetting_top5_evidence_dossier.md` |
| `topic-research-brief` | done | 读取真实 topic workflow JSON 与 evidence dossier Markdown，生成最小 evidence-backed research brief Markdown；当前为结构化 MVP，不添加未经证据支持的结论 | `python -m ai4research.indexing_pipeline.scripts_py.build_topic_research_brief --help` | `tests/indexing_pipeline/test_build_topic_research_brief_cli.py`；`tests/indexing_pipeline/test_build_topic_research_brief.py` | `topic_workflows/llm_agent_long_term_memory_consolidation_retention_forgetting_top5_research_brief.md` |
| `retrieval-experiment-registry` | done | 记录 baseline、权重扫描、推荐策略与待办 | 无独立 CLI；由 JSON 资产维护 | `tests/indexing_pipeline/test_retrieval_experiment_registry.py` | `retrieval_suite_v1_experiment_registry.json` |
| `embedding-audit` | done | 扫描 embedding cache，核验模型、维度、subchunk、重复 ID、读取错误 | `python -m ai4research.indexing_pipeline.scripts_py.audit_embedding_run --help` | `tests/indexing_pipeline/test_audit_embedding_run.py` | `bge_m3_subchunk_3200_embedding_audit.json` |
| `rerank-texts-manual-cli` | done | 对 query 与多条候选文本调用 bge-m3 /v1/rerank 并按相关性排序 | `python -m ai4research.indexing_pipeline.scripts_py.rerank_texts --help` | `tests/indexing_pipeline/test_rerank_texts_cli.py` | `rerank_texts_bge_m3_demo.json` |
| `rerank-hybrid-candidates` | full-suite-validated-experimental | 展开 hybrid evidence、按 chunk 去重与完整分段、调用 bge-m3 rerank，聚合为可评估论文排序；全 suite 未优于默认 hybrid | `python -m ai4research.indexing_pipeline.scripts_py.rerank_hybrid_candidates --help` | `tests/indexing_pipeline/test_reranking.py`；`tests/indexing_pipeline/test_rerank_hybrid_candidates_cli.py` | `bm25_bge_m3_subchunk_rerank_v1/` |
| `rerank-suite-runner` | full-suite-validated-experimental | 逐 case 读取已保存 hybrid 结果，运行 rerank、评估并生成 suite summary；结果不替代推荐 hybrid | `python -m ai4research.indexing_pipeline.scripts_py.run_rerank_suite --help` | `tests/indexing_pipeline/test_run_rerank_suite_cli.py` | `bm25_bge_m3_subchunk_rerank_v1/` |

## 当前推荐基线

| 策略 | MRR | AP | P@5 | R@5 | nDCG@5 |
|---|---:|---:|---:|---:|---:|
| BM25 | 0.9375 | 0.8052 | 0.6000 | 0.7125 | 0.8071 |
| bge-m3 subchunk vector | 0.8750 | 0.7734 | 0.6750 | 0.7750 | 0.7397 |
| Hybrid: BM25 0.7 + bge-m3 0.3 | 0.9375 | 0.8228 | 0.6250 | 0.7333 | 0.8235 |

## 已验收真实工作流

| run_id | topic | workflow JSON | hybrid JSON | 验收结果 |
|---|---|---|---|---|
| `long-term-memory-forgetting-top5` | `LLM agent long-term memory consolidation retention forgetting` | `topic_workflows/llm_agent_long_term_memory_consolidation_retention_forgetting_top5.json` | `topic_workflows/llm_agent_long_term_memory_consolidation_retention_forgetting_top5_hybrid_search_output.json` | `ready=5/5`，`chunk_ready=5/5`，`loaded=5/5`，`missing=0` |

## 下一步

| priority | capability_id | 目标 |
|---|---|---|
| high | `evidence-backed-research-brief` | 读取真实 topic hybrid JSON，生成可核查的结构化研究简报：论文、核心机制、证据页码/section、局限与跨论文观察 |
| later | `rerank-hybrid-fusion-scan` | 仅在后续需要继续优化检索时，扫描已保存 hybrid 与 rerank ranking 的保守固定融合权重；只有 suite-level 改善才考虑升级默认策略 |
| later | `dynamic-weighting` | 探索 query-aware 的 BM25/vector 权重 |
| later | `embedding-audit-extension` | 仅在确有需求时增加更细的按 case 审计 |

## 更新约定

每个新能力完成时，至少补充：

1. `capability_id` 与状态；
2. 功能一句话说明；
3. `python -m ... --help` 手工入口；
4. 最小 demo 或关键产物；
5. 对应测试文件；
6. 是否替代了旧能力，以及原因。
