# 切换到根目录
```bash
cd ~
```

# Phase 0 — GROBID Spike（动手前先验证 GROBID 在我们语料上的效果）

功能②（参考文献 + 引用上下文）依赖 GROBID。导师指出 GROBID "没法完整获取"，
所以**先验证、再集成**。这一步会：下载我们库里 2-3 篇论文的 PDF → 交给 GROBID →
把 TEI 存到本地 → 计算质量指标并给出 PASS/FAIL。

只读 Mongo，不写任何论文字段。

## 1. 启动 GROBID（本地 Docker，CPU 即可）
```bash
# 轻量 CRF 版（拉取快、CPU 友好）
docker run --rm --init -p 8070:8070 lfoppiano/grobid:0.8.0

# 或官方完整版（解析质量更好，体积大、首启慢）
# docker run --rm --init -p 8070:8070 grobid/grobid:0.8.1
```
另开一个终端确认服务起来了：
```bash
curl -s http://localhost:8070/api/isalive   # 期望输出: true
```

## 2. 跑 spike
```bash
python -m ai4research.field_processing_pipeline.scripts_py.test_grobid --limit 3
```

不想本地起 Docker，也可指向托管的 GROBID（用环境变量覆盖）：
```bash
GROBID_URL=https://kermitt2-grobid.hf.space \
  python -m ai4research.field_processing_pipeline.scripts_py.test_grobid --limit 1
```
> 注意：托管的 HF Space 经常休眠/限额；生产请用本地 Docker。

## 3. 通过标准（spike 会自动判断）
- `n_biblstruct` ≥ 20 且与论文实际参考文献数量大致相符；
- `title_rate` ≥ 0.80（biblStruct 解析出非空标题的比例）；
- `n_sentences` > 0（说明 `segmentSentences` 生效）；
- `resolvable_target_rate` ≥ 0.70（in-text `<ref type="bibr">` 的 `@target` 能在
  参考文献里找到对应 `xml:id` 的比例——这正对应导师说的"没法完整获取"，文献口径 0.76–0.91）。

TEI 会存到 `field_processing_pipeline/cache/store/grobid_tei/<paper_id>.tei.xml`，
可用在线 XML viewer（如 https://jsonformatter.org/xml-viewer）查看。

若全部论文都不达标：换官方完整版镜像 `grobid/grobid:<ver>-full`，
或检查是不是扫描版 PDF（GROBID 对扫描件会报 `NO_BLOCKS`），并反馈导师。
