# 13. 下载与管理论文 PDF

本文档说明如何使用 `fulltext_pipeline` 按需下载、并发下载、续传、刷新和审计论文 PDF。

---

## 1. 模块定位

`data_pipeline/` 负责论文元数据的采集、融合和 MongoDB 存储。

`fulltext_pipeline/` 负责论文全文资产，包括：

* PDF 地址解析；
* PDF 下载；
* 断点续跑；
* 并发任务领取；
* 按域名限速；
* PDF 文件校验；
* PDF 资产审计；
* 后续 TXT 提取、OCR 和结构化解析。

PDF、TXT 等大文件不存放在 Git 仓库中，而是存放在独立资产目录中。

---

## 2. 配置资产根目录

当前服务器使用：

```bash
export AI4RESEARCH_DATA_ROOT=/data/ai4research_assets
```

该配置已经写入：

```text
~/.bashrc
```

重新打开终端后会自动生效。

可以通过下面的命令确认：

```bash
echo $AI4RESEARCH_DATA_ROOT
```

预期输出：

```text
/data/ai4research_assets
```

---

## 3. 初始化资产目录

在新服务器部署项目后，执行：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.create_asset_directories
```

创建：

```text
/data/ai4research_assets/
├── pdf
├── structured
├── temp
└── txt
```

该命令可以重复执行，不会删除已有文件。

---

## 4. PDF 存储规则

MongoDB 只保存相对路径，例如：

```text
pdf/af/32/af32138f7c04e15f3d021a8008bbc64b66f1ba23.pdf
```

当前机器上的实际路径为：

```text
/data/ai4research_assets/pdf/af/32/af32138f7c04e15f3d021a8008bbc64b66f1ba23.pdf
```

论文按照 `_id` 的前四个字符进行两级分目录，避免将数万篇 PDF 放在同一个目录中。

迁移到新机器时，只需：

1. 复制整个资产目录；
2. 迁移或连接 MongoDB；
3. 设置新机器上的 `AI4RESEARCH_DATA_ROOT`。

MongoDB 中保存的是相对路径，通常不需要逐条修改。

---

## 5. PDF 来源优先级

同一篇论文可能同时具有多个 PDF 地址。

当前选择顺序为：

```text
ACL Anthology 正式版
→ AAAI Official 正式版
→ PMLR 正式版
→ OpenReview 版本
→ arXiv 版本
→ base_urls 历史字段兜底
```

如果优先地址下载失败，程序会继续尝试后面的候选地址。

---

## 6. 下载指定论文

```bash
python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --paper-id <paper_id>
```

例如：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --paper-id af32138f7c04e15f3d021a8008bbc64b66f1ba23
```

默认最多处理一篇论文。

---

## 7. 下载指定会议

例如，顺序下载 ICLR 2022 中最多 10 篇论文：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --accepted-by "ICLR 2022" \
  --limit 10
```

并发下载最多 100 篇：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --accepted-by "ICLR 2022" \
  --limit 100 \
  --workers 4
```

`--workers` 是全局线程数。

即使设置多个 Worker，各个网站仍然受到独立限速策略约束。

---

## 8. 下载 Query 召回的候选论文

候选 ID 文件格式：

```text
# Agent Memory 相关候选论文
paper_id_1
paper_id_2
paper_id_3
```

要求每行一个论文 `_id`。

程序会自动忽略：

* 空行；
* 以 `#` 开头的注释行；
* 重复 ID。

执行：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --ids-file candidate_paper_ids.txt \
  --limit 100 \
  --workers 8
```

这适用于：

```text
用户 Query
→ 通过标题和摘要粗召回
→ 输出候选 paper_id
→ 按需下载候选论文 PDF
```

---

## 9. 下载全部待处理论文

必须显式提供 `--all`：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --all \
  --limit 100 \
  --workers 8
```

即使使用 `--all`，仍然受 `--limit` 控制。

建议先小规模测试，不要一开始直接下载全部论文。

---

## 10. 断点续跑

PDF 状态保存在：

```text
pdf_asset.status
```

主要状态包括：

```text
pending       尚未下载
running       某个 Worker 正在处理
success       已下载并通过校验
failed        下载失败，可以重试
unavailable   当前没有 PDF URL
```

已经是 `success` 的论文不会被重复领取。

因此，假设第一次下载了 3 万篇后断网，重新运行相同命令时，不需要重新检查或下载前面的 3 万篇。

程序只会领取仍然符合条件的任务。

`running` 状态具有租约。进程意外退出后，租约过期的任务可以被后续 Worker 重新领取。

---

## 11. 下载重试参数

默认每篇论文最多领取 3 次：

```bash
--max-attempts 3
```

失败后的等待时间默认为 60 秒：

```bash
--retry-delay-seconds 60
```

任务租约默认是 600 秒：

```bash
--lease-seconds 600
```

示例：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --accepted-by "ACL 2025" \
  --limit 100 \
  --workers 4 \
  --max-attempts 3 \
  --retry-delay-seconds 120 \
  --lease-seconds 900
```

---

## 12. unavailable 状态

如果一篇论文当前没有任何 PDF URL，程序会标记：

```text
pdf_asset.status = unavailable
```

这种情况不会消耗真正的下载尝试次数。

例如目前部分 ICML 2026 记录只有会议页面，没有 PDF 地址。

后续爬虫补充 PDF URL 后，需要执行可用性刷新。

刷新某个会议：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.refresh_pdf_availability \
  --accepted-by "ICML 2026"
```

刷新指定论文：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.refresh_pdf_availability \
  --paper-id <paper_id>
```

刷新全部 unavailable 记录：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.refresh_pdf_availability \
  --all
```

检测到 PDF URL 后，状态会从：

```text
unavailable → pending
```

之后可以重新运行下载命令。

---

## 13. PDF 下载安全机制

下载过程采用：

```text
PDF URL
→ Worker 独立临时文件
→ PDF 基础校验
→ 续租并确认任务所有权
→ 原子移动到正式路径
→ MongoDB 写入 success
```

临时文件以 `.part` 形式保存。

只有下载完成并通过校验后，才会原子移动到正式 PDF 路径。

基础校验包括：

* 文件存在；
* 文件大小合理；
* 文件头以 `%PDF-` 开始；
* 计算 SHA256。

MongoDB 中记录：

```text
pdf_asset.relative_path
pdf_asset.size_bytes
pdf_asset.sha256
pdf_asset.source
pdf_asset.source_url
pdf_asset.final_url
pdf_asset.downloaded_at
```

---

## 14. 按域名限速

当前不同来源可以并行，但同一来源受到独立限制。

第一版保守策略包括：

```text
arxiv.org
openreview.net
aclanthology.org
ojs.aaai.org
proceedings.mlr.press
```

全局 `--workers` 不等于某个网站的并发数。

例如：

```bash
--workers 8
```

表示进程最多运行 8 个任务，但 OpenReview、arXiv 等域名仍按照各自策略限制请求频率。

---

## 15. 审计 PDF 资产

审计程序只读取数据库和本地文件，不会自动修改数据库，也不会删除文件。

检查指定论文：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.audit_pdf_assets \
  --paper-id <paper_id>
```

检查某个会议：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.audit_pdf_assets \
  --accepted-by "ICLR 2022" \
  --limit 100
```

检查全部已下载论文中的前 1000 篇：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.audit_pdf_assets \
  --all \
  --limit 1000
```

审计内容包括：

* 相对路径是否为空；
* 本地文件是否存在；
* PDF 基础校验是否通过；
* 文件大小是否与 MongoDB 一致；
* SHA256 是否与 MongoDB 一致。

---

## 16. 常用命令总结

初始化资产目录：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.create_asset_directories
```

下载一篇论文：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --paper-id <paper_id>
```

并发下载某个会议：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --accepted-by "ICLR 2022" \
  --limit 100 \
  --workers 4
```

下载 Query 候选论文：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --ids-file candidate_paper_ids.txt \
  --limit 100 \
  --workers 8
```

刷新 PDF 可用性：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.refresh_pdf_availability \
  --all
```

审计 PDF：

```bash
python -m ai4research.fulltext_pipeline.scripts_py.audit_pdf_assets \
  --all \
  --limit 1000
```
