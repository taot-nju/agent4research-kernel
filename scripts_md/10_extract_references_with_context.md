# 切换到根目录
```bash
cd ~
```

# 功能② — 抽取参考文献 + 每条的 in-text 引用上下文（GROBID）

对一篇论文：下载 PDF → GROBID 解析 → 写入 `references` 字段。每条参考文献带
`occurrences`（它在正文每次被引处：所在句子下标 `sentence_index`、章节 `section`、
命中文本 `matched_text`）。**窗口（前 N 句 + 本句 + 后 N 句）在读取时现算，不落库**，
所以 N 可任意改，无需重抽。

## 前置
1. **GROBID 服务必须可达**（见 `11_run_grobid_spike.md` 起 Docker）：
   ```bash
   docker run --rm --init -p 8070:8070 lfoppiano/grobid:0.8.0
   curl -s http://localhost:8070/api/isalive   # true
   ```
   默认连 `http://localhost:8070`，可用环境变量 `GROBID_URL` 覆盖。
2. 论文的 `base_urls` 里要有 PDF 链接（采集层已写入 `*_pdf_url`）。本步骤会自动
   下载 PDF 到本地并回填 `local_pdf_path` + `processing_status.pdf_downloaded`。

## 单篇（最常用于验证）
```bash
python -m ai4research.field_processing_pipeline.scripts_py.extract_references \
  --id <paper_id> \
  --force
```

## 按会议 / 来源批量
```bash
# 按 accepted_by
python -m ai4research.field_processing_pipeline.scripts_py.extract_references \
  --accepted-by "ICLR 2025" --limit 50

# 按来源
python -m ai4research.field_processing_pipeline.scripts_py.extract_references \
  --source OpenReview --limit 50 --sleep 0.5
```

## 参数
- `--id`：只处理单篇 `_id`
- `--accepted-by` / `--source`：按字段批量选论文
- `--limit`：最多处理多少篇
- `--window-n`：窗口句数（**读时现算**，此处仅预留，不影响落库）
- `--force`：忽略 `references_extracted` 幂等闸门，强制重抽
- `--sleep`：每篇间隔秒（限流，GROBID 单实例时建议设）

## 优雅降级（不会因为一篇坏论文中断整批）
- 没有 PDF 链接 → 记 `no_url` 跳过；
- 下载到的不是 PDF（HTML 错误页）→ `not_pdf` 跳过；
- 扫描版 PDF（GROBID 返回 `NO_BLOCKS`）→ 记 `GrobidError` 跳过；
- in-text 引用的 `@target` 悬空（GROBID 没链到某条 bib）→ 进 `unmatched_citations`
  计数（写在 edit_logs 的 detail 里），**不丢、不报错**。

## 落库结构（`references` 数组，每个元素）
```jsonc
{
  "ref_id": "a1b2c3d4e5f60718",        // sha1(paper_id+':'+bib_id)[:16]，稳定可复现
  "bib_id": "b2",                       // GROBID <biblStruct xml:id>
  "title": "Compilers: ...",            // 顶层冗余一份，兼容现有 references.title 索引
  "raw": "Alfred V Aho. 2007. ...",
  "parsed": { "title": "...", "year": "2007", "authors": ["Alfred V Aho"],
              "first_author_surname": "aho", "doi": "" },
  "extractor": "grobid",
  "occurrences": [                      // 第 k 次出现 = occurrences[k-1]；times = len(occurrences)
    { "occ_id": 1, "section": "3 Method", "sentence_index": 27,
      "char_span": [2355, 2366], "matched_text": "(Aho, 2007)",
      "match_method": "grobid_target", "match_confidence": 1.0, "ambiguous": false }
  ]
}
```
> `body_sentences`（整篇句子数组，窗口真相源）落在
> `field_processing_pipeline/cache/store/body_sentences/<paper_id>.json`，不进 Mongo。
> 读时用 `extractors.sentence_window.build_window(body_sentences, sentence_index, n)` 现算窗口。
