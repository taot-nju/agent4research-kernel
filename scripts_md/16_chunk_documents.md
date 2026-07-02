# 16. 将 OCR Markdown 切分为可引用 chunk

本文档说明如何将已经通过质量检查的标准 Markdown 切分为带页码、稳定 ID 和完整来源信息的 chunk 资产。

---

## 1. 功能定位

当前处理链路：

```text
document_asset.status = success
→ quality_status = passed / warning
→ 读取 document.md
→ 页码感知的 Markdown 块解析
→ 字符级 chunk 分组与 overlap
→ DocumentChunk Schema
→ chunks.jsonl + manifest.json
```

本阶段不生成 embedding，也不绑定向量数据库。

---

## 2. 设计依据

真实 GLM-OCR Markdown 存在以下特点：

- 页码使用 `<!-- page: N -->`，稳定可用；
- 章节标题可能是普通文本，也可能使用 Markdown `#`；
- 标题大小写和层级格式不统一；
- 句子可能跨页延续；
- 表格通常保留为 Markdown 表格；
- 公式可能保留为 LaTeX；
- 图注、伪代码和 OCR 错字会混入正文。

因此当前策略是：

```text
页码是强约束
章节标题是弱提示
页面不是强制 chunk 边界
表格和公式尽量保持完整
```

---

## 3. 当前模块

```text
indexing_pipeline/
├── schemas/
│   └── document_chunk.py
├── splitters/
│   ├── base.py
│   ├── markdown_blocks.py
│   └── markdown_block_splitter.py
├── repositories/
│   ├── base.py
│   ├── document_source.py
│   └── jsonl.py
├── pipelines/
│   └── document_chunk_pipeline.py
├── scripts_py/
│   └── chunk_documents.py
└── utils/
    └── storage_paths.py
```

职责分离：

- `DocumentChunk`：chunk 数据结构和稳定 ID；
- `DocumentSplitter`：可替换的切分器接口；
- `MarkdownBlockSplitter`：当前字符级 MVP；
- `ChunkRepository`：可替换的存储接口；
- `JsonlChunkRepository`：当前文件资产实现；
- `document_source`：读取 MongoDB `document_asset`；
- `document_chunk_pipeline`：单篇文档切分与持久化编排；
- CLI：按 paper ID 执行完整流程。

---

## 4. 执行指定论文

命令可在任意当前目录执行：

```bash
PYTHONPATH="$HOME" python -m \
  ai4research.indexing_pipeline.scripts_py.chunk_documents \
  --paper-id <paper_id>
```

只允许质量状态为 `passed`：

```bash
PYTHONPATH="$HOME" python -m \
  ai4research.indexing_pipeline.scripts_py.chunk_documents \
  --paper-id <paper_id> \
  --passed-only
```

默认允许：

```text
quality_status = passed | warning
```

`rejected` 文档不会进入 chunk 流程。

---

## 5. 默认切分参数

```text
target_chars:                   2400
max_chars:                      3200
overlap_chars:                   300
min_chars_before_heading_break:  800
```

自定义示例：

```bash
PYTHONPATH="$HOME" python -m \
  ai4research.indexing_pipeline.scripts_py.chunk_documents \
  --paper-id <paper_id> \
  --target-chars 2600 \
  --max-chars 3600 \
  --overlap-chars 300 \
  --min-chars-before-heading-break 900
```

当前 MVP 使用字符数，不使用特定 tokenizer，因此不绑定 embedding 模型。

---

## 6. 标准资产路径

chunk 资产保存在：

```text
chunks/<id前2位>/<id第3-4位>/<paper_id>/
  <splitter_name>/<splitter_version>-<config_fingerprint>/
```

当前生成：

```text
chunks.jsonl
manifest.json
```

示例：

```text
chunks/19/34/<paper_id>/
  markdown-block-splitter/1-4ecc5f86be65f06e/
    chunks.jsonl
    manifest.json
```

配置指纹由切分器名称、版本和完整配置稳定生成。

---

## 7. DocumentChunk 主要字段

每个 chunk 包含：

```text
chunk_id
paper_id
chunk_index
text
char_count
content_sha256
page_start
page_end
section_path
source_markdown_relative_path
source_markdown_sha256
source_pdf_sha256
source_parser_name
source_parser_version
splitter_name
splitter_version
splitter_options
schema_version
```

`section_path` 来自保守的标题启发式识别，可能为空，不应作为页码证据的替代品。

---

## 8. 稳定 ID 与陈旧资产识别

`chunk_id` 由以下内容共同决定：

```text
paper ID
chunk 序号
chunk 内容 SHA256
页码范围
章节路径
来源 Markdown SHA256
来源 PDF SHA256
解析器名称与版本
切分器名称、版本与配置
Schema 版本
```

因此：

- 相同输入重复切分产生相同 ID；
- 切分配置变化会产生不同 ID；
- Markdown 或 PDF 变化会产生不同 ID；
- 解析器或切分器语义版本变化会产生不同 ID。

同一配置路径下，如果来源 Markdown 已变化，JSONL 和 manifest 会被原子更新。

---

## 9. 幂等性与完整性

首次执行：

```text
status: written
```

输入和配置均未变化时重复执行：

```text
status: reused
```

存储层会同时核验：

- `chunks.jsonl` 的确定性内容；
- `manifest.json`；
- chunk 数量和 ID；
- JSONL SHA256；
- 来源和切分器信息。

如果 JSONL 损坏或来源发生变化，会重新写入资产。manifest 最后提交，作为该组 chunk 资产的完成标记。

---

## 10. 页码与结构语义

当前切分器：

- 从 `<!-- page: N -->` 提取页码；
- 不把页标记写入 chunk 正文；
- 允许一个 chunk 跨页；
- overlap 可能使下一 chunk 的 `page_start` 回到上一页；
- 记录完整的 `page_start` 和 `page_end`；
- 保守识别数字章节、附录章节、ATX 标题和常见特殊标题；
- 避免将 Markdown 表格、公式和明显伪代码误判为标题；
- 普通超长段落可以拆分；
- 表格和公式作为原子块尽量不从中间拆分。

---

## 11. 已验证结果

真实论文：

```text
Infini Memory
pages: 14
chunks: 20

What Spatial Memory Must Store
pages: 23
chunks: 34

MemGen
pages: 34
chunks: 54
```

联合结果：

```text
documents: 3
chunks: 108
page coverage: complete
manifest / JSONL hash audit: passed
repeated execution: reused
```

自动化测试基线：

```text
20 passed
```

测试不连接真实 MongoDB，也不依赖正式资产目录；真实 MongoDB 和正式资产另有手动验证。

---

## 12. 当前边界

当前尚未实现：

- MongoDB 中的 chunk 任务租约与批量状态；
- 多篇文档并发切分；
- token 感知切分；
- 模型辅助章节识别；
- 表格、公式和图注的独立结构化对象；
- embedding 后端；
- 向量数据库；
- BM25 与向量混合检索；
- rerank；
- 面向 Research Agent 的证据返回接口。

当前 JSONL 是 embedding、全文索引和带页码引用的标准输入资产。
