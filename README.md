# agent4research-kernel

`agent4research-kernel` 是一个面向 AI Research Agent 的论文数据与检索内核。

本项目当前阶段的重点不是直接构建一个完整的自动科研 Agent，而是先构建一个稳定、可扩展、可追踪的论文数据底座：从 arXiv、OpenReview、PMLR、ICML 官方网站、AAAI 官方网站、ACL Anthology（含 ACL、EMNLP、NAACL、COLING 等）等来源采集论文元数据，转换为统一的论文 Schema，写入 MongoDB，并支持后续的去重、多源融合、字段检查、命令行查询、PDF 处理、正文解析和科研事实抽取。

需要注意：

```text
仓库 / 项目名：agent4research-kernel
Python 包路径：ai4research
```

因此，当前命令行运行方式仍然是：

```bash
python -m ai4research.data_pipeline.scripts_py.xxx
```

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

## 2. 当前已实现功能总览

当前版本已经从最初的 arXiv 单源爬取，扩展为多源论文数据采集与 MongoDB 管理内核。

| 模块 | 当前状态 | 说明 |
|---|---|---|
| MongoDB 数据库连接 | 已实现 | 支持 MongoDB 配置、连接和 collection 获取 |
| MongoDB 索引初始化 | 已实现 | 支持 papers 集合索引初始化 |
| 统一论文 Schema | 已实现 | 使用 `DEFAULT_PAPER_FIELDS` 定义统一论文字段 |
| Schema 版本管理 | 已实现 | 使用 `CURRENT_SCHEMA_VERSION` 标记 Schema 版本 |
| Schema 迁移 | 已实现 | 支持为旧记录补齐新增字段 |
| 论文 upsert | 已实现 | 支持插入、去重、字段补全、来源追踪和编辑日志 |
| 字段检查 | 已实现 | 支持检查字段是否为空、统计字段覆盖情况 |
| 数据库查询 | 已实现 | 支持标题模糊查询、字段精确查询、非空字段筛选 |
| arXiv 数据源 | 已实现 | 支持按日期范围和 category 爬取论文 |
| OpenReview 数据源 | 已实现 | 支持 ICLR、NeurIPS、ICML 等会议的 OpenReview 论文采集 |
| PMLR 数据源 | 已实现 | 支持采集 PMLR Proceedings 中的论文元数据 |
| ICML Official 数据源 | 已实现 | 支持从 ICML 官方页面采集论文信息 |
| AAAI Official 数据源 | 已实现 | 支持从 AAAI 官方 Proceedings (OJS) 采集论文信息 |
| ACL Anthology 数据源 | 已实现 | 支持 ACL、EMNLP、NAACL、COLING 等 ACL 体系论文采集 |
| 操作文档 | 持续更新 | `scripts_md/` 中已沉淀数据库、迁移和各数据源爬取文档 |

当前尚未完成或仍处于后续规划中的能力包括：

- PDF 自动下载；
- PDF 正文解析；
- OCR 或文本抽取；
- 参考文献结构化抽取；
- 表格、图、公式等内容抽取；
- baseline / benchmark / metric 自动抽取；
- 论文关系图谱；
- Web 可视化界面；
- 上层 Research Agent。

---

## 3. 当前项目结构

当前文件结构如下：

```text
.
├── data_pipeline
│   ├── crawlers
│   │   ├── aaai_official_crawler.py
│   │   ├── acl_anthology_crawler.py
│   │   ├── arxiv_crawler.py
│   │   ├── base.py
│   │   ├── icml_official_crawler.py
│   │   ├── __init__.py
│   │   ├── openreview_crawler.py
│   │   └── pmlr_crawler.py
│   ├── db_ops
│   │   ├── field_checker.py
│   │   ├── __init__.py
│   │   ├── paper_query.py
│   │   └── paper_repository.py
│   ├── db_settings
│   │   ├── init_indexes.py
│   │   ├── __init__.py
│   │   ├── mongo_client.py
│   │   └── mongo_config.py
│   ├── __init__.py
│   ├── pipelines
│   │   ├── aaai_official_pipeline.py
│   │   ├── acl_anthology_pipeline.py
│   │   ├── arxiv_daily.py
│   │   ├── icml_official_pipeline.py
│   │   ├── __init__.py
│   │   ├── openreview_pipeline.py
│   │   └── pmlr_pipeline.py
│   ├── schemas
│   │   ├── __init__.py
│   │   └── paper_schema.py
│   ├── scripts_py
│   │   ├── check_fields.py
│   │   ├── crawl_aaai_official.py
│   │   ├── crawl_acl_anthology.py
│   │   ├── crawl_arxiv_daily.py
│   │   ├── crawl_icml_official.py
│   │   ├── crawl_openreview.py
│   │   ├── crawl_pmlr.py
│   │   ├── init_db.py
│   │   ├── __init__.py
│   │   ├── migrate_schema.py
│   │   └── query_paper.py
│   ├── source_configs
│   │   ├── aaai_config.py
│   │   ├── acl_anthology_config.py
│   │   ├── arxiv_spec_config.py
│   │   ├── conference_gen_config.py
│   │   ├── __init__.py
│   │   ├── openreview_gen_config.py
│   │   └── pmlr_gen_config.py
│   └── utils
│       ├── __init__.py
│       ├── text_utils.py
│       └── time_utils.py
├── __init__.py
├── README.md
├── requirements.txt
└── scripts_md
    ├── 0_db_operations.md
    ├── 1_init_database.md
    ├── 2_migrate_schema.md
    ├── 3_crawl_arxiv_daily.md
    ├── 4_crawl_openreview_by_Conf_Year.md
    ├── 5_crawl_pmlr_by_Conf_Year.md
    ├── 6_crawl_ICML_by_Official.md
    ├── 7_crawl_NeurIPS_by_OpenReview.md
    ├── 8_crawl_ACL_by_OfficialAnthology.md
    ├── 9_crawl_AAAI_by_Official.md
    ├── 10_crawl_EMNLP_by_OfficialAnthology.md
    ├── 11_crawl_NAACL_by_OfficialAnthology.md
    ├── 12_crawl_COLING_by_OfficialAnthology.md
    └── All Sources Details.md
```

各目录职责如下：

| 目录 | 作用 |
|---|---|
| `data_pipeline/crawlers/` | 从具体数据源抓取论文原始信息 |
| `data_pipeline/pipelines/` | 组织爬取流程，并逐篇写入数据库 |
| `data_pipeline/scripts_py/` | 命令行入口脚本 |
| `data_pipeline/source_configs/` | 不同数据源的配置 |
| `data_pipeline/schemas/` | 统一论文 Schema |
| `data_pipeline/db_settings/` | MongoDB 连接、配置和索引 |
| `data_pipeline/db_ops/` | 数据库 upsert、查询、字段检查等操作 |
| `data_pipeline/utils/` | 文本归一化、时间工具等通用函数 |
| `scripts_md/` | 分步骤操作文档 |

---

## 4. 整体数据流

本项目采用统一的数据处理流程：

```text
source_configs/
    ↓
crawlers/
    ↓
pipelines/
    ↓
db_ops/paper_repository.py
    ↓
MongoDB
```

也就是：

```text
配置数据源
    ↓
爬取论文
    ↓
转换为统一 paper_data
    ↓
逐篇 upsert 到 MongoDB
    ↓
支持查询、检查、迁移和后续处理
```

整体原则是：

```text
爬取一篇论文
    -> 转换为统一 Schema
    -> 立即写入或更新 MongoDB
```

这种方式相比"全部爬完后一次性写入"更适合长期增量采集，也方便中途失败后恢复。

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

## 13. 操作文档

当前 `scripts_md/` 已经包含以下操作文档：

| 文档 | 内容 |
|---|---|
| `0_db_operations.md` | 数据库查询、字段检查等基础操作 |
| `1_init_database.md` | 初始化 MongoDB 与索引 |
| `2_migrate_schema.md` | Schema 迁移 |
| `3_crawl_arxiv_daily.md` | arXiv 日常增量爬取 |
| `4_crawl_openreview_by_Conf_Year.md` | 按会议和年份爬取 OpenReview（ICLR 等） |
| `5_crawl_pmlr_by_Conf_Year.md` | 按会议和年份爬取 PMLR |
| `6_crawl_ICML_by_Official.md` | 从 ICML 官方网站爬取论文 |
| `7_crawl_NeurIPS_by_OpenReview.md` | 通过 OpenReview 爬取 NeurIPS |
| `8_crawl_ACL_by_OfficialAnthology.md` | 从 ACL Anthology 爬取 ACL 论文 |
| `9_crawl_AAAI_by_Official.md` | 从 AAAI 官方 Proceedings 爬取论文 |
| `10_crawl_EMNLP_by_OfficialAnthology.md` | 从 ACL Anthology 爬取 EMNLP 论文 |
| `11_crawl_NAACL_by_OfficialAnthology.md` | 从 ACL Anthology 爬取 NAACL 论文 |
| `12_crawl_COLING_by_OfficialAnthology.md` | 从 ACL Anthology 爬取 COLING 论文 |
| `All Sources Details.md` | 所有数据源覆盖清单（含各会议各年份爬取状态） |

建议后续每新增一个数据源，都同步新增一个 `scripts_md/` 操作文档。

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

## 16. 当前边界与注意事项

当前项目仍处于数据底座建设阶段，需要注意：

1. 当前主要处理论文元数据，尚未全面处理 PDF 正文；
2. `tags`、`toc_tree`、`references`、`baselines`、`benchmarks`、`metrics` 等字段多为预留字段；
3. 当前去重主要依赖标题归一化，不能完全解决标题变体问题；
4. 同一论文多源融合仍需要继续增强；
5. 引文数量字段 `cite_numbers` 尚未形成稳定自动更新流程；
6. PDF 下载、文本抽取、OCR 和 JSON 结构化仍是后续任务；
7. 不同会议官网结构可能随年份变化，需要单独适配；
8. OpenReview 不同会议、不同年份的 invitation、venue 字段可能不同，需要分别处理；
9. AAAI 2022 使用旧版 WordPress 页面结构，与 2023–2026 的 OJS 平台不同；
10. PMLR、ICML Official、ACL Anthology 等数据源的字段覆盖情况需要通过 `check_fields.py` 持续检查；
11. 所有命令行脚本的最新参数应以 `--help` 输出和 `scripts_md/` 文档为准。

---

## 17. Roadmap

### 阶段 1：多源元数据采集 ✅（基本完成）

目标：

```text
稳定采集 AI 论文元数据，并统一入库。
```

已覆盖：

- arXiv 日常增量；
- OpenReview（ICLR / NeurIPS / ICML）；
- PMLR Proceedings；
- ICML Official；
- AAAI Official；
- ACL Anthology（ACL / EMNLP / NAACL / COLING）；

后续扩展：

- 其他 AI 会议（KDD、SIGIR、IJCAI、CVPR、ICCV 等）；
- 期刊论文（JMLR、TACL 等）。

---

### 阶段 2：PDF 下载与正文解析

目标：

```text
从论文元数据进入论文全文层。
```

重点：

- PDF 自动下载；
- PDF 本地路径管理；
- TXT 抽取；
- JSON 结构化抽取；
- 目录结构抽取；
- 参考文献抽取；
- 处理状态更新。

---

### 阶段 3：科研事实抽取

目标：

```text
从论文正文中抽取可查询的科研事实。
```

重点字段：

- `pipeline`
- `baselines`
- `benchmarks`
- `metrics`
- `txt_contributions`
- `txt_scientific_question`
- `summary_short`
- `summary_long`

最终希望支持：

```text
查询某个 benchmark 被哪些论文使用；
查询某个 baseline 被哪些论文对比；
查询某个 metric 在哪些任务中出现；
查询某类方法的发展脉络。
```

---

### 阶段 4：科研分析与图谱构建

目标：

```text
将论文数据库升级为科研知识库。
```

重点：

- paper-method 图谱；
- paper-benchmark 图谱；
- paper-baseline 图谱；
- paper-metric 图谱；
- paper-citation 图谱；
- topic trend 分析；
- venue trend 分析；
- related work 自动证据表。

---

### 阶段 5：Research Agent 支撑

目标：

```text
为上层 Research Agent 提供可信数据基础。
```

可能能力：

- 论文检索 Agent；
- 相关工作整理 Agent；
- benchmark 追踪 Agent；
- baseline 推荐 Agent；
- idea novelty 检查 Agent；
- 研究趋势分析 Agent；
- 论文阅读与问答 Agent。

---

## 18. 项目亮点

本项目的亮点不是单个爬虫，而是逐步形成了一个面向 AI 论文的结构化数据内核：

1. **多源采集**：支持 arXiv、OpenReview（ICLR/NeurIPS/ICML）、PMLR、ICML Official、AAAI Official、ACL Anthology（ACL/EMNLP/NAACL/COLING）等 AI 论文核心来源；
2. **统一建模**：使用统一 Schema 表示不同来源的论文记录；
3. **多源融合**：同一篇论文可以合并来自不同来源的信息；
4. **可追踪更新**：通过 `seen_in_sources`、`seen_in_categories`、`edit_logs` 记录数据来源与更新历史；
5. **字段检查与查询**：支持对入库数据进行基础查询和质量检查；
6. **面向后续抽取**：预留了摘要实体、目录、参考文献、baseline、benchmark、metric 等字段；
7. **可扩展工程结构**：新增数据源时可以沿用 config-crawler-pipeline-script-doc 的开发模式；
8. **适合 Research Agent**：可以作为后续科研智能体的数据基础设施。

一句话概括：

```text
别人多数是在做"找论文、读论文、写综述"；
本项目要做的是"把 AI 论文变成可查询、可分析、可推理的结构化科研知识库"。
```

---

## 19. 开发原则

本项目后续开发会逐步遵循以下原则：

1. 一步一步推进，每次只完成一个明确的小目标；
2. 先小规模验证，再全量爬取；
3. 先保证入库正确，再追求覆盖规模；
4. 字段命名优先稳定，不轻易频繁变动；
5. 新增字段后及时更新 Schema 迁移脚本；
6. 新增数据源后补充 `scripts_md/` 操作文档；
7. 所有来源字段尽量保留原始证据 URL；
8. 不把大文本直接塞进 MongoDB，只存路径和状态；
9. 对已入库数据尽量采用补全策略，避免误覆盖；
10. 重要操作先 commit，再继续下一阶段开发。

---

## 20. 常用命令速查

初始化数据库：

```bash
python -m ai4research.data_pipeline.scripts_py.init_db
```

迁移 Schema：

```bash
python -m ai4research.data_pipeline.scripts_py.migrate_schema
```

爬取 arXiv：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01

# 指定 category
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01 \
  --categories cs.AI cs.CL
```

爬取 OpenReview：

```bash
# ICLR
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR --year 2026

# NeurIPS
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue NeurIPS --year 2025
```

爬取 AAAI Official：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_aaai_official --year 2026
```

爬取 ACL Anthology：

```bash
# ACL
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue ACL --year 2025 --subtype long --delay-seconds 0.5

# EMNLP
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue EMNLP --year 2025 --subtype main --delay-seconds 0.5

# NAACL
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue NAACL --year 2025 --subtype long --delay-seconds 0.5

# COLING
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology \
  --venue COLING --year 2025 --subtype main --delay-seconds 0.5
```

查看其他爬虫参数：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_pmlr --help
python -m ai4research.data_pipeline.scripts_py.crawl_icml_official --help
python -m ai4research.data_pipeline.scripts_py.crawl_acl_anthology --help
```

查询论文：

```bash
# 模糊查询
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --title "your paper title" --brief

# 非空字段查询
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --non-empty abstract --brief

# 精确字段查询
python -m ai4research.data_pipeline.scripts_py.query_paper \
  --field accepted_by --value "ICLR 2026" --brief
```

检查字段：

```bash
python -m ai4research.data_pipeline.scripts_py.check_fields --help
```

---

## 21. 当前项目状态总结

当前项目已经完成了从"单一 arXiv 爬虫"到"多源论文数据底座"的全面升级。

目前主干能力包括：

```text
MongoDB 数据库
统一论文 Schema（含 arXiv / OpenReview / AAAI / Official / ACL Anthology 子结构）
索引初始化
Schema 迁移
upsert 多源融合
字段检查
命令行查询
arXiv 增量爬取
OpenReview 会议论文采集（ICLR / NeurIPS / ICML）
PMLR Proceedings 论文采集
ICML Official 论文采集
AAAI Official 论文采集（2022–2026）
ACL Anthology 论文采集（ACL / EMNLP / NAACL / COLING，各 2–4 年）
操作文档沉淀（13 篇 + 覆盖清单）
```

下一阶段最值得推进的是：

```text
PDF 下载
正文解析
参考文献抽取
baseline / benchmark / metric 抽取
科研事实查询
论文关系图谱
Research Agent 支撑
```