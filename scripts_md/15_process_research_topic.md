# 15. 根据 Research Topic 获取论文 Markdown

## 1. 功能定位

该命令提供当前项目的上层 MVP 工作流：

```text
Research Topic
→ MongoDB 词法召回
→ 筛选具备 PDF 处理条件的论文
→ PDF 下载或复用
→ 文档任务状态刷新
→ OCR 解析或复用
→ 文档质量检查
→ 输出 Markdown 绝对路径
```

入口：

```bash
python -m ai4research.research_pipeline.scripts_py.process_research_topic
```

当前检索器：

```text
mongo-lexical-topic-retriever
version: 2
```

## 2. 前置条件

运行前需要：

1. 激活 `ai4research` Conda 环境；
2. MongoDB 服务可用；
3. GLM-OCR 的 vLLM 服务已启动；
4. OCR 地址默认为：

```text
http://127.0.0.1:9000/v1
```

5. 默认模型名为：

```text
glm-ocr
```

## 3. 只预览候选

预览不会下载 PDF、不会执行 OCR，也不会修改数据库：

```bash
cd ~

python -m ai4research.research_pipeline.scripts_py.process_research_topic \
  --topic "agent memory" \
  --top-k 3 \
  --preview
```

## 4. 执行完整工作流

```bash
cd ~

python -m ai4research.research_pipeline.scripts_py.process_research_topic \
  --topic "agent memory" \
  --top-k 3
```

成功后，终端最后会输出：

```text
READY_MARKDOWN_PATHS
```

其下每一行都是一篇论文的 Markdown 绝对路径，例如：

```text
/data/ai4research_assets/documents/ac/7d/<paper_id>/document.md
```

## 5. 自动补位语义

`--top-k` 表示目标处理论文数量。

系统会跳过以下候选：

- PDF 尚未下载；
- 同时也不存在任何可用 PDF URL。

然后从后续高相关候选中自动补位。

默认最多检查前 30 个高相关候选：

```text
--candidate-scan-limit 30
```

可调整为：

```bash
python -m ai4research.research_pipeline.scripts_py.process_research_topic \
  --topic "agent memory" \
  --top-k 10 \
  --candidate-scan-limit 100
```

如果候选池中可处理论文不足，或者实际下载、OCR、质检失败，
最终 Markdown 路径数量仍可能少于 `top-k`。

## 6. 三个数量参数的区别

### `--top-k`

最终希望处理并返回的相关论文数量。

默认：

```text
3
```

### `--candidate-scan-limit`

按相关性排序后，为自动补位而检查的候选数量。

默认：

```text
30
```

### `--candidate-pool-size`

从 MongoDB 初步读取并参与词法评分的候选池上限。

默认：

```text
1000
```

一般应满足：

```text
candidate_pool_size >= candidate_scan_limit >= top_k
```

## 7. 幂等性

命令可以安全重复运行。

如果论文已经完成：

- PDF 下载会跳过；
- OCR 会跳过；
- 已有质量结果默认会跳过；
- 已生成的 Markdown 路径仍会正常输出。

因此，相同查询重复执行不会重复消耗 OCR 资源。

## 8. 保存完整 JSON 结果

```bash
python -m ai4research.research_pipeline.scripts_py.process_research_topic \
  --topic "agent memory" \
  --top-k 3 \
  --save-json ~/agent_memory_result.json
```

JSON 中包括：

- Topic；
- 检索器名称与版本；
- 候选论文；
- 检索分数；
- 命中字段；
- PDF、文档和质量状态；
- Markdown 相对路径与绝对路径；
- 各阶段统计；
- 错误信息。

## 9. 性能参数

增加单篇论文的页面 OCR 并发：

```bash
--page-workers 8
```

增加 PDF 下载并发：

```bash
--download-workers 4
```

调整 PDF 页面渲染清晰度：

```bash
--render-dpi 200
```

当前 OCR 并发主要位于单篇论文的页面级别。

未来增加 GPU 时，可以扩展为：

- 多个 OCR 服务实例；
- OCR 后端负载均衡；
- 多篇论文并发解析；
- 分布式任务 Worker。

现有 `TopicRetriever`、`PageOCRBackend` 和任务仓储接口可继续复用。

## 10. 当前检索评分

当前是可解释的词法检索，不是百分制。

主要加分来源：

- 完整 Topic 出现在标题；
- 完整 Topic 出现在摘要；
- 单个查询词出现在标题；
- 单个查询词出现在摘要；
- 查询词出现在关键词或标签；
- 查询词覆盖率。

同分时依次按以下字段稳定排序：

1. 分数降序；
2. 标题字母顺序；
3. paper ID。

PDF 或 OCR 是否完成不参与相关性评分。

## 11. 当前边界

当前版本尚未实现：

- 语义向量检索；
- BM25 与向量混合检索；
- Markdown 切分为 chunk；
- embedding 与向量数据库；
- 基于全文的二次排序；
- 多篇论文并行 OCR；
- 面向 Agent 的最终答案生成。

当前输出的 Markdown 是后续 chunk、embedding、全文检索和论文分析的标准输入。
