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

当前版本已经实现了 arXiv 数据采集与 MongoDB 入库主链路，并接入了 OpenReview（会议）数据采集与多源富化主链路。

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

### 2.5 OpenReview 爬取（会议论文）

本功能移植自 `openreview-paper-portrait`，把其完整的抓取/富化引擎接入本仓库的
「Crawler → Pipeline → db_ops → MongoDB」架构，作为一等的 OpenReview 数据源。

已支持：

* 兼容 OpenReview v2（api2.openreview.net）与 v1（api.openreview.net），按 venue 自动探测可用版本；
* 按 venue 抓取（`accepted` / `all` / `withdrawn,rejected,...`），偏移分页 + 重试退避，避免漏抓；
* 把每条 note 映射为统一 schema，写入新增的 `openreview_obj` 字段；
* `_id` 复用「标题规范化 SHA1」，因此与 arXiv 天然去重：同一篇论文若先来自 arXiv、
  后被会议接收，会落到同一条记录上（`accepted_by` 由 arXiv 覆盖为会议名，且**不会**覆盖已有的 `arxiv_obj`）；
* 多源富化，均可选、独立、可降级：
  * arXiv：按标题匹配 arXiv id / URL / 首末版本日期；
  * Semantic Scholar：引用数 + DOI（按 arXiv id 批量，或按标题回退）；
  * Papers-with-Code：官方 GitHub 仓库；
  * OpenAlex：多时间戳引用历史（`cite_numbers` 写入 `["<count>@<YYYY.MM.DD>", ...]`）；
  * 作者画像：主页 + 论文发表当年的单位；
  * LLM 抽取：通读 PDF 抽取 Baselines / Benchmarks / Metrics（标记 `auto_extracted`，多 provider：
    claude-cli / anthropic / openai / deepseek / openrouter）；
* 可选额外输出 Obsidian Markdown「论文画像」（vault），主存储仍是 MongoDB；
* 重复爬取幂等：不重复插入，只补全空字段、累积 `cite_numbers` 时间戳快照、追加 `edit_logs`；
* 各外部源磁盘缓存（`<vault>/.cache/`），重复运行更快、对网络抖动更鲁棒。

相关模块：

```text
data_pipeline/source_configs/openreview_config.py
data_pipeline/crawlers/openreview/            # 移植并模块化的抓取/富化引擎
data_pipeline/crawlers/openreview_crawler.py  # OpenReviewCrawler + record_to_paper_data 映射
data_pipeline/pipelines/openreview_venue.py
data_pipeline/scripts_py/crawl_openreview.py
data_pipeline/db_ops/paper_repository.py      # 新增 upsert_openreview_paper（跨源合并，不覆盖 arxiv_obj）
```

---

## 3. 项目结构

当前项目结构如下：

```text
agent4research-kernel/
├── data_pipeline/
│   ├── crawlers/
│   │   ├── arxiv_crawler.py
│   │   ├── openreview_crawler.py        # OpenReviewCrawler + record_to_paper_data 映射
│   │   ├── openreview/                  # 移植并模块化的 OpenReview 抓取/富化引擎
│   │   │   ├── helpers.py               # Throttle / JsonCache / 重试 / 文本规范化 / cval
│   │   │   ├── source.py                # OpenReviewSource（v1/v2）+ ProfileResolver
│   │   │   ├── enrichment.py            # arXiv / S2 / Papers-with-Code / OpenAlex
│   │   │   ├── llm_extract.py           # 多 provider LLM 抽取
│   │   │   ├── record.py                # PaperRecord + build_base_record + apply_*
│   │   │   ├── vault_writer.py          # 可选 Markdown 论文画像输出
│   │   │   ├── collect.py               # collect_records（连接→抓取→富化，不写盘）
│   │   │   └── __init__.py
│   │   ├── base.py
│   │   └── __init__.py
│   ├── db_ops/
│   │   ├── paper_repository.py          # upsert_paper（arXiv）+ upsert_openreview_paper（会议）
│   │   └── __init__.py
│   ├── db_settings/
│   │   ├── init_indexes.py
│   │   ├── mongo_client.py
│   │   ├── mongo_config.py
│   │   └── __init__.py
│   ├── pipelines/
│   │   ├── arxiv_daily.py
│   │   ├── openreview_venue.py
│   │   └── __init__.py
│   ├── schemas/
│   │   ├── paper_schema.py
│   │   └── __init__.py
│   ├── scripts_py/
│   │   ├── crawl_arxiv_daily.py
│   │   ├── crawl_openreview.py
│   │   ├── init_db.py
│   │   ├── migrate_schema.py
│   │   └── __init__.py
│   ├── source_configs/
│   │   ├── arxiv_spec_config.py
│   │   ├── conference_gen_config.py
│   │   ├── openreview_config.py
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
│   ├── 4_crawl_openreview.md
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
🔹 Schema migration finished. 0 documents upgraded to v2
```

> 注意：当前 schema 版本为 **v2**（新增 `openreview_obj` 字段）。从旧库升级时执行本脚本即可
> 自动为已有记录补全 `openreview_obj` 空字段；随后再执行 `init_db` 重建索引（新增
> `openreview_obj.forum_id` 的 partial 唯一索引）。

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

### 5.6 爬取 OpenReview venue（会议论文）

完整命令示例见 `scripts_md/4_crawl_openreview.md`。常用命令：

冒烟测试（不写库、不富化、只抓 3 篇）：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference \
  --enrich none \
  --no-profiles --no-github --no-cited-history --no-llm-extract \
  --limit 3 --dry-run
```

小规模真实入库（核心字段）：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference \
  --enrich none --no-profiles --no-github --no-cited-history --no-llm-extract \
  --limit 5
```

默认档位（Full + LLM 抽取，开启全部富化）：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference --limit 10
```

额外输出 Markdown 论文画像（vault，主存储仍是 MongoDB）：

```bash
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference --limit 5 \
  --vault --vault-dir openreview_vault
```

说明：

* `--venue` 为 OpenReview venue id，例如 `ICLR.cc/2024/Conference`、`NeurIPS.cc/2023/Conference`；
* `--enrich none|arxiv|s2|all` 控制 arXiv / Semantic Scholar 富化档位；
* `--profiles` / `--github` / `--cited-history` / `--llm-extract` 默认开启，可用 `--no-xxx` 关闭；
* OpenReview 匿名即可抓取，提供 `--username/--password`（或环境变量 `OPENREVIEW_USERNAME/OPENREVIEW_PASSWORD`）会显著加快作者画像解析；
* 默认配置（venue、富化档位、限流间隔、环境变量名）见 `data_pipeline/source_configs/openreview_config.py`。

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
openreview_obj
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

* `_id`：由论文标题规范化后计算 SHA1 得到（arXiv 与 OpenReview 共用同一规则，实现跨源去重）；
* `arxiv_obj`：存储 arXiv 专属信息；
* `openreview_obj`：存储 OpenReview（会议）专属信息，与 `arxiv_obj` 平行，包含
  `forum_id`、`openreview_url`、`openreview_pdf`、`venue`、`presentation_type`、
  `primary_area`、`keywords`、`authorids`、`first_author_hp`、`affiliations`、
  `s2_paper_id`、`corpus_id`、`doi`、`arxiv_id`、`time_start/time_end`，以及
  标记由 LLM 抽取的 `auto_extracted`；非 OpenReview 记录该字段保持为空；
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

一条 OpenReview（会议）论文记录示例（节选，来自 ICLR 2024，核心字段未富化）：

```python
{
    "_id": "c5319b816e59781f83ce108ff1d3f5ecc920ba54",
    "title": "Exposing Text-Image Inconsistency Using Diffusion Models",
    "authors": [
        {"name": "Mingzhen Huang", "affiliation": "", "homepage": ""},
        {"name": "Shan Jia", "affiliation": "", "homepage": ""}
    ],
    "abstract": "...",
    "accepted_by": "ICLR 2024",
    "arxiv_obj": {
        "arxiv_id": "",
        "arxiv_url": "",
        "arxiv_pdf_url": "",
        "arxiv_categories": [],
        "comment": "",
        "doi": "",
        "submission_history": [{"version": "", "date": ""}]
    },
    "openreview_obj": {
        "forum_id": "Ny150AblPu",
        "number": 5,
        "openreview_url": "https://openreview.net/forum?id=Ny150AblPu",
        "openreview_pdf": "https://openreview.net/pdf/5ef1...cf04.pdf",
        "venue": "ICLR 2024",
        "presentation_type": "poster",
        "primary_area": "societal considerations including fairness, safety, privacy",
        "keywords": ["inconsistency detection", "multi-modal learning", "diffusion models"],
        "authorids": ["~Mingzhen_Huang2", "~Shan_Jia1"],
        "first_author_hp": "",
        "affiliations": [],
        "s2_paper_id": "",
        "corpus_id": "",
        "doi": "",
        "arxiv_id": "",
        "auto_extracted": [],
        "time_start": "202309",
        "time_end": "202401"
    },
    "base_urls": {
        "openreview_url": "https://openreview.net/forum?id=Ny150AblPu"
    },
    "more_urls": {
        "openreview_pdf": "https://openreview.net/pdf/5ef1...cf04.pdf",
        "others": ["https://openreview.net/pdf/5ef1...cf04.pdf"]
    },
    "tags": ["inconsistency-detection", "multi-modal-learning", "diffusion-models"],
    "seen_in_sources": ["ICLR 2024"],
    "_schema_version": 2,
    "edit_logs": [
        {
            "time": "2026-06-05T21:02:02+08:00",
            "op": "insert from ICLR 2024",
            "detail": "insert paper metadata (OpenReview)"
        }
    ]
}
```

> 开启富化后（`--enrich all --profiles --github --cited-history --llm-extract`），
> `arxiv_obj`、`base_urls.arxiv_url`、`more_urls.code`、`cite_numbers`、
> `openreview_obj.affiliations/first_author_hp/s2_paper_id`、以及
> `baselines/benchmarks/metrics` 等字段会被相应填充。

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

OpenReview 链路已端到端验证：

* OpenReview v2/v1 自动探测、按 venue 偏移分页抓取成功（ICLR 2024 实测 2260 篇）；
* note → `paper_schema`（v2）映射正确，`openreview_obj` 完整填充；
* `_id` 使用标题哈希，与 arXiv 跨源去重；`upsert_openreview_paper` 跨源合并时
  **不会**覆盖已有的 `arxiv_obj`，并把 `accepted_by` 覆盖为会议名；
* 重复爬取幂等：不重复插入、`cite_numbers` 按日期累积、`edit_logs` 追加更新记录；
* 可选 Markdown vault（每篇一个 `.md` + `_index.json`）输出正确；
* `--dry-run` 不写库、不写文件；
* `init_db` 成功创建 `openreview_obj.forum_id` partial 唯一索引。

示例验证结果：

```text
python -m ai4research.data_pipeline.scripts_py.crawl_arxiv_daily \
  --start 2026-06-01 \
  --end 2026-06-01 \
  --categories cs.AI

Crawling papers: 242paper [00:16, 15.01paper/s]
🎉 2026-06-01 ~ 2026-06-01 crawl finished. Total papers processed: 242
```

```text
python -m ai4research.data_pipeline.scripts_py.crawl_openreview \
  --venue ICLR.cc/2024/Conference \
  --enrich none --no-profiles --no-github --no-cited-history --no-llm-extract \
  --limit 2

Connected via API v2 [anonymous] (probe: 1 accepted note(s), group=True)
Fetching notes for venueid=ICLR.cc/2024/Conference ... -> 2260 notes
✅ Inserted new paper (OpenReview): c5319b816e59781f83ce108ff1d3f5ecc920ba54
🎉 OpenReview venue ICLR.cc/2024/Conference crawl finished. Total papers processed: 2
```

---

## 10. 后续计划

### 10.1 数据采集扩展

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

### 10.2 PDF 与正文处理

计划支持：

* PDF 下载；
* PDF 转 TXT；
* OCR 识别；
* 目录结构抽取；
* 参考文献抽取；
* 表格、图表、公式等结构化解析。

---

### 10.3 论文画像抽取

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

### 10.4 检索与推荐

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

### 10.5 Research Agent 支撑

长期目标是让该项目成为 Agent4Research 的底层 kernel，为上层 research agent 提供：

* 论文检索能力；
* 论文理解能力；
* 研究脉络整理能力；
* related work 辅助；
* baseline/benchmark 选择辅助；
* idea novelty 检查辅助；
* research planning 辅助。

---

## 11. 项目定位

Agent4Research Kernel 当前阶段定位为：

```text
Research-agent data infrastructure
```

也就是：

```text
面向 Research Agent 的论文数据与检索内核
```

它当前不是完整自动科研系统，而是一个逐步构建中的科研论文数据底座。后续可以在此基础上继续扩展 Agent 能力。
