# Agent4Research Kernel

**Agent4Research Kernel** 是面向 Research Agent 的论文数据与检索内核。当前阶段主要实现论文数据采集、论文画像构建、结构化入库与基础去重更新能力；未来将逐步扩展到顶会/期刊论文采集、PDF 解析、论文结构化信息抽取、相关论文检索、idea matching、baseline 推荐和 benchmark 推荐等功能。

本项目不是一个完整的自动科研 Agent，而是为后续 Agent4Research 系统提供底层数据基础设施。

---

## 1. 项目目标

Agent4Research Kernel 的长期目标是构建一个面向科研场景的论文智能数据系统，支持：

1. 从 arXiv、顶级会议、期刊等来源采集论文数据；
2. 为每篇论文构建结构化画像；
3. 将论文数据统一写入 MongoDB；
4. 支持论文去重、来源追踪和分类追踪；
5. 支持后续 PDF 下载、正文解析、参考文献抽取、目录抽取；
6. 支持从论文中抽取方法、任务、数据集、baseline、benchmark、metric 等信息；
7. 支持给定关键词、研究课题或 idea，检索相关论文；
8. 支持为新研究 idea 推荐相关工作、baseline 和 benchmark；
9. 为未来的 Research Agent 提供可查询、可分析、可扩展的论文数据底座。

---

## 2. 当前已实现功能

当前版本已经实现了 arXiv 数据采集与 MongoDB 入库主链路。

### 2.1 MongoDB 数据库支持

已实现：

* MongoDB 基础配置；
* MongoDB collection 获取；
* MongoDB 连接测试；
* papers 集合索引初始化；
* schema 迁移入口；
* 论文 upsert 插入/更新逻辑。

相关模块：

```text
data_pipeline/db_settings/mongo_config.py
data_pipeline/db_settings/mongo_client.py
data_pipeline/db_settings/init_indexes.py
data_pipeline/scripts_py/init_db.py
data_pipeline/scripts_py/migrate_schema.py
```

---

### 2.2 论文 Schema

项目定义了统一的论文画像 schema，用于描述每篇论文的结构化信息。

当前 schema 包括：

* 基础信息：标题、作者、摘要；
* arXiv 元信息：arXiv ID、URL、PDF URL、分类、版本历史、备注、DOI；
* 来源追踪：论文来自哪些数据源；
* 分类追踪：论文是从哪些 arXiv category 入口被发现的；
* 后处理字段：标签、目录、参考文献、关键词、摘要、贡献、科学问题；
* 实验四要素：pipeline、baselines、benchmarks、metrics；
* 文件路径：本地 PDF、TXT、JSON 路径；
* 处理状态：PDF 是否下载、TXT 是否抽取、参考文献是否抽取等；
* 编辑日志：记录每次插入、更新、补全操作。

相关模块：

```text
data_pipeline/schemas/paper_schema.py
```

---

### 2.3 arXiv 爬取

当前版本使用 arXiv 官方 Python SDK 进行论文采集。

已支持：

* 按 arXiv category 爬取；
* 按日期范围爬取；
* 不指定日期时默认爬取当天；
* 一篇论文解析完成后立即 yield；
* 爬一篇、处理一篇、写入一篇；
* 支持调试时限制每个 category 最大爬取数量；
* 支持正式模式下不限制数量；
* 支持从命令行指定 category；
* 支持重复爬取时不重复插入；
* 支持同一篇论文从多个 category 入口发现时补充 `seen_in_categories`。

相关模块：

```text
data_pipeline/source_configs/arxiv_spec_config.py
data_pipeline/crawlers/base.py
data_pipeline/crawlers/arxiv_crawler.py
data_pipeline/pipelines/arxiv_daily.py
data_pipeline/scripts_py/crawl_arxiv_daily.py
```

---

### 2.4 去重与更新逻辑

当前论文唯一 ID 使用标题规范化后的 SHA1 hash 生成。

处理逻辑：

* 同一篇论文重复爬取时不会重复插入；
* 如果已有论文缺少某些字段，新爬取结果可以补全空字段；
* 支持嵌套字段补全，例如 `arxiv_obj.arxiv_url`；
* 支持同一篇论文在多个 arXiv category 中出现时记录多个入口分类；
* 使用 `edit_logs` 记录插入、更新、无更新等操作。

相关模块：

```text
data_pipeline/utils/text_utils.py
data_pipeline/db_ops/paper_repository.py
```

---

## 3. 项目结构

当前项目结构如下：

```text
agent4research-kernel/
├── data_pipeline/
│   ├── crawlers/
│   │   ├── arxiv_crawler.py
│   │   ├── base.py
│   │   └── __init__.py
│   ├── db_ops/
│   │   ├── paper_repository.py
│   │   └── __init__.py
│   ├── db_settings/
│   │   ├── init_indexes.py
│   │   ├── mongo_client.py
│   │   ├── mongo_config.py
│   │   └── __init__.py
│   ├── pipelines/
│   │   ├── arxiv_daily.py
│   │   └── __init__.py
│   ├── schemas/
│   │   ├── paper_schema.py
│   │   └── __init__.py
│   ├── scripts_py/
│   │   ├── crawl_arxiv_daily.py
│   │   ├── init_db.py
│   │   ├── migrate_schema.py
│   │   └── __init__.py
│   ├── source_configs/
│   │   ├── arxiv_spec_config.py
│   │   ├── conference_gen_config.py
│   │   └── __init__.py
│   ├── utils/
│   │   ├── text_utils.py
│   │   ├── time_utils.py
│   │   └── __init__.py
│   └── __init__.py
├── scripts_md/
│   ├── 1_init_database.md
│   ├── 2_migrate_schema.md
│   ├── 3_crawl_arxiv_daily.md
│   └── __init__.py
├── __init__.py
├── requirements.txt
└── README.md
```

---

## 4. 环境准备

### 4.1 Python 环境

建议使用 Python 3.10。

安装依赖：

```bash
pip install -r requirements.txt
```


---

### 4.2 MongoDB

当前默认连接本地 MongoDB：

```text
mongodb://localhost:27017/
```

默认数据库：

```text
ai4research
```

默认集合：

```text
papers
```

配置文件位置：

```text
data_pipeline/db_settings/mongo_config.py
```

---

## 5. 使用方法

### 5.1 初始化数据库和索引

在项目父目录执行：

```bash
python -m ai4research.data_pipeline.scripts_py.init_db
```

正常输出示例：

```text
✅ MongoDB connected successfully.
✅ MongoDB indexes initialized successfully.
```

---

### 5.2 执行 schema 迁移

当 `paper_schema.py` 更新后，可以执行：

```bash
python -m ai4research.data_pipeline.scripts_py.migrate_schema
```

正常输出示例：

```text
✅ MongoDB connected successfully.
🔹 Schema migration finished. 0 documents upgraded to v1
```

---

### 5.3 爬取指定日期的 arXiv 论文

爬取配置文件中定义的所有 category：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01
```

---

### 5.4 只爬取指定 category

例如只爬取 `cs.AI`：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01 \
  --categories cs.AI
```

同时爬取多个 category：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01 \
  --categories cs.AI cs.CL
```

---

### 5.5 调试模式：限制每个 category 的论文数量

例如每个 category 最多爬取 5 篇：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01 \
  --categories cs.AI cs.CL \
  --max-results 5
```

如果不传 `--max-results`，则默认不限制数量。

---

## 6. 当前 arXiv 配置

当前默认关注的 arXiv category 位于：

```text
data_pipeline/source_configs/arxiv_spec_config.py
```

当前配置示例：

```python
CATEGORIES = [
    "cs.AI",
    "cs.CL",
]
```

后续可以扩展为：

```python
CATEGORIES = [
    "cs.AI",
    "cs.CL",
    "cs.LG",
    "cs.IR",
    "cs.NE",
    "cs.HC",
    "cs.SI",
    "cs.SC",
]
```

---

## 7. 数据字段说明

当前每篇论文会写入 MongoDB 的核心字段包括：

```text
_id
title
aliases
authors
abstract
abstract_entities
arxiv_obj
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
_schema_version
```

其中：

* `_id`：由论文标题规范化后计算 SHA1 得到；
* `arxiv_obj`：存储 arXiv 专属信息；
* `seen_in_categories`：记录该论文是从哪些 arXiv category 入口被发现；
* `seen_in_sources`：记录该论文来自哪些来源，例如 `arXiv`、`ICLR 2026`；
* `edit_logs`：记录插入、更新、重复爬取等操作；
* `processing_status`：记录 PDF、TXT、JSON、目录、参考文献等是否已处理。

---

## 8. 示例数据

一条 arXiv 论文记录示例：

```python
{
    "_id": "c742fe529154080239d119e5d9e4b9d755e675fb",
    "title": "What Benchmarks Don't Measure: The Case for Evaluating Abstention Competence in Autonomous Agents",
    "authors": [
        {
            "name": "Victor Ojewale",
            "affiliation": "",
            "homepage": ""
        },
        {
            "name": "Suresh Venkatasubramanian",
            "affiliation": "",
            "homepage": ""
        }
    ],
    "abstract": "...",
    "accepted_by": "arXiv",
    "arxiv_obj": {
        "arxiv_id": "2606.02965",
        "arxiv_url": "https://arxiv.org/abs/2606.02965",
        "arxiv_pdf_url": "https://arxiv.org/pdf/2606.02965",
        "arxiv_categories": ["cs.AI"],
        "comment": "ACM CAIS 2026: RLEval Workshop Oral Presentation(Best Paper Award)",
        "doi": "",
        "submission_history": [
            {
                "version": "v1",
                "date": "2026-06-01"
            }
        ]
    },
    "base_urls": {
        "arxiv_url": "https://arxiv.org/abs/2606.02965",
        "arxiv_pdf_url": "https://arxiv.org/pdf/2606.02965"
    },
    "seen_in_categories": ["cs.AI"],
    "seen_in_sources": ["arXiv"],
    "edit_logs": [
        {
            "time": "2026-06-04T20:36:41+08:00",
            "op": "insert from arXiv @ cs.AI",
            "detail": "insert paper metadata"
        }
    ]
}
```

---

## 9. 已验证功能

当前已经完成并验证：

* MongoDB 连接成功；
* MongoDB 索引初始化成功；
* schema 迁移脚本可运行；
* arXiv SDK 爬虫可运行；
* 单 category、单天、不限制数量爬取成功；
* `--max-results` 调试参数生效；
* `--categories` 参数生效；
* 重复爬取不会重复插入；
* 同一论文出现在多个 arXiv category 时，能够补充 `seen_in_categories`；
* requests 依赖 warning 已修复。

示例验证结果：

```text
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01 \
  --categories cs.AI

Crawling papers: 242paper [00:16, 15.01paper/s]
🎉 2026-06-01 ~ 2026-06-01 crawl finished. Total papers processed: 242
```

---


## 10. 当前已支持功能

### 10.1 MongoDB 论文数据存储

项目使用 MongoDB 作为论文元数据与后续结构化分析结果的存储后端。每篇论文按照统一的 `paper_schema.py` 进行组织，包含标题、作者、摘要、来源信息、URL、处理状态、后续抽取字段等。

当前支持：

* 初始化 MongoDB 索引；
* 论文记录 upsert，避免重复插入；
* schema migration，用于在 schema 更新后补齐旧记录字段；
* 多来源合并，例如同一篇论文可能同时来自 arXiv、OpenReview 或会议官网。

### 10.2 arXiv 数据源

当前已支持基于 arXiv 官方 Python SDK 的论文爬取。

支持能力：

* 按 arXiv category 爬取，例如 `cs.AI`、`cs.CL`；
* 支持指定日期范围；
* 不指定日期时默认爬取当天；
* 支持 `--max-results` 调试参数；
* 支持 `--categories` 指定单个或多个类别；
* 一篇论文爬取完成后立即写入 MongoDB；
* 同一篇论文出现在多个 arXiv category 时，会记录到 `seen_in_categories`。

示例命令：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01 \
  --categories cs.AI cs.CL \
  --max-results 10
```

正式爬取时可以不传 `--max-results`：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01 \
  --categories cs.AI
```

### 10.3 OpenReview 数据源

当前已支持基于 `openreview-py` 的 OpenReview 论文爬取。

OpenReview 主要用于爬取已经托管在 OpenReview 上的会议论文，例如 ICLR 2026、ICML 2026 等。对于这些会议年份，如果 OpenReview 已经提供标题、作者、摘要、录用类型、PDF 链接等完整信息，则优先使用 OpenReview，不再重复爬取会议官网主页。

当前支持能力：

* 按 venue/year 爬取 OpenReview 论文；
* 支持读取 OpenReview note 中的标题、作者、摘要、关键词、TLDR、primary area、venue、venueid、paperhash、PDF 链接等字段；
* 自动将 OpenReview 的相对 PDF 路径转换为完整 URL；
* 自动解析录用类型，例如 `Poster`、`Oral`；
* 支持 `--max-results` 调试参数；
* 一篇论文爬取完成后立即写入 MongoDB；
* 支持重复爬取去重。

示例命令：

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

### 10.4 当前数据流

当前论文数据采集流程如下：

```text
source_configs/
    定义数据源配置，例如 arXiv categories、OpenReview venue/year

crawlers/
    负责从具体数据源获取论文，并转换为统一 paper_data

pipelines/
    负责组织爬取流程，并逐篇调用 upsert_paper()

db_ops/paper_repository.py
    负责论文入库、去重、字段补全、多来源合并

MongoDB
    存储统一 schema 下的论文记录
```

整体原则是：

```text
爬取一篇论文
    -> 转成统一 paper schema
    -> 立即 upsert 到 MongoDB
```



## 11. 后续计划

### 11.1 数据采集扩展

计划支持更多数据源：

* arXiv 更多 category；
* ICLR；
* NeurIPS；
* ICML；
* ACL；
* EMNLP；
* NAACL；
* AAAI；
* KDD；
* SIGIR；
* TACL；
* 期刊论文数据。

---

### 11.2 PDF 与正文处理

计划支持：

* PDF 下载；
* PDF 转 TXT；
* OCR 识别；
* 目录结构抽取；
* 参考文献抽取；
* 表格、图表、公式等结构化解析。

---

### 11.3 论文画像抽取

计划从论文正文中抽取：

* 研究问题；
* 方法贡献；
* pipeline；
* baselines；
* benchmarks；
* metrics；
* datasets；
* tasks；
* models；
* limitations；
* future work。

---

### 11.4 检索与推荐

计划支持：

* 关键词检索；
* 研究主题检索；
* 相关论文推荐；
* idea 相似论文检索；
* baseline 推荐；
* benchmark 推荐；
* research trend 分析；
* topic graph / citation graph 构建。

---

### 11.5 Research Agent 支撑

长期目标是让该项目成为 Agent4Research 的底层 kernel，为上层 research agent 提供：

* 论文检索能力；
* 论文理解能力；
* 研究脉络整理能力；
* related work 辅助；
* baseline/benchmark 选择辅助；
* idea novelty 检查辅助；
* research planning 辅助。

---

## 12. 项目定位

Agent4Research Kernel 当前阶段定位为：

```text
Research-agent data infrastructure
```

也就是：

```text
面向 Research Agent 的论文数据与检索内核
```

它当前不是完整自动科研系统，而是一个逐步构建中的科研论文数据底座。后续可以在此基础上继续扩展 Agent 能力。
