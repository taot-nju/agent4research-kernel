# agent4research-kernel

面向 AI Research Agent 的论文数据、全文资产与检索编排内核。

本项目不止是论文爬虫。它负责把多源论文元数据、PDF、OCR 文档和处理状态沉淀为可追踪、可恢复、可扩展的数据资产，并为后续的全文切分、语义检索和 Research Agent 提供统一入口。

> 仓库名为 `agent4research-kernel`；当前 Python 包目录名为 `ai4research`。

---

## 1. 项目定位

`agent4research-kernel` 的定位是：

```text
Research-agent data infrastructure
```

也就是：

```text
面向 Research Agent 的论文数据与检索内核
```

它主要解决的问题包括：

1. 从多个论文来源采集 AI 相关论文数据；
2. 为每篇论文构建统一的结构化画像；
3. 将论文数据写入 MongoDB；
4. 支持论文去重、字段补全、来源追踪和分类追踪；
5. 支持后续 PDF 下载、正文解析、参考文献抽取和目录抽取；
6. 支持从论文中抽取方法、任务、数据集、baseline、benchmark、metric 等科研要素；
7. 支持后续相关论文检索、idea matching、baseline 推荐和 benchmark 推荐；
8. 为未来的 Research Agent 提供可查询、可分析、可扩展的数据底座。

一句话概括：

```text
本项目不是简单的论文爬虫，而是面向 AI 研究的结构化论文知识底座。
```

---

---

## 2. 当前已实现功能总览

截至 2026-06-20，以下主链路已经跑通：

```text
多源论文元数据采集
→ MongoDB 统一存储与去重融合
→ PDF 自动下载与资产校验
→ GLM-OCR 文档解析
→ 基础质量检查
→ 根据 Research Topic 召回论文
→ 自动复用或补齐 PDF/OCR 资产
→ 输出可用 Markdown 路径
```

| 能力 | 状态 | 说明 |
|---|---|---|
| 多源元数据采集 | 已完成 | arXiv、OpenReview、PMLR、ICML Official、AAAI Official、ACL Anthology |
| MongoDB Schema、索引、迁移 | 已完成 | 支持统一记录、去重、多源融合和历史 Schema 迁移 |
| PDF 下载与管理 | 已完成 | 支持候选 URL 解析、校验、失败重试、租约、并发和幂等执行 |
| GLM-OCR 接入 | MVP 已完成 | 通过 OpenAI-compatible 接口调用本地 vLLM 服务 |
| 标准文档输出 | MVP 已完成 | 输出逐页 Markdown 和 `parse_report.json` |
| 文档质量检查 | MVP 已完成 | 检查页数、页标记、字符数、标题和解析报告 |
| Topic 到 Markdown 编排 | MVP 已完成 | 词法召回、无 PDF 候选补位、下载、OCR、质检、路径输出 |
| 自动化测试 | 已建立 | 当前 7 项测试通过 |
| chunk / embedding / 向量检索 | 未开始 | 下一阶段重点 |
| 全文二次排序与答案生成 | 未开始 | 后续 Research Agent 能力 |

---

## 3. 当前项目结构

### 3.1 分层架构

```text
data_pipeline
    论文元数据采集、Schema、MongoDB 与查询
        ↓
fulltext_pipeline
    PDF 候选解析、下载、校验与任务状态管理
        ↓
document_pipeline
    PDF 页面渲染、OCR、Markdown 生成与质量检查
        ↓
research_pipeline
    Topic 召回与跨模块工作流编排
```

各层通过 Schema、仓储接口和任务状态衔接。上层编排负责组合能力，底层模块不反向依赖上层，因此可以独立替换检索器、OCR 后端、解析器或质量检查器。

### 3.2 目录结构

```text
ai4research/
├── data_pipeline/
│   ├── crawlers/                 # 各数据源爬虫
│   ├── db_ops/                   # 查询、字段检查和论文仓储
│   ├── db_settings/              # MongoDB 连接、配置与索引
│   ├── pipelines/                # 各来源采集流程
│   ├── schemas/                  # 统一论文 Schema
│   ├── scripts_py/               # 数据采集与数据库 CLI
│   ├── source_configs/           # 数据源配置
│   └── utils/
├── fulltext_pipeline/
│   ├── downloaders/              # 下载器和域名限速
│   ├── pipelines/                # 串行/并发 PDF 下载 Runner
│   ├── repositories/             # PDF 任务领取、租约和状态更新
│   ├── scripts_py/               # PDF 下载、审计和恢复 CLI
│   └── utils/                    # URL 解析、PDF 校验和存储路径
├── document_pipeline/
│   ├── ocr_backends/             # OCR 后端统一接口及 OpenAI-compatible 实现
│   ├── parsers/                  # 文档解析器接口和 OCR 解析器
│   ├── pipelines/                # 文档解析与质量检查 Runner
│   ├── quality_checks/           # 文档质量检查接口及基础实现
│   ├── repositories/             # 文档任务与质量状态仓储
│   ├── schemas/                  # 文档资产结构
│   ├── scripts_py/               # 解析、状态刷新和质检 CLI
│   └── utils/                    # 文档资产路径
├── research_pipeline/
│   ├── retrieval/                # TopicRetriever 与 MongoDB 词法召回
│   ├── pipelines/                # Topic → Markdown 上层编排
│   └── scripts_py/               # 对外 CLI
├── tests/
│   ├── document_pipeline/
│   └── research_pipeline/
├── scripts_md/                   # 分阶段操作手册
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

---

## 4. 整体数据流

当前项目形成了从论文来源到 Agent 可消费 Markdown 的连续数据流：

```text
多源元数据采集
→ MongoDB 统一 Schema、去重和来源追踪
→ PDF 候选解析、下载与校验
→ PDF 页面渲染和 GLM-OCR
→ 标准 Markdown 与 parse_report.json
→ 基础文档质量检查
→ Research Topic 召回与跨模块编排
→ READY_MARKDOWN_PATHS
```

各层通过 Schema、仓储接口和任务状态衔接。底层模块不反向依赖上层编排，因此召回器、OCR 后端、解析器、质量规则和并发方式都可以独立替换。

元数据采用逐篇 upsert；PDF 和文档任务采用原子领取、租约、Worker 所有权、失败重试、临时文件和原子提交。重复运行会复用成功资产。

---

## 5. 环境准备

### 5.1 Python 环境

建议使用 Python 3.10+。

安装依赖：

```bash
pip install -r requirements.txt
```

当前主要依赖：

| 包 | 版本 | 用途 |
|---|---|---|
| `arxiv` | 2.3.1 | arXiv API 论文检索 |
| `beautifulsoup4` | 4.14.3 | HTML 页面解析 |
| `pymongo` | 4.17.0 | MongoDB 驱动 |
| `requests` | 2.32.5 | HTTP 请求 |
| `rich` | 15.0.0 | 终端美化输出 |
| `tqdm` | 4.67.3 | 进度条显示 |
| `openreview-py` | latest | OpenReview API 访问 |

---

### 5.2 MongoDB

当前默认连接本地 MongoDB。

配置文件：

```text
data_pipeline/db_settings/mongo_config.py
```

默认配置：

```python
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "ai4research"
COLLECTION_NAME = "papers"
```

默认数据库与集合：

```text
Database: ai4research
Collection: papers
```

---

### 5.3 文档处理新增依赖

主环境已经验证：

```text
Python 3.10
openai==2.43.0
PyMuPDF==1.27.2.3
```

开发测试依赖：

```text
-r requirements.txt
pytest==9.1.0
```

### 5.4 全文资产与 OCR 服务

当前 MVP 使用 GLM-OCR，并通过 vLLM 暴露 OpenAI-compatible API。

示例启动命令：

```bash
vllm serve <GLM_OCR_MODEL_PATH> \
  --allowed-local-media-path / \
  --port 9000 \
  --speculative-config '{"method": "mtp", "num_speculative_tokens": 1}' \
  --served-model-name glm-ocr
```

健康检查：

```bash
curl --fail --silent --show-error \
  http://127.0.0.1:9000/v1/models
```

默认 OCR 配置：

```text
base_url:       http://127.0.0.1:9000/v1
model_name:     glm-ocr
timeout:        300 seconds
render_dpi:     200
page_workers:   4
max_tokens:     8192
temperature:    0.0
```

OCR 服务地址和模型名由 `document_pipeline/config.py` 集中管理，可通过环境变量覆盖。解析器只依赖 `PageOCRBackend` 接口，后续可以接入其他本地服务、云端 API 或负载均衡后端。

全文资产根目录由 `AI4RESEARCH_DATA_ROOT` 指定。服务器当前使用 `/data/ai4research_assets`，未设置时默认使用 `~/ai4research_assets`。

---

## 6. 初始化数据库

首次使用时，需要初始化数据库索引。

在项目父目录执行：

```bash
python -m ai4research.data_pipeline.scripts_py.init_db
```

正常输出示例：

```text
✅ MongoDB connected successfully.
✅ MongoDB indexes initialized successfully.
```

索引初始化逻辑位于：

```text
data_pipeline/db_settings/init_indexes.py
```

索引用于加速常用查询和去重检查，例如标题、来源 ID、venue/year、标签、参考文献等字段。具体索引字段以 `init_indexes.py` 中的实现为准。

---

---

## 7. 统一论文 Schema

论文统一 Schema 定义在：

```text
data_pipeline/schemas/paper_schema.py
```

当前 Schema 版本号为：

```python
CURRENT_SCHEMA_VERSION = 1
```

所有论文记录默认基于：

```python
DEFAULT_PAPER_FIELDS
```

进行初始化。

当前每篇论文记录主要包括以下字段：

```text
title
aliases
authors
abstract
abstract_entities
arxiv_obj
openreview_obj
aaai_obj
official_obj
acl_anthology_obj
seen_in_categories
accepted_by
base_urls
more_urls
cite_numbers
tags
toc_tree
references
keywords
summary_short
summary_long
txt_contributions
txt_scientific_question
pipeline
baselines
benchmarks
metrics
processing_status
local_txt_path
local_pdf_path
local_json_path
seen_in_sources
edit_logs
```

此外，数据库记录中还会包含 MongoDB `_id` 以及用于版本管理的 schema version 字段。

---

### 7.1 基础信息字段

```python
"title": ""
"aliases": []
"authors": []
"abstract": ""
"abstract_entities": []
```

说明：

- `title`：论文标题；
- `aliases`：论文别名，例如方法简称、全称、常见别称；
- `authors`：作者列表；
- `abstract`：论文摘要；
- `abstract_entities`：从摘要中抽取的实体，例如模型、任务、数据集等。

其中，`title`、`authors`、`abstract` 通常可以从数据源直接获取；`abstract_entities` 属于后续处理字段。

---

### 7.2 arXiv 特有字段

```python
"arxiv_obj": {
    "arxiv_id": "",
    "arxiv_url": "",
    "arxiv_pdf_url": "",
    "arxiv_categories": [],
    "comment": "",
    "doi": "",
    "submission_history": [
        {
            "version": "",
            "date": ""
        }
    ]
}
```

说明：

- `arxiv_id`：arXiv 编号；
- `arxiv_url`：arXiv abstract 页面；
- `arxiv_pdf_url`：arXiv PDF 链接；
- `arxiv_categories`：arXiv 分类，例如 `cs.AI`、`cs.CL`；
- `comment`：arXiv comment；
- `doi`：DOI；
- `submission_history`：arXiv 版本历史。

对于非 arXiv 来源论文，该字段保持默认空值。

---

### 7.3 OpenReview 特有字段

```python
"openreview_obj": {
    "note_id": "",
    "forum_id": "",
    "number": "",
    "venue": "",
    "venueid": "",
    "paperhash": "",
    "pdf_url": "",
    "forum_url": "",
    "keywords": [],
    "tldr": "",
    "primary_area": "",
    "accept_type": ""
}
```

说明：

- `note_id`：OpenReview note ID；
- `forum_id`：OpenReview forum ID；
- `number`：OpenReview submission number；
- `venue`：OpenReview 记录中的 venue，例如 `ICLR 2026 Poster`；
- `venueid`：OpenReview venue ID；
- `paperhash`：OpenReview paperhash；
- `pdf_url`：OpenReview PDF 地址；
- `forum_url`：OpenReview 论文页面；
- `keywords`：作者在 OpenReview 中填写的关键词；
- `tldr`：OpenReview TLDR；
- `primary_area`：论文方向；
- `accept_type`：接收类型，例如 `Poster`、`Oral`、`Spotlight`。

对于非 OpenReview 来源论文，该字段保持默认空值。

---

### 7.4 AAAI Official 特有字段

```python
"aaai_obj": {
    "year": "",
    "conference_number": "",
    "volume": "",
    "issue": "",
    "issue_title": "",
    "track_type": "",
    "track_name": "",
    "article_id": "",
    "article_url": "",
    "official_pdf_url": "",
    "doi": "",
    "pages": "",
    "published": ""
}
```

说明：

- `year`：AAAI 会议年份；
- `conference_number`：会议届数，例如 `40` 表示 AAAI-40；
- `volume` / `issue`：论文集卷/期信息；
- `issue_title`：议题标题（如 "AAAI Technical Track on ..."）；
- `track_type`：track 类型（如 "Technical Track"、"Special Track"）；
- `track_name`：track 名称；
- `article_id`：OJS 文章 ID；
- `article_url`：AAAI proceedings 文章页面；
- `official_pdf_url`：AAAI 官方 PDF 地址；
- `doi`：DOI；
- `pages`：页码；
- `published`：发表日期。

对于非 AAAI 来源论文，该字段保持默认空值。

---

### 7.5 Official 会议官网字段

```python
"official_obj": {
    "venue": "",
    "year": "",
    "event_id": "",
    "event_type": "",
    "accept_type": "",
    "official_url": "",
    "official_pdf_url": "",
    "keywords": []
}
```

说明：

- `venue`：会议名称，例如 `ICML`；
- `year`：会议年份；
- `event_id`：官网 event ID；
- `event_type`：官网事件类型，例如 `poster`；
- `accept_type`：接收类型，例如 `Poster`；
- `official_url`：会议官网论文页面；
- `official_pdf_url`：会议官网 PDF；
- `keywords`：官网 meta keywords。

该字段当前主要用于 ICML Official 数据源，也可以扩展到其他会议官网。

---

### 7.6 ACL Anthology 特有字段

```python
"acl_anthology_obj": {
    "anthology_id": "",
    "volume_id": "",
    "venue": "",
    "year": None,
    "subtype": "",
    "paper_url": "",
    "pdf_url": "",
    "bib_url": "",
    "doi": "",
    "first_page": "",
    "last_page": "",
    "publication_date": ""
}
```

说明：

- `anthology_id`：ACL Anthology 论文 ID，例如 `2025.acl-long.1`；
- `volume_id`：ACL Anthology volume ID，例如 `2025.acl-long`；
- `venue`：会议或期刊名称（`ACL`、`EMNLP`、`NAACL`、`COLING` 等）；
- `year`：年份；
- `subtype`：论文类型，例如 `Long Paper`、`Short Paper`、`Findings`；
- `paper_url`：ACL Anthology 页面；
- `pdf_url`：PDF 地址；
- `bib_url`：BibTeX 地址；
- `doi`：DOI；
- `first_page` / `last_page`：页码；
- `publication_date`：发表时间。

对于非 ACL Anthology 来源论文，该字段保持默认空值。

---

### 7.7 来源追踪字段

```python
"seen_in_sources": []
"seen_in_categories": []
```

说明：

- `seen_in_sources`：记录论文在哪些来源中出现过；
- `seen_in_categories`：记录论文是从哪些分类、入口或 track 中被发现的。

示例：

```python
"seen_in_sources": ["arXiv", "ICLR 2026"]
"seen_in_categories": ["cs.AI", "cs.CL"]
```

如果一篇论文既在 arXiv 的 `cs.AI` 中出现过，也在 `cs.CL` 中出现过，则：

```python
"seen_in_categories": ["cs.AI", "cs.CL"]
```

如果一篇论文先出现在 arXiv，后续又被 ICLR 2026 接收，则：

```python
"seen_in_sources": ["arXiv", "ICLR 2026"]
```

---

### 7.8 接收 venue 字段

```python
"accepted_by": ""
```

示例：

```python
"accepted_by": "ICLR 2026"
"accepted_by": "ICML 2026"
"accepted_by": "ACL 2025"
"accepted_by": "arXiv 2026"
```

说明：

- `accepted_by` 用于记录论文被哪个会议、期刊或来源接收；
- 如果论文只是 arXiv 预印本，可以暂记为 `arXiv 2026`；
- 如果论文后来被正式会议或期刊接收，建议以正式会议或期刊为主；
- 更细粒度的接收类型应写入 `openreview_obj.accept_type`、`official_obj.accept_type` 或 `acl_anthology_obj.subtype`。

---

### 7.9 URL 字段

```python
"base_urls": {}
"more_urls": {}
```

`base_urls` 用于记录核心链接，例如：

```python
"base_urls": {
    "arxiv_url": "https://arxiv.org/abs/xxxx.xxxxx",
    "arxiv_pdf_url": "https://arxiv.org/pdf/xxxx.xxxxx.pdf",
    "openreview_url": "https://openreview.net/forum?id=xxxx",
    "openreview_pdf_url": "https://openreview.net/pdf?id=xxxx",
    "official_url": "https://icml.cc/virtual/2026/poster/xxxxx",
    "official_pdf_url": "",
    "aaai_url": "https://ojs.aaai.org/index.php/AAAI/article/view/xxxxx",
    "aaai_pdf_url": "https://ojs.aaai.org/index.php/AAAI/article/view/xxxxx/pdf",
    "acl_anthology_url": "https://aclanthology.org/2025.acl-long.1/",
    "acl_anthology_pdf_url": "https://aclanthology.org/2025.acl-long.1.pdf"
}
```

`more_urls` 用于记录附加链接，例如：

```python
"more_urls": {
    "code": "",
    "project": "",
    "video": "",
    "slides": "",
    "demo": "",
    "dataset": ""
}
```

---

### 7.10 引文与参考文献字段

```python
"cite_numbers": []
"references": []
```

说明：

- `cite_numbers`：用于记录 Google Scholar、Semantic Scholar 等来源的引用量；
- `references`：用于记录从论文 PDF 或正文中抽取出的参考文献列表。

示例：

```python
"cite_numbers": [
    {
        "count": 123,
        "source": "Semantic Scholar",
        "time": "2026-06-01T10:00:00+08:00"
    }
]
```

当前这两个字段主要是预留字段，后续会在 PDF 解析和外部引用源接入后逐步填充。

---

### 7.11 论文内容分析字段

```python
"tags": []
"toc_tree": []
"keywords": []
"summary_short": ""
"summary_long": ""
"txt_contributions": ""
"txt_scientific_question": ""
```

说明：

- `tags`：论文主题标签；
- `toc_tree`：论文目录结构；
- `keywords`：正文关键词；
- `summary_short`：短总结；
- `summary_long`：长总结；
- `txt_contributions`：论文贡献总结；
- `txt_scientific_question`：论文主要研究的关键科学问题。

这些字段当前主要是为后续 PDF 解析、NLP 抽取和 LLM 抽取预留。

---

### 7.12 论文实验四要素字段

```python
"pipeline": ""
"baselines": []
"benchmarks": []
"metrics": []
```

说明：

- `pipeline`：论文的方法流程或实验流程；
- `baselines`：论文对比方法；
- `benchmarks`：论文评测数据集、任务或 benchmark；
- `metrics`：论文评价指标。

这是后续科研分析中最关键的一组字段。未来可以支持：

```text
查询某个 benchmark 被哪些论文使用
查询某个 baseline 被哪些论文对比
查询某个 metric 在哪些任务中出现
查询某类方法的发展脉络
```

---

### 7.13 处理状态与本地文件路径

处理状态字段：

```python
"processing_status": {
    "toc_extracted": False,
    "references_extracted": False,
    "pdf_downloaded": False,
    "txt_extracted": False,
    "json_extracted": False
}
```

本地路径字段：

```python
"local_txt_path": ""
"local_pdf_path": ""
"local_json_path": ""
```

说明：

- `pdf_downloaded`：PDF 是否已经成功下载；
- `txt_extracted`：文本是否已经成功抽取；
- `json_extracted`：结构化 JSON 是否已经成功抽取；
- `toc_extracted`：目录是否已经抽取；
- `references_extracted`：参考文献是否已经抽取；
- `local_pdf_path`：本地 PDF 路径；
- `local_txt_path`：本地 TXT 路径；
- `local_json_path`：本地 JSON 路径。

设计原则：

```text
大文本、PDF、JSON 文件不直接存入 MongoDB；
MongoDB 中只保存文件路径和处理状态。
```

---

### 7.14 编辑日志字段

```python
"edit_logs": []
```

示例：
```python
{
    "time": "2026-06-01T10:00:00+08:00",
    "op": "insert from arXiv @ cs.AI",
    "detail": "insert paper metadata"
}
```

说明：

- `edit_logs` 用于记录论文记录的插入、更新、字段补全等操作；
- 该字段有助于追踪数据来源和更新历史；
- 后续排查重复爬取、字段覆盖和多源融合问题时，该字段非常重要。

---

### 7.15 当前 PDF 与文档资产状态

旧字段 `processing_status` 和 `local_pdf_path` 为兼容历史数据保留。当前 PDF 与 OCR 主流程以 `pdf_asset` 和 `document_asset` 为准。

一篇论文记录除元数据外，主要通过两个嵌套对象跟踪全文资产。

#### `pdf_asset`

记录 PDF 下载状态、来源 URL、最终 URL、相对路径、文件大小、SHA256、HTTP 状态、尝试次数、错误、重试时间、Worker 和租约。

常见状态：

```text
pending | running | success | failed | unavailable
```

#### `document_asset`

记录文档解析状态、解析器名称与版本、来源 PDF 路径和 SHA256、Markdown/报告路径、页数、字符数、耗时、质量状态、错误、尝试次数、Worker 和租约。

常见状态：

```text
blocked | pending | running | success | failed
```

其中：

- PDF 不可用时，文档任务为 `blocked`；
- PDF 成功后，文档任务可刷新为 `pending`；
- 解析成功后为 `success`；
- 重复执行会跳过已成功任务。

所有任务更新都校验 Worker 所有权，避免租约过期后旧 Worker 覆盖新结果。

---

## 8. 去重与多源融合策略

当前论文唯一 ID 使用标题规范化后的 SHA1 hash 生成。

相关工具位于：

```text
data_pipeline/utils/text_utils.py
```

基本流程：

```text
原始标题
    ↓
normalize_title(title)
    ↓
sha1(normalized_title)
    ↓
作为 MongoDB _id
```

数据库写入逻辑位于：

```text
data_pipeline/db_ops/paper_repository.py
```

upsert 基本策略：

1. 如果数据库中不存在该论文，则插入新记录；
2. 如果数据库中已经存在该论文，则补充缺失字段；
3. 不轻易覆盖已有非空字段；
4. 自动追加 `seen_in_sources`；
5. 自动追加 `seen_in_categories`；
6. 写入 `edit_logs`。

需要注意，标题归一化去重并不能解决所有问题。例如：

- 同一篇论文在不同来源中标题有轻微差异；
- 标题中标点、大小写、LaTeX 符号不同；
- 会议版本和 arXiv 版本标题不完全一致；
- 同名论文或极短标题可能导致误合并。

后续可以继续增强去重策略，例如结合：

- arXiv ID；
- DOI；
- OpenReview note ID；
- ACL Anthology ID；
- 作者列表；
- 发表年份；
- 标题相似度；
- PDF 指纹。

---

---

## 9. 当前支持的数据源

### 9.1 arXiv

arXiv 数据源用于日常增量采集 AI 相关预印本论文。

相关文件：

```text
data_pipeline/source_configs/arxiv_spec_config.py
data_pipeline/crawlers/arxiv_crawler.py
data_pipeline/pipelines/arxiv_daily.py
data_pipeline/scripts_py/crawl_arxiv_daily.py
scripts_md/3_crawl_arxiv_daily.md
```

当前支持：

- 按日期范围爬取；
- 按 arXiv category 爬取；
- 不指定日期时默认爬取当天；
- 支持命令行指定单个或多个 category；
- 支持 `--max-results` 调试参数；
- 解析标题、作者、摘要、arXiv ID、PDF URL、分类、comment、DOI、版本历史等字段；
- 一篇论文解析完成后立即写入 MongoDB；
- 重复爬取时避免重复插入；
- 同一篇论文从多个 category 出现时补充 `seen_in_categories`。

默认 category 配置位于：

```text
data_pipeline/source_configs/arxiv_spec_config.py
```

示例：

```python
CATEGORIES = [
    "cs.AI",
    "cs.CL",
]
```

运行示例：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01
```

指定 category：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01 \
  --categories cs.AI cs.CL
```

调试模式限制数量：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01 \
  --categories cs.AI cs.CL \
  --max-results 5
```

---

### 9.2 OpenReview

OpenReview 数据源用于采集托管在 OpenReview 上的会议论文，目前已覆盖 **ICLR**（2022–2026）、**NeurIPS**（2022–2025）和 **ICML**（2022–2025 via OpenReview）。

相关文件：

```text
data_pipeline/source_configs/openreview_gen_config.py
data_pipeline/crawlers/openreview_crawler.py
data_pipeline/pipelines/openreview_pipeline.py
data_pipeline/scripts_py/crawl_openreview.py
scripts_md/4_crawl_openreview_by_Conf_Year.md
scripts_md/7_crawl_NeurIPS_by_OpenReview.md
```

当前支持：

- 按 venue/year 爬取 OpenReview 论文；
- 读取标题、作者、摘要、关键词、TLDR、primary area 等字段；
- 读取 OpenReview note、forum、venue、venueid、paperhash 等字段；
- 解析 PDF 链接和 forum 链接；
- 解析接收类型，例如 `Poster`、`Oral`、`Spotlight`；
- 支持 `--max-results` 调试参数；
- 一篇论文爬取完成后立即写入 MongoDB；
- 支持重复爬取去重和字段补全。

运行示例（ICLR）：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR \
  --year 2026 \
  --max-results 3
```

正式爬取时可以不传 `--max-results`：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR \
  --year 2026
```

NeurIPS、ICML 也可以通过相同方式采集，具体可参考：

```text
scripts_md/7_crawl_NeurIPS_by_OpenReview.md
```

---

### 9.3 PMLR

PMLR 数据源用于采集 Proceedings of Machine Learning Research 中的论文元数据。

相关文件：

```text
data_pipeline/source_configs/pmlr_gen_config.py
data_pipeline/crawlers/pmlr_crawler.py
data_pipeline/pipelines/pmlr_pipeline.py
data_pipeline/scripts_py/crawl_pmlr.py
scripts_md/5_crawl_pmlr_by_Conf_Year.md
```

当前支持：

- 按会议和年份组织 PMLR 论文采集；
- 从 PMLR 页面解析论文元数据；
- 写入统一论文 Schema；
- 通过 upsert 逻辑入库；
- 支持与其他来源的后续融合。

运行方式请优先查看脚本帮助：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_pmlr --help
```

对应操作文档：

```text
scripts_md/5_crawl_pmlr_by_Conf_Year.md
```

---

### 9.4 ICML Official

ICML Official 数据源用于从 ICML 官方会议页面采集论文信息。

相关文件：

```text
data_pipeline/source_configs/conference_gen_config.py
data_pipeline/crawlers/icml_official_crawler.py
data_pipeline/pipelines/icml_official_pipeline.py
data_pipeline/scripts_py/crawl_icml_official.py
scripts_md/6_crawl_ICML_by_Official.md
```

当前支持：

- 从 ICML 官方页面采集论文；
- 解析 event ID；
- 解析 event type；
- 解析 official URL；
- 解析 accept type；
- 记录官网 meta keywords；
- 写入 `official_obj`；
- 支持重复爬取去重和字段补全。

运行方式请优先查看脚本帮助：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_icml_official --help
```

对应操作文档：

```text
scripts_md/6_crawl_ICML_by_Official.md
```

---

### 9.5 AAAI Official

AAAI Official 数据源用于从 AAAI 官方 Proceedings（基于 OJS 平台）采集 AAAI 主会论文信息，当前覆盖 AAAI 2022–2026。

相关文件：

```text
data_pipeline/source_configs/aaai_config.py
data_pipeline/crawlers/aaai_official_crawler.py
data_pipeline/pipelines/aaai_official_pipeline.py
data_pipeline/scripts_py/crawl_aaai_official.py
scripts_md/9_crawl_AAAI_by_Official.md
```

当前支持：

- 从 AAAI OJS proceedings 页面采集论文；
- 自动遍历年度页面 → issue 列表 → section 文章列表；
- 按 `INCLUDE_ISSUE_KEYWORDS` 过滤，只采集 Technical Tracks 和 Special Tracks；
- 自动排除 IAAI、EAAI、Student Abstracts、Doctoral Consortium 等非研究论文类别；
- 解析 article ID、track type、track name、DOI、页码、发表日期等字段；
- 解析 official PDF 链接；
- 写入 `aaai_obj`；
- 支持 `--year` 和 `--max-results` 参数；
- 支持重复爬取去重和字段补全。

运行示例（小规模测试）：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_aaai_official \
  --year 2026 \
  --max-results 3
```

正式全量爬取：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_aaai_official \
  --year 2026
```

对应操作文档：

```text
scripts_md/9_crawl_AAAI_by_Official.md
```

---

### 9.6 ACL Anthology（含 ACL / EMNLP / NAACL / COLING）

ACL Anthology 数据源用于采集 ACL 体系论文，目前已覆盖 **ACL**、**EMNLP**、**NAACL**、**COLING** 等多个会议，支持按 venue、year、subtype 灵活爬取。

相关文件：

```text
data_pipeline/source_configs/acl_anthology_config.py
data_pipeline/crawlers/acl_anthology_crawler.py
data_pipeline/pipelines/acl_anthology_pipeline.py
data_pipeline/scripts_py/crawl_acl_anthology.py
scripts_md/8_crawl_ACL_by_OfficialAnthology.md
scripts_md/10_crawl_EMNLP_by_OfficialAnthology.md
scripts_md/11_crawl_NAACL_by_OfficialAnthology.md
scripts_md/12_crawl_COLING_by_OfficialAnthology.md
```

当前支持：

- 从 ACL Anthology 采集论文元数据；
- 解析 anthology ID、volume ID；
- 解析 venue、year、subtype（`long` / `short` / `main` / `findings` 等）；
- 解析 paper URL、PDF URL、BibTeX URL；
- 解析 DOI、页码、发表日期等字段；
- 支持 `--delay-seconds` 控制请求间隔；
- 支持 `--max-results` 调试参数；
- 写入 `acl_anthology_obj`；
- 支持重复爬取去重和字段补全。

运行示例（ACL 2025 Long）：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue ACL \
  --year 2025 \
  --subtype long \
  --delay-seconds 0.5
```

运行示例（EMNLP 2025 main + findings）：

```bash
# EMNLP 2025 main
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue EMNLP \
  --year 2025 \
  --subtype main \
  --delay-seconds 0.5

# EMNLP 2025 findings
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue EMNLP \
  --year 2025 \
  --subtype findings \
  --delay-seconds 0.5
```

NAACL、COLING 同理，只需修改 `--venue`、`--year`、`--subtype` 参数，详见对应操作文档。

---

### 9.7 数据源覆盖总览

详细的数据源覆盖清单（含各会议各年份的爬取状态）请参考：

```text
scripts_md/All Sources Details.md
```

当前已覆盖的主要会议/来源一览：

| 来源 | 覆盖年份 | 采集方式 |
|---|---|---|
| arXiv | 日常增量 | arXiv API |
| ICLR | 2022–2026 | OpenReview |
| NeurIPS | 2022–2025 | OpenReview |
| ICML | 2022–2025 | OpenReview + PMLR + Official |
| AAAI | 2022–2026 | AAAI Official (OJS) |
| ACL | 2022–2025 | ACL Anthology |
| EMNLP | 2022–2025 | ACL Anthology |
| NAACL | 2022, 2024–2025 | ACL Anthology |
| COLING | 2022, 2024–2025 | ACL Anthology |

---

---

## 10. 数据库查询与字段检查

### 10.1 查询论文

查询工具入口：

```text
data_pipeline/scripts_py/query_paper.py
```

底层实现：

```text
data_pipeline/db_ops/paper_query.py
```

当前支持：

- 按标题模糊查询；
- 简要显示；
- 显示摘要；
- 按字段精确查询；
- 按字段非空查询；
- 多个非空字段 AND 查询。

按标题模糊查询：

```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --title "chain of thought" \
  --brief
```

显示摘要：

```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --title "chain of thought" \
  --show-abstract
```

查询摘要非空论文：

```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --non-empty abstract \
  --brief
```

查询 arXiv ID 非空论文：

```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --non-empty arxiv_obj.arxiv_id \
  --brief
```

多个字段同时非空：

```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --non-empty abstract \
  --non-empty arxiv_obj.arxiv_id \
  --brief
```

按字段精确查询：

```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --field accepted_by \
  --value "ICLR 2026" \
  --brief
```

查询 ACL Anthology 字段：

```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --field acl_anthology_obj.venue \
  --value "ACL" \
  --brief
```

查询 AAAI 字段：

```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --field aaai_obj.year \
  --value "2026" \
  --brief
```

---

### 10.2 检查字段

字段检查入口：

```text
data_pipeline/scripts_py/check_fields.py
```

底层实现：

```text
data_pipeline/db_ops/field_checker.py
```

该工具用于检查数据库中某些字段的覆盖情况，例如字段是否存在、是否为空、哪些记录缺少关键字段等。

运行方式请优先查看脚本帮助：

```bash
python -m ai4research.data_pipeline.scripts_py.check_fields --help
```

对应操作文档：

```text
scripts_md/0_db_operations.md
```

---

---

## 11. Schema 迁移

当 `paper_schema.py` 中的 `DEFAULT_PAPER_FIELDS` 增加新字段后，旧记录可能缺少这些字段。

此时可以执行 Schema 迁移：

```bash
python -m ai4research.data_pipeline.scripts_py.migrate_schema
```

相关文件：

```text
data_pipeline/scripts_py/migrate_schema.py
data_pipeline/schemas/paper_schema.py
scripts_md/2_migrate_schema.md
```

迁移逻辑一般包括：

1. 遍历 MongoDB 中已有论文记录；
2. 检查每条记录是否缺少 `DEFAULT_PAPER_FIELDS` 中定义的字段；
3. 对缺失字段写入默认值；
4. 保留已有字段内容；
5. 更新 schema version。

迁移原则：

```text
只补齐缺失字段，不随意覆盖已有非空字段。
```

---

---

## 12. 已验证的典型流程

### 12.1 初始化数据库

```bash
python -m ai4research.data_pipeline.scripts_py.init_db
```

预期效果：

```text
✅ MongoDB connected successfully.
✅ MongoDB indexes initialized successfully.
```

---

### 12.2 迁移 Schema

```bash
python -m ai4research.data_pipeline.scripts_py.migrate_schema
```

预期效果：

```text
✅ MongoDB connected successfully.
Schema migration finished.
```

---

### 12.3 爬取 arXiv 某一天论文

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01 \
  --categories cs.AI
```

示例验证结果：

```text
Crawling papers: 242paper [00:16, 15.01paper/s]
🎉 2026-06-01 ~ 2026-06-01 crawl finished. Total papers processed: 242
```

---

### 12.4 爬取 OpenReview 会议论文

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR \
  --year 2026
```

示例已验证能力包括：

```text
ICLR / NeurIPS / ICML accepted papers filtering
Poster / Oral / Spotlight accept type parsing
OpenReview forum URL / PDF URL extraction
```

---

### 12.5 爬取 ICML Official

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_icml_official --help
```

对应文档：

```text
scripts_md/6_crawl_ICML_by_Official.md
```

---

### 12.6 爬取 AAAI Official

```bash
# 小规模测试
python -m ai4research.data_pipeline.scripts_py.crawl_aaai_official \
  --year 2026 \
  --max-results 3

# 全量爬取
python -m ai4research.data_pipeline.scripts_py.crawl_aaai_official \
  --year 2026
```

对应文档：

```text
scripts_md/9_crawl_AAAI_by_Official.md
```

---

### 12.7 爬取 ACL Anthology（ACL / EMNLP / NAACL / COLING）

```bash
# ACL 2025 Long
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue ACL --year 2025 --subtype long --delay-seconds 0.5

# EMNLP 2025 main
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue EMNLP --year 2025 --subtype main --delay-seconds 0.5

# NAACL 2025 long
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue NAACL --year 2025 --subtype long --delay-seconds 0.5

# COLING 2025 main
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue COLING --year 2025 --subtype main --delay-seconds 0.5
```

对应文档：

```text
scripts_md/8_crawl_ACL_by_OfficialAnthology.md
scripts_md/10_crawl_EMNLP_by_OfficialAnthology.md
scripts_md/11_crawl_NAACL_by_OfficialAnthology.md
scripts_md/12_crawl_COLING_by_OfficialAnthology.md
```

---

### 12.8 查询数据库记录

```bash
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --non-empty abstract \
  --brief
```

预期效果：

```text
返回摘要非空的论文简要信息。
```

---

### 12.9 Research Topic 到 Markdown

所有 `python -m ai4research...` 命令应在包目录的父目录执行。服务器目录为 `~/ai4research` 时，先进入 `~`：

#### 1. 只预览候选

预览不会下载 PDF、不会执行 OCR，也不会修改数据库：

```bash
cd ~

python -m ai4research.research_pipeline.scripts_py.process_research_topic \
  --topic "agent memory" \
  --top-k 3 \
  --preview
```

#### 2. 执行完整工作流

```bash
cd ~

python -m ai4research.research_pipeline.scripts_py.process_research_topic \
  --topic "agent memory" \
  --top-k 3
```

工作流自动完成：

```text
Topic 词法召回
→ 检查高相关候选是否具备 PDF 处理条件
→ 无 PDF 候选自动向后补位
→ 已下载 PDF 直接复用，否则下载
→ 自动刷新文档任务可用性
→ 已解析文档直接复用，否则 OCR
→ 质量检查
→ 输出 READY_MARKDOWN_PATHS
```

输出示例：

```text
READY_MARKDOWN_PATHS
====================================================================================================
/data/ai4research_assets/documents/ac/7d/<paper_id>/document.md
/data/ai4research_assets/documents/9e/75/<paper_id>/document.md
/data/ai4research_assets/documents/19/34/<paper_id>/document.md
```

#### 3. 保存结构化执行结果

```bash
python -m ai4research.research_pipeline.scripts_py.process_research_topic \
  --topic "agent memory" \
  --top-k 3 \
  --save-json ~/agent_memory_result.json
```

JSON 包含候选、分数、命中字段、各阶段统计、最终状态、错误和 Markdown 路径。

#### 数量参数

| 参数 | 默认值 | 含义 |
|---|---:|---|
| `--top-k` | 3 | 目标处理并返回的论文数 |
| `--candidate-scan-limit` | 30 | 为跳过无 PDF 候选而检查的高相关候选数 |
| `--candidate-pool-size` | 1000 | 从 MongoDB 初步读取并参与评分的候选池上限 |

通常应满足：

```text
candidate_pool_size >= candidate_scan_limit >= top_k
```

如果数据库中可处理论文不足，或者下载、OCR、质检实际失败，最终路径数量仍可能少于 `top-k`。

### 12.10 Topic 召回策略

当前实现是可解释的 MongoDB 词法召回：

```text
name:     mongo-lexical-topic-retriever
version:  2
```

评分考虑：

- 完整 Topic 是否出现在标题或摘要；
- 查询词是否出现在标题、摘要、关键词或标签；
- 查询词覆盖率。

分数是同一次查询内部使用的原始排序分，不是百分制，也不应跨不同 Topic 直接比较。

同分时依次按以下规则稳定排序：

1. 分数降序；
2. 标题字母顺序；
3. paper ID。

PDF 是否下载、OCR 是否完成不参与相关性评分。处理状态只用于上层编排判断能否复用或需要补齐资产，因此相同数据库内容下的检索排序可复现。

`TopicRetriever` 是独立接口。后续可以增加 BM25、向量召回或混合检索，而不改动 PDF 和 OCR 模块。

### 12.11 PDF、OCR 与质量检查独立入口

#### PDF 下载

处理指定论文：

```bash
cd ~

python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --paper-id <paper_id>
```

PDF 管线支持：

- 多来源候选 URL 优先级；
- 域名级限速；
- PDF 内容校验；
- 临时文件与原子提交；
- 任务领取、租约和 Worker 所有权；
- 失败重试与限流任务恢复；
- 串行或并发下载；
- 已成功资产自动跳过。

完整操作参见 `scripts_md/13_download_and_manage_PDFs.md`。

#### 文档可用性刷新

单独运行 PDF 和 OCR 命令时，需要把 PDF 状态同步到文档任务：

```bash
python -m ai4research.document_pipeline.scripts_py.refresh_document_availability \
  --paper-id <paper_id> \
  --execute
```

使用 `process_research_topic` 时，这一步由上层编排自动完成。

#### OCR 解析

```bash
python -m ai4research.document_pipeline.scripts_py.parse_documents \
  --paper-id <paper_id>
```

批量入口还支持 `--accepted-by`、`--all` 和 `--limit`。当前文档 Runner 按论文顺序处理，单篇论文内部使用页面级并发。

解析成功后写入：

- `document.md`：按页拼接的标准 Markdown；
- `parse_report.json`：逐页结果、耗时、错误和解析器版本；
- MongoDB `document_asset`：路径、页数、字符数、状态、来源 PDF SHA256 等。

#### 文档质量检查

```bash
python -m ai4research.document_pipeline.scripts_py.check_document_quality \
  --paper-id <paper_id>
```

当前基础检查包括：

- Markdown 文件存在且非空；
- 页数有效；
- Markdown 页标记与报告页数一致；
- 字符数与数据库记录基本一致；
- 平均每页字符数合理；
- 标题匹配；
- 解析报告完整。

质量状态：

```text
unchecked | passed | warning | rejected
```

完整操作参见 `scripts_md/14_parse_and_quality_check_documents.md`。

### 12.12 自动化测试

在仓库目录运行：

```bash
cd ~/ai4research
python -m pytest -q
```

当前测试覆盖：

- OCR 文档解析成功、页面顺序和部分页面失败；
- 基础文档质量检查；
- Topic 候选跳过无 PDF 记录并自动补位；
- 候选扫描数量不低于 `top-k`。

当前基线：

```text
7 passed
```

---

## 13. 操作文档

`scripts_md/` 保存按阶段执行和排障的详细说明：

| 文档 | 内容 |
|---|---|
| `0_db_operations.md` | MongoDB 常用操作 |
| `1_init_database.md` | 初始化数据库与索引 |
| `2_migrate_schema.md` | Schema 迁移 |
| `3_crawl_arxiv_daily.md` | arXiv 增量采集 |
| `4_crawl_openreview_by_Conf_Year.md` | OpenReview 会议采集 |
| `5_crawl_pmlr_by_Conf_Year.md` | PMLR 采集 |
| `6_crawl_ICML_by_Official.md` | ICML 官方来源采集 |
| `7_crawl_NeurIPS_by_OpenReview.md` | NeurIPS 采集 |
| `8_crawl_ACL_by_OfficialAnthology.md` | ACL 采集 |
| `9_crawl_AAAI_by_Official.md` | AAAI 官方来源采集 |
| `10_crawl_EMNLP_by_OfficialAnthology.md` | EMNLP 采集 |
| `11_crawl_NAACL_by_OfficialAnthology.md` | NAACL 采集 |
| `12_crawl_COLING_by_OfficialAnthology.md` | COLING 采集 |
| `13_download_and_manage_PDFs.md` | PDF 下载与资产管理 |
| `14_parse_and_quality_check_documents.md` | OCR 解析与质量检查 |
| `15_process_research_topic.md` | Topic 到 Markdown 上层工作流 |
| `All Sources Details.md` | 数据源字段与覆盖说明 |

---

## 14. 新增数据源开发规范

新增一个数据源时，建议遵循以下结构。

以新增 `xxx` 数据源为例：

```text
data_pipeline/source_configs/xxx_config.py
data_pipeline/crawlers/xxx_crawler.py
data_pipeline/pipelines/xxx_pipeline.py
data_pipeline/scripts_py/crawl_xxx.py
scripts_md/n_crawl_XXX.md
```

推荐开发流程：

```text
1. 调研数据源页面或 API；
2. 写最小 crawler，只抓 1 年、1 页或少量样例；
3. 打印检查原始字段；
4. 转换为 DEFAULT_PAPER_FIELDS 兼容结构；
5. 如果数据源有特有字段，在 paper_schema.py 中新增对应的 *_obj 字段；
6. 写 pipeline；
7. 写命令行 script；
8. 小规模测试；
9. 完整爬取；
10. 用 query_paper.py 和 check_fields.py 检查入库质量；
11. 更新 All Sources Details.md 覆盖清单；
12. 写 scripts_md 操作文档；
13. git commit 固化当前阶段。
```

---

---

## 15. 字段填写建议

### 15.1 `accepted_by`

推荐格式：

```text
arXiv 2026
ICLR 2026
NeurIPS 2025
ICML 2026
AAAI 2026
ACL 2025
EMNLP 2025
NAACL 2025
COLING 2025
```

如果论文同时存在 arXiv 和正式会议版本，建议以正式会议或期刊为主。

---

### 15.2 `seen_in_sources`

推荐格式：

```python
["arXiv"]
["OpenReview"]
["PMLR"]
["ICML 2026"]
["AAAI 2026"]
["ACL Anthology"]
["arXiv", "ICLR 2026"]
["OpenReview", "AAAI 2026"]
```

---

### 15.3 `seen_in_categories`

推荐格式：

```python
["cs.AI"]
["cs.CL"]
["cs.AI", "cs.CL"]
["ICLR 2026 Poster"]
["ICLR 2026 Oral"]
["AAAI Technical Track"]
["ACL Long Paper"]
["EMNLP Findings"]
```

---

### 15.4 `base_urls`

推荐只放核心 URL：

```python
{
    "arxiv_url": "",
    "arxiv_pdf_url": "",
    "openreview_url": "",
    "openreview_pdf_url": "",
    "official_url": "",
    "official_pdf_url": "",
    "aaai_url": "",
    "aaai_pdf_url": "",
    "acl_anthology_url": "",
    "acl_anthology_pdf_url": ""
}
```

---

### 15.5 `more_urls`

推荐放扩展 URL：

```python
{
    "code": "",
    "project": "",
    "video": "",
    "slides": "",
    "demo": "",
    "dataset": ""
}
```

---

---

## 16. 当前边界与注意事项

当前已经得到可供下游处理的论文 Markdown，但尚未完成：

- Markdown 结构清洗和章节识别；
- chunk 切分与 chunk Schema；
- embedding 生成与向量数据库；
- BM25 / 向量混合召回；
- 基于全文的 rerank；
- 引用、表格、公式和实验要素的稳定结构化抽取；
- 多篇论文并行 OCR 与多 GPU 调度；
- 基于证据的论文对比、综述和最终回答生成。

当前 Topic 召回只使用 MongoDB 元数据字段，因此它是候选初筛，不是最终语义检索结果。

补充注意事项：

- `top-k` 是目标处理数量；可处理论文不足或任务失败时，路径数可能更少；
- `candidate-scan-limit` 用于无 PDF 候选补位，不等于 MongoDB 初始候选池；
- 当前 OCR 并发主要位于单篇论文页面级，多篇论文仍按 Runner 顺序处理；
- 分步执行 PDF 和 OCR 时需手动刷新文档可用性，Topic 编排会自动完成；
- Topic 分数不是百分制，仅用于同一次查询内部排序；
- 密钥和密码不得写入代码、README 或 Git。

---

## 17. Roadmap

建议按以下顺序继续：

1. 定义 `DocumentChunk` Schema 和稳定 chunk ID；
2. 实现 Markdown 章节感知切分；
3. 将 chunk 写入独立存储或 MongoDB 集合；
4. 抽象 `EmbeddingBackend`，先接入一个本地 embedding 模型；
5. 建立向量索引；
6. 将词法召回与全文向量召回组合为混合检索；
7. 对候选段落和论文做 rerank；
8. 为 Research Agent 输出带 paper ID、页码和原文证据的结果。

```text
阶段 1：多源元数据采集                 ✅ 基本完成
阶段 2：PDF 下载、OCR 与质量检查       ✅ MVP 完成
阶段 3：Topic 到 Markdown 编排         ✅ MVP 完成
阶段 4：chunk、embedding 与混合检索    ⏳ 下一阶段
阶段 5：科研事实抽取与证据组织          ⏳ 规划中
阶段 6：Research Agent 回答与分析       ⏳ 规划中
```

---

## 18. 项目亮点

1. 元数据、PDF 和 OCR 文档共享稳定 paper ID；
2. MongoDB 状态与文件资产可以互相核验；
3. 长任务支持租约、重试、幂等和 Worker 所有权保护；
4. OCR 资产记录来源 PDF SHA256、解析器版本和逐页报告；
5. Topic 工作流复用已有资产，并跳过无 PDF 条件的候选；
6. 相关性评分与处理状态解耦，排序可以稳定复现；
7. CLI、测试和分阶段操作文档覆盖已完成主链路；
8. 模块接口允许继续增加模型、GPU、Worker 和外部服务。

### 18.1 可扩展接口

当前 MVP 特意保留了以下替换点：

| 接口 | 当前实现 | 可扩展方向 |
|---|---|---|
| `TopicRetriever` | MongoDB 词法召回 | BM25、向量召回、混合召回、重排序 |
| `PageOCRBackend` | OpenAI-compatible GLM-OCR | 其他本地模型、云 API、负载均衡 |
| `DocumentParser` | OCR 文档解析器 | 原生文本解析、版面模型、多模态解析 |
| `DocumentQualityChecker` | 基础规则检查 | 版面质量、公式/表格完整性、模型判分 |
| PDF URL Resolver | 固定来源优先级 | 新出版平台、代理或镜像来源 |
| Repository / Runner | MongoDB 任务租约 | 多机 Worker、队列系统、分布式执行 |

新增实现应依赖这些接口，不要把具体模型、API 地址或任务并发策略写死在业务流程中。

---

## 19. 开发原则

- 先完成可验证的 MVP，再扩展并发和模型能力；
- 配置、接口、业务编排和存储职责分离；
- 数据库状态与文件资产必须能够相互核验；
- 所有长任务应支持幂等、租约、重试和断点恢复；
- 大文件放在资产目录，不提交到 Git；
- 不在代码和文档中写入密钥；
- 每个阶段完成后运行测试并更新操作文档；
- Schema、解析器、检索器和质量检查策略发生语义变化时升级版本号。

新增数据源、解析器、OCR 后端、检索器或质量规则时，应优先实现现有抽象接口；发生语义变化时升级稳定版本号。业务编排不应写死模型路径、API 地址或并发策略。

---

## 20. 常用命令速查

```bash
# 初始化 MongoDB 索引
cd ~
python -m ai4research.data_pipeline.scripts_py.init_db

# 下载指定论文 PDF
python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --paper-id <paper_id>

# 手动同步文档任务可用性
python -m ai4research.document_pipeline.scripts_py.refresh_document_availability \
  --paper-id <paper_id> \
  --execute

# OCR 指定论文
python -m ai4research.document_pipeline.scripts_py.parse_documents \
  --paper-id <paper_id>

# 检查指定论文文档质量
python -m ai4research.document_pipeline.scripts_py.check_document_quality \
  --paper-id <paper_id>

# 预览 Topic 候选
python -m ai4research.research_pipeline.scripts_py.process_research_topic \
  --topic "agent memory" \
  --top-k 3 \
  --preview

# 自动获得相关论文 Markdown
python -m ai4research.research_pipeline.scripts_py.process_research_topic \
  --topic "agent memory" \
  --top-k 3

# 运行测试
cd ~/ai4research
python -m pytest -q
```

---

当前项目已经从“多源论文元数据仓库”推进到“可按研究主题自动准备全文 Markdown 的 Research Agent 数据内核”。下一阶段的核心，是把这些文档转化为可引用、可检索、可排序的细粒度证据。

---

## 21. 当前项目状态总结

截至 2026-06-20，项目已经从“多源论文元数据仓库”推进到“可按研究主题自动准备全文 Markdown 的 Research Agent 数据内核”。

真实验证已经覆盖 Topic 召回、无 PDF 候选补位、PDF 复用或下载、GLM-OCR、逐页 Markdown、解析报告、质量检查、幂等重复运行和多路径输出。当前完整测试基线为 `7 passed`。

下一阶段主线：

```text
章节感知 chunk
→ 稳定 chunk ID 与页码证据
→ embedding
→ 向量索引
→ 词法 + 语义混合检索
→ rerank
→ 带论文与页码引用的 Agent 输出
```

至此，数据采集、全文准备和 Topic 初筛已经连成一条可运行、可恢复、可扩展的 MVP 主链路。
