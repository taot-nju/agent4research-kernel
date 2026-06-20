# 14. 解析 PDF 与检查文档质量

本文档说明如何使用 `document_pipeline` 将已经下载成功的 PDF
解析为标准 Markdown，并执行独立的基础质量检查。

---

## 1. 当前处理链路

```text
MongoDB paper
    ↓
pdf_asset.status = success
    ↓
领取 document_asset 任务
    ↓
PDF 按页渲染为 PNG
    ↓
PageOCRBackend
    ↓
OpenAI-compatible GLM-OCR
    ↓
document.md + parse_report.json
    ↓
document_asset.status = success
    ↓
独立质量检查
    ↓
quality_status = passed / warning / rejected
```

解析成功与质量通过是两个独立概念：

```text
document_asset.status = success
```

表示解析程序成功生成资产。

```text
document_asset.quality_status = passed
```

表示生成的资产通过当前质量规则。

---

## 2. 当前架构边界

### `DocumentParser`

负责完整 PDF 的解析流程。

当前实现：

```text
OCRDocumentParser
```

### `PageOCRBackend`

负责识别单张页面图片。

当前实现：

```text
OpenAICompatibleOCRBackend
```

因此以后可以新增：

```text
本地 vLLM 后端
云端 OpenAI-compatible API
其他商业 OCR API
本地 Python SDK
```

而不修改任务领取、MongoDB 回写和资产存储逻辑。

---

## 3. 启动 GLM-OCR 服务

当前服务器使用 vLLM 部署：

```bash
conda activate env_deploy_glmocr_vllm

vllm serve \
  /data/huggingface/models--zai-org--GLM-OCR/snapshots/ca5d8b3e287e52589e37c28385d9655ee4372f9d \
  --allowed-local-media-path / \
  --port 9000 \
  --speculative-config '{"method": "mtp", "num_speculative_tokens": 1}' \
  --served-model-name glm-ocr
```

文档解析程序通过 Base64 发送页面图片，不依赖 OCR 服务直接读取 PDF 路径。

检查服务：

```bash
curl --fail --silent --show-error \
  http://localhost:9000/v1/models
```

---

## 4. OCR 服务配置

默认配置：

```text
base_url:       http://127.0.0.1:9000/v1
model_name:     glm-ocr
api_key:        EMPTY
timeout:        300 秒
```

支持以下环境变量：

```bash
export AI4RESEARCH_OCR_BASE_URL="http://127.0.0.1:9000/v1"
export AI4RESEARCH_OCR_MODEL="glm-ocr"
export AI4RESEARCH_OCR_API_KEY="EMPTY"
export AI4RESEARCH_OCR_TIMEOUT_SECONDS="300"
```

不要把真实 API Key 写入代码、文档或 Git。

---

## 5. 解析指定论文

从项目父目录执行：

```bash
cd ~
```

解析一篇指定论文：

```bash
python -m ai4research.document_pipeline.scripts_py.parse_documents \
  --paper-id <paper_id>
```

默认参数：

```text
limit:               1
render_dpi:          200
page_workers:        4
max_tokens:          8192
temperature:         0
lease_seconds:       3600
max_attempts:        3
retry_delay_seconds: 60
```

已经是：

```text
document_asset.status = success
```

的论文不会被重复领取。

---

## 6. 按会议解析

示例：

```bash
python -m ai4research.document_pipeline.scripts_py.parse_documents \
  --accepted-by "NeurIPS 2025" \
  --limit 10
```

当前执行模式：

```text
论文之间：顺序执行
单篇论文内部：页面并发
```

`--page-workers` 只控制单篇论文内部的页面 OCR 并发数。

---

## 7. 从全部任务中解析

必须显式使用 `--all`：

```bash
python -m ai4research.document_pipeline.scripts_py.parse_documents \
  --all \
  --limit 10
```

即使使用 `--all`，仍然受到 `--limit` 限制。

首次扩大批量时应逐步增加：

```text
1 → 5 → 10 → 100
```

不要直接对全部 35,000 余篇任务运行。

---

## 8. 常用解析参数

降低显存或服务压力：

```bash
python -m ai4research.document_pipeline.scripts_py.parse_documents \
  --paper-id <paper_id> \
  --page-workers 2
```

修改页面渲染 DPI：

```bash
python -m ai4research.document_pipeline.scripts_py.parse_documents \
  --paper-id <paper_id> \
  --render-dpi 150
```

修改单页最大输出长度：

```bash
python -m ai4research.document_pipeline.scripts_py.parse_documents \
  --paper-id <paper_id> \
  --max-tokens 4096
```

---

## 9. 标准资产目录

每篇论文的解析结果保存在：

```text
documents/<id前2位>/<id第3-4位>/<paper_id>/
```

当前 MVP 生成：

```text
document.md
parse_report.json
raw/
```

示例：

```text
documents/95/97/95975c4de39a40041a99313a59c4a61b96e53811/
├── document.md
├── parse_report.json
└── raw/
```

MongoDB 中只保存相对于 `AI4RESEARCH_DATA_ROOT` 的路径。

---

## 10. 文档任务状态

```text
pending
    已有可用 PDF，等待解析

running
    某个 Worker 正在解析

success
    标准文档资产已经生成

failed
    解析失败，到达重试时间后可以重新领取

blocked
    当前没有成功下载的 PDF

stale
    PDF 已变化，需要重新解析
```

任务使用：

```text
worker_id
lease_until
attempts
next_retry_at
```

支持进程异常退出后的恢复。

---

## 11. 质量检查

检查尚未质检的指定论文：

```bash
python -m ai4research.document_pipeline.scripts_py.check_document_quality \
  --paper-id <paper_id>
```

检查某个会议：

```bash
python -m ai4research.document_pipeline.scripts_py.check_document_quality \
  --accepted-by "NeurIPS 2025" \
  --limit 100
```

检查全部已解析文档：

```bash
python -m ai4research.document_pipeline.scripts_py.check_document_quality \
  --all \
  --limit 100
```

规则升级后重新检查：

```bash
python -m ai4research.document_pipeline.scripts_py.check_document_quality \
  --paper-id <paper_id> \
  --recheck
```

重新质检不会重新执行 OCR。

---

## 12. 当前基础质量规则

当前检查：

```text
Markdown 文件存在
Markdown 正文非空
PDF 页数有效
Markdown 页标记数与页数一致
实际字符数与解析记录基本一致
平均每页字符数不过低
文档开头能够匹配论文标题
解析报告页数与成功状态一致
```

质量状态：

```text
passed
warning
rejected
```

质量规则具有独立版本，可以在不重新 OCR 的情况下升级和重跑。

---

## 13. 自动化测试

安装开发依赖：

```bash
python -m pip install -r ~/ai4research/requirements-dev.txt
```

运行全部测试：

```bash
cd ~/ai4research
python -m pytest -q
```

当前测试不连接 MongoDB，也不调用真实 OCR 服务。

---

## 14. 当前 MVP 边界

当前已经实现：

```text
OpenAI-compatible GLM-OCR 后端
OCR 服务启动前健康检查
单页 OCR 标准接口
完整 PDF 按页并发解析
Markdown 与解析报告
MongoDB 原子任务领取
任务租约、失败重试和所有权检查
正式资产提交
独立质量检查与重新质检
最小自动化测试
```

当前尚未实现：

```text
多篇论文同时并发
任务处理期间的周期性租约续期
原生 PDF 文本层优先提取
OCR fallback 决策
纯文本资产生成
布局 JSON 和页坐标
失败页面断点续跑
文档资产全量审计与状态报告
```
