# `field_processing_pipeline` 实施与设计规划

> 功能① 通过论文 title 获取**被引次数**  ·  功能② 提取论文**参考文献及其在正文中的引用上下文**
>
> 状态：**设计/规划稿（待与导师讨论拍板）** · 编写日期：2026-06-13 · 分支：`main`
>
> 本文档 = 需求复述与确认 + 外部方案调研（2026 现状，含实测证据） + 改进版 JSON 设计 + 模块落地蓝图 + 实施路线图 + 待导师确认的开放问题。

---

## 0. TL;DR（给导师的一页纸）

1. **两个功能本质是"字段处理 / 富化（enrichment）"，不是"采集"**：它们读已入库的论文，补 `cite_numbers`（功能①）和 `references`（功能②）两个字段，因此独立成一个与 `data_pipeline/` 平级的新模块 `field_processing_pipeline/`，**不照搬 `crawlers/` 这套采集语义**。

2. **功能①（被引量）能很快做出来，但"一个权威数字"在技术上不存在**。各家口径天然不一致——这不是 bug。**实证**：用我们自己缓存里的同一篇论文 *Instance-dependent Early Stopping*，**OpenAlex = 1 次**而 **Semantic Scholar = 14 次**。所以建议**多源并存、分源留痕、记查询时间**，而不是存一个数。

3. **功能②（引文 + 上下文）有一个隐藏的硬阻塞**：要"前 N 句 + 本句 + 后 N 句"必须有论文**正文**，而**当前仓库里没有任何代码会下载 PDF / 抽正文**（`local_pdf_path` / `local_txt_path` 永远为空，`processing_status.pdf_downloaded/txt_extracted` 永远是 `False`）。功能②不是"新建四个文件"就能跑，它**先依赖一个尚未实现的 PDF→正文阶段**。

4. **功能②有一条"零部署的 MVP 捷径"**：Semantic Scholar API 直接返回每条参考文献的 `contexts`（引用上下文，**已 2026 实测可用、免 API key**）。但它**只给"本句"**，给不了可调的"前 N 句/后 N 句"，且覆盖率约 65–80%。**真正达到导师要求的可调 N 句窗口，最终仍需 GROBID + 全文。**

5. **关于导师的 JSON 设计**：导师明确邀请"一起设计更好的"。我逐点评析了两版，并给出一版**改进结构**（详见 §4.4）——核心改动是：**只存"句子下标 + 字符偏移"作为唯一真相源，任意 N 的窗口在读取时现算，不再为每个 N 预存 `windows_1/windows_2`**。

6. **一处需要确认的理解**（导师 Allam 例子已暗示，但请确认）：上下文取的是**"引用方说的话"**——即正文里发生引用那一处、引用者自己写的句子，**不是被引文章本身的内容**。本规划按此理解设计。

> 文末 §7 列出了 **8 个需要导师拍板的问题**；其中最关键的三个是：被引量要"一个数"还是"多源表"？功能② 先交 S2-MVP 还是直接立项 GROBID？PDF→正文这个前置阶段归谁、何时就绪？

---

## 1. 需求复述与确认

### 1.1 功能① —— 通过 title 获取被引次数

- **输入**：一篇 paper 的 `title`。
- **输出**：它的被引数量。
- **导师明确点出的痛点**：(a) **不够精确**；(b) 与 **Semantic Scholar / Google Scholar 的引用量不统一**。
- **导师的指示**：先**整理成一个功能函数**即可，后期放进 `field_processing_pipeline`。
- **学生既有进展**：此前已用 **OpenAlex** 实现过（见 §2.1 的 prior art）。

### 1.2 功能② —— 提取参考文献及其引用上下文

对一篇论文：

1. **提取所有参考文献条目**（references）；
2. 对**每一条**参考文献，提取它在正文中**每一次被引用**处的上下文：**前 N 句 + 本句 + 后 N 句**（`N` 是可自定义的窗口参数：`N=1` → 3 句，`N=2` → 5 句）；
3. 同一条参考文献可能在正文中**出现多次**，要**全部收集**，并记录出现次数 `times`。

**导师的例子**：参考文献 *Allam, 2024* 在正文里以 `Allam, 2024` 的形式出现，引用发生处引用者写了一些话——我们要抓的就是这些话（及其前后 N 句）。

### 1.3 一个需要确认的关键理解 ✅

> **上下文 = 引用方（citing paper）在引用发生处说的话**，是论文正文里的句子；**不是被引文献本身的摘要/内容**。

导师的 Allam 例子（"作者引用这篇文章的时候说了一些话"）已经表明是前者。**本规划按"引用方上下文"设计。若理解有误请纠正——这会改变整个功能② 的数据来源。**

### 1.4 定位：这是"富化"，不是"采集"

| | 采集层 `data_pipeline/` | 富化层 `field_processing_pipeline/`（本任务） |
|---|---|---|
| 语义 | 从数据源抓论文，`crawl()` 是 generator | 读已入库论文，逐篇补字段 |
| 入口 | `upsert_paper()`（**只补空、不覆盖**） | 需要**可刷新**写库（见 §5.3） |
| 落库字段 | `title/authors/abstract/*_obj/...` | `cite_numbers`（①）、`references`（②） |

---

## 2. 关键事实核查（仓库现状 + 外部 API 2026 实测）

### 2.1 学生已有的 prior art（在 `feat/openreview-integration` 分支的缓存里）

- **OpenAlex 缓存**：`oa_resolve::<规范化标题>` → `{id, cited_by_count, counts_by_year, title}`。
- **Semantic Scholar 缓存**：`s2title::<规范化标题>` → `{paperId, citationCount, doi, arxiv, corpusId, dblp, year}`；并有 `s2cites::<paperId>::<date>` → **每条引用的日期列表**。
- **既有的 `cite_numbers` 设计**：一个**时间序列**快照 `["1@2024.10.01", "3@2025.04.01", ..., "14@2026.06.06"]`（`count@date`），是从 S2 的"每条引用日期"重建出来的引用增长曲线。**优点**：保留了时间维度；**不足**：未标注来源（到底是 OA 还是 S2？），单源、口径不可追溯。

### 2.2 "各家引用量不统一" —— 用我们自己的数据实证

> 同一篇论文 ***Instance-dependent Early Stopping*（ICLR 2025）**：
> - **OpenAlex** `cited_by_count = 1`
> - **Semantic Scholar** `citationCount = 14`

**相差 14 倍。** 这正是导师说的"不精确、不统一"。原因（§3.2 详述）是收录范围不同（S2 含 AI 抽取的网络拷贝/预印本，OpenAlex 偏严）。**结论：不要假装能合成一个"真值"，应分源存储。**

### 2.3 🔴 硬阻塞：仓库里没有 PDF 下载 / 正文抽取

- `paper_schema` 里 `local_pdf_path / local_txt_path / local_json_path` 都存在，`processing_status.{pdf_downloaded, txt_extracted}` 也都存在；
- 但**全仓库没有任何代码会写这些字段**——它们永远是空 / `False`。
- 功能② 要"前 N 句/后 N 句"，**必须有正文**。因此功能② 隐含一个**尚未实现的前置阶段**：「PDF 获取 → 正文抽取（OCR/解析）」。**这是功能② 的第一阻塞项**，必须先明确归属与时间表（见 §7-Q5）。

### 2.4 ⚠️ 写库约定冲突：`upsert_paper` 只补空、永不刷新

`data_pipeline/db_ops/paper_repository.py` 的 `upsert_paper` 对同源/异源**都只做 `merge_missing_fields`（补空，不覆盖）**：一旦 `cite_numbers` / `references` 第一次被写成非空，**之后任何 upsert 都不会再刷新它**。这与"被引量要随时间重抓刷新"的诉求直接矛盾。
→ **富化模块必须有自己的写库函数**（按 `_id` 直接 `$set` 覆盖 + `$push edit_logs`），见 §5.3。这一点需要导师认可"富化可以绕开 `upsert_paper` 走独立写库路径"（§7-Q7）。

---

## 3. 功能① 设计：被引量

### 3.1 各数据源对比（2026 现状）

| 数据源 | 取数方式 | 口径特点 | 鉴权/限流（2026） | 定位 |
|---|---|---|---|---|
| **Semantic Scholar** ⭐ | `/graph/v1/paper/search/match?query=<title>`；或精确 `/paper/ARXIV:<id>`、`/paper/DOI:<doi>` | 覆盖最广，**含 AI 抽取的网络拷贝/预印本，数值通常偏高**（≈ OpenAlex 的 1.4–1.9×） | **免 key 可用**（匿名共享池，易 429）；申请免费 key ≈ 1 RPS | **首选**（语义匹配 + 强标识符精确查） |
| **OpenAlex** | `/works/https://doi.org/<doi>`（精确）；`?filter=title.search:<title>`（标题） | 偏严，数值系统性偏低；适合做**对照口径** | **2026-02-13 起强制 API key**；免费层每天 ≈100 credits（仅测试），mailto/polite pool 已废弃 | **对照源 / 兜底** |
| **Crossref** | `/works/<doi>`（取 `is-referenced-by-count`）；`query.bibliographic` | **只数注册 DOI 的入链**，对纯预印本近乎 0；正式期刊口径清晰 | 免费；2025-12-01 收紧限流；带 mailto 进 polite pool | 正式期刊**下界兜底** |
| **Google Scholar** | 无官方 API；`scholarly` 直爬 / SerpAPI 等付费代理 | **数值最高、学界最认**；但**不可复现** | `scholarly` 几次即 CAPTCHA 封 IP；付费服务有额度费用 | **仅当导师明确要求"对齐 GS 口径"时**才上，且走付费服务 |
| Dimensions / Lens | DOI/title 查 times_cited | 与 Crossref 系接近 | 多为申请制/付费 | 可选第四口径，非必需 |

### 3.2 为什么各家不一致（口径差异，不是 bug）

收录范围不同（S2/GS 含网络拷贝与预印本，Crossref 只数注册 DOI 入链）；预印本与正式版**是否合并计数**不同；**自引**是否计入不同；**快照时间**不同。**因此严禁把多家数字相加 / 取平均当"真值"。**

### 3.3 推荐取数链路

```
第一步（消歧优先）：若本库该论文已有强标识符 → 精确 lookup，避免 title 歧义
    arxiv_obj.arxiv_id / arxiv_obj.doi / acl_anthology_obj.doi
    → Semantic Scholar: /paper/ARXIV:<id> 或 /paper/DOI:<doi>
    → OpenAlex:         /works/https://doi.org/<doi>

第二步（无标识符才退化到 title）：
    → S2 /paper/search/match（返回 matchScore）；OpenAlex ?filter=title.search:<title> 取首条
    → 用返回的 year / authors 与本库字段二次校验；低置信度标 low_confidence

兜底链：S2 拿不到 → OpenAlex 对照 → 正式期刊再查 Crossref
特例：导师要"和 Google Scholar 口径对齐" → 才上 SerpAPI 等付费服务（需预算）
```

> ⚠️ **title 两套用法不能混**：查外部 API 用**原始 title**（含大小写标点）以提升匹配率；但**回写定位本库文档**必须用 `paper_id_from_title()`（`normalize_title` 后 SHA1）。
> ⚠️ 仓库的 `normalize_title` 只保留 `[a-z0-9\s]`，会把重音/CJK/希腊字母/连字符/冒号子标题全替成空格——跨语言标题相似度会被系统性拉低，匹配时要注意。
> ⚠️ arXiv 的 DOI（`10.48550/arXiv.*`）在 OpenAlex 常 404；S2 该走 `ARXIV:<id>` 端点而非 DOI 端点。

### 3.4 落库结构建议：`cite_numbers` 存"多源快照表"

不要存单个数字。**保留学生既有的"时间快照"思路，但升级为多源、带来源标注的结构**：

```jsonc
"cite_numbers": [
  {
    "source": "Semantic Scholar",     // 口径来源（关键：解决"不统一"）
    "count": 14,
    "matched_id": "DOI:10.48550/arXiv.2502.07547",  // 命中的强标识符/外部id
    "match_method": "doi",            // doi | arxiv | title
    "match_score": null,              // title 匹配时记 matchScore；强标识符为 null
    "queried_at": "2026-06-13T10:00:00+08:00"
  },
  { "source": "OpenAlex", "count": 1, "matched_id": "W4407425063",
    "match_method": "title", "match_score": 0.98, "queried_at": "2026-06-13T10:00:00+08:00" }
]
```

- **每次刷新 append 一条新快照** → 天然得到"多源 × 时间"的引用增长曲线（兼容学生旧的 `count@date` 直觉，但更可追溯）。
- 这样导师一眼能看到 "OA=1 / S2=14" 的差异，而不是被迫相信某一个数。

### 3.5 函数签名草图

```python
# field_processing_pipeline/enrichers/cite_count_enricher.py
def fetch_cite_count(title: str, ids: dict = None) -> list:
    """
    输入 title（+ 可选强标识符 ids={"doi":..., "arxiv_id":..., "paperId":...}），
    返回可直接写入 cite_numbers 的"多源快照"列表（见 §3.4）；全部失败返回 []。
    顺序：本地缓存 → SemanticScholar(强标识符优先, 否则 title) → OpenAlex → Crossref。
    每次外呼经 rate_limit 退避；命中即写 JSON 缓存（key=normalize_title 或 external_id）。
    """
```

> 🐞 **注意**：调研里一版草图把 `cite_numbers` 的 `$push` 和 `edit_logs` 的 `$push` 写进同一个 dict，后者会**覆盖**前者导致 `cite_numbers` 根本没写入——实现时务必避免（写库统一走 §5.3 的 `update_paper_fields`）。

---

## 4. 功能② 设计：参考文献 + 引用上下文

### 4.1 两条技术路线（必须先选）

| | 路线 A：Semantic Scholar `contexts`（MVP/兜底） | 路线 B：GROBID + 全文（达标版） |
|---|---|---|
| 是否需要 PDF | **否**，一个 HTTP 请求 | **是**（依赖 §2.3 的前置阶段） |
| 能给到什么 | 参考文献条目 ✅ + 每条的"引用本句" ✅ + 引用意图(`intents`) ✅ + 是否重要引用(`isInfluential`) ✅ | 参考文献条目 ✅ + 正文每个引用锚点 ✅ + **二者反向链接** ✅ + **可调 N 句窗口** ✅ |
| **可调 N 句窗口** | ❌ **只给"本句"，拿不到前后 N 句** | ✅ 前 N 句 + 本句 + 后 N 句，N 任意 |
| 覆盖率 | 约 **65–80%**（约 1/4~1/3 的 ref 的 `contexts` 为空） | 取决于 PDF 质量，理论上全覆盖 |
| 部署成本 | **零**（免 key，纯 `requests`） | **重**（Docker/Java 常驻服务，4–8GB 内存） |
| 文本质量 | 有 PDF 抽取噪声（偶尔粘连缺空格） | 由 GROBID 句切，较干净 |

**2026 实测证据（路线 A 可用性）**：实际请求 `GET /graph/v1/paper/<id>/references?fields=contexts,contextsWithIntent,intents,isInfluential`，**HTTP 200、免 key**，返回里 `contexts`（句子级片段）、`contextsWithIntent`、`intents`、`isInfluential` 四字段**全部存在**。覆盖率实测：Attention 78%、BERT 75%、ResNet 66%。**OpenAlex / Crossref 实测都拿不到任何 in-text 上下文**（只有"被引 works 列表"/"参考文献条目"）。

**推荐策略**：**A 先行做 MVP**（零成本快速交一版"参考文献 + 本句上下文 + 引用意图"），**B 作为达标增强层**（要可调 N 窗口、要补齐空缺）。两层用 reference 的 title/外部 id 对齐合并。**但要让导师知道：纯 A 不满足"可调 N 句窗口"，最终达标必须上 B。**（§7-Q4）

### 4.2 为什么 GROBID 是路线 B 的核心

GROBID 是**唯一在一次 `processFulltextDocument` 调用里同时输出**：(a) 结构化参考文献条目 `<biblStruct xml:id="b2">`、(b) 正文里的 in-text 引用标记 `<ref type="bibr" target="#b2">`（**天然带 `target` 反向链接**）、(c) 句子切分 `<s>`（`segmentSentences=true`）的开源工具。这正好对应导师 JSON 的：`bibID`（= `xml:id` 去掉 `#`）、`inTextCitation`（每个 `<ref>` 的可见文本）、`times`（同一 `target` 出现次数）。数字制 `[1]` 与作者年制 `(Aho, 2007)` **都**被标成 `<ref type="bibr">`，统一处理。

> 备选：science-parse（引用提及→bib 链接，但只给单句、维护停滞）；或 Docling/marker 拿结构化全文 + AnyStyle/refextract 解析条目，再自写"in-text↔bib"匹配。GROBID/CERMINE/science-parse 是 Apache-2.0。

### 4.3 核心算法（路线 B 的窗口生成）

三步流水线：

```
(1) 句子切分：把正文切成"带字符偏移的句子数组"
    sentences[i] = (text, char_start, char_end, section)
    工具首选 PySBD(clean=False, char_span=True)：对学术文本鲁棒
      —— 正确处理 et al. / e.g. / i.e. / Fig. 3 / 小数 0.5 / 版本 v2.，
         且不把 (Aho, 2007). 里的句点误当句末；char_span=True 直接给偏移。
    （clean=True 与 char_span 互斥，必须 clean=False）

(2) in-text 引用识别 + 回链到具体参考文献条目
    数字制 [12]/上标：按编号对齐 references[n]（编号必须在 references 里找得到，
        否则不计——避免 [2018]/[0,1] 误报）
    作者年制 (Allam, 2024)/Allam (2024)：按"第一作者姓(unidecode 去重音+小写)+年份"建索引匹配
    成组引用 (Zhangsan 2021, Aho 2007) / [3,5,7] / [3-6]：拆成多个独立引用分别回链
        （它们共享同一所在句、窗口相同，但 times 各自计数）
    GROBID 路径下：直接用 <ref target="#b2"> 的 target 回链，最稳

(3) 窗口计算（任意 N，O(N) 现算）
    把引用的字符偏移二分定位到所在句下标 sidx
    context(N) = sentences[sidx-N : sidx+N+1] 拼接
```

> **工程铁律**：**只持久化"句子数组 + 每个引用的 (句下标, 字符偏移)"作为单一真相源**，`windows_N` 在读取时现算。绝不为每个 N 物化进库——否则 N 一变就得重算、且历史数据出现"有的有 `windows_3` 有的没有"的不一致。

### 4.4 改进后的输出 JSON 设计（回应导师"一起设计更好的"）

#### 4.4.1 对导师两版的逐点评析

| 导师设计 | 问题 | 改进 |
|---|---|---|
| 外层 key = 随机串 `"4324sfdajdr..."` | 不可复现、跑一次变一次，无法幂等/去重/追溯；又和 value 里的 `bibID` 重复成两套 id | 外层用**可复现稳定 id** `ref_id = sha1(citing_paper_id + ":" + bib_id)[:16]`；单篇内保留 `bib_id` 当 GROBID 锚点 |
| `windows_1` / `windows_2` 为每个 N 预存 | **冗余**（`windows_2` 含 `windows_1`）、**不可扩展**（要 N=3 就得重抽）、把"渲染结果"当存储 | **只存 `sentence_index` + `char_span`**，任意 N 现算；`windows_N` 退化为读取层视图 |
| `inTextCitation: ["Aho, 2007)", ...]` | `"Aho, 2007)"` 带半个括号（脏数据）；和 `inTextContent` 的 `"1"/"2"` 靠"下标顺序"隐含对齐，极脆 | 每次出现做成一个 **`occurrence` 对象**，`matched_text`(清洗后)/`char_span`/`sentence_index`/`section` 挂在一起 |
| `inTextContent` 内层 `"1"/"2"` 字符串 key | 用字符串数字 key 模拟数组，丢失有序性、不能 `len`/`slice` | 用 **`occurrences` 数组**，第 k 次出现 = `occurrences[k-1]` |
| `times` | 纯派生量（= `len(occurrences)`），存它会引入不一致风险 | **不入库**，读取时 `len` 现算 |
| 命名 `Title/PubYear` vs `bibID/inTextCitation` 大小写混乱 | 与仓库 `snake_case`（`arxiv_obj`/`cite_numbers`）不一致 | 统一 **snake_case** |
| 缺 `section` / 定位 / 匹配置信度 / 外部 id / 引用样式 | 无法做引用意图分析、无法回溯高亮、错链会静默写入 | 补 `section` / `char_span` / `match_confidence` / `ids{doi,arxiv,s2,openalex}` / `citation_style` |

#### 4.4.2 改进结构（带注释）

```jsonc
// A. paper 级新增：句子真相源（全篇只存一份，供任意 N 现算窗口 + 回原文高亮/校验）
//    体量较大，建议落 cache/ 或单列字段，不必塞进每条 reference。
"body_sentences": [
  { "s_idx": 12, "text": "We build on prior work (Zhangsan 2021, Aho, 2007).",
    "char_start": 1044, "char_end": 1094, "section": "1 Introduction" }
  // ... 全篇句子，顺序即文档顺序
],

// B. references：list，每个元素是一条参考文献的"富对象"（与 paper_schema.references=[] 对齐）
"references": [
  {
    "ref_id": "a1b2c3d4e5f60718",   // 稳定可复现 = sha1(citing_paper_id+":"+bib_id)[:16]
    "bib_id": "b2",                  // GROBID <biblStruct xml:id="b2">，单篇内锚点
    "raw": "Alfred V Aho. 2007. Compilers: principles, techniques and tools. Pearson Education India.",
    "parsed": {
      "title": "Compilers: principles, techniques and tools",
      "year": "2007", "authors": ["Alfred V Aho"],
      "first_author_surname": "aho",  // unidecode+小写，作者年制回链键
      "venue": "Pearson Education India"
    },
    "ids": { "doi": "", "arxiv": "", "s2": "", "openalex": "" }, // 和功能①打通
    "linked_paper_id": "",            // 若被引文献也在本库，回填其 _id → 形成引用图
    "citation_style": "author_year",  // author_year | numeric
    "extractor": "grobid",            // grobid | s2_api | regex_fallback
    "occurrences": [                  // 第 k 次出现 = occurrences[k-1]；times = len(occurrences)
      {
        "occ_id": 1,
        "section": "3 Method",
        "sentence_index": 27,         // 指向 body_sentences[*].s_idx
        "char_span": [2355, 2366],
        "matched_text": "(Aho, 2007)",// 清洗后的命中文本
        "match_method": "grobid_target", // grobid_target | numeric | author_year
        "match_confidence": 1.0,
        "ambiguous": false
        // 窗口不存：读取时 body_sentences[27-N : 27+N+1] 现算
      }
    ]
  }
]
```

#### 4.4.3 完整示例（导师的 Aho / Allam 例子）

```jsonc
{
  "body_sentences": [
    { "s_idx": 26, "text": "Our pipeline lexes, parses and emits intermediate representation.", "char_start": 2250, "char_end": 2314, "section": "3 Method" },
    { "s_idx": 27, "text": "Our compiler reuses classic techniques (Aho, 2007).",            "char_start": 2315, "char_end": 2366, "section": "3 Method" },
    { "s_idx": 28, "text": "We then extend them to a neural setting.",                        "char_start": 2367, "char_end": 2407, "section": "3 Method" },
    { "s_idx": 11, "text": "Modern code generation systems must respect language semantics.","char_start": 980,  "char_end": 1043, "section": "1 Introduction" },
    { "s_idx": 12, "text": "We build on prior work (Zhangsan 2021, Aho, 2007).",             "char_start": 1044, "char_end": 1094, "section": "1 Introduction" },
    { "s_idx": 13, "text": "These foundations shape our compiler design.",                   "char_start": 1095, "char_end": 1139, "section": "1 Introduction" }
  ],
  "references": [
    {
      "ref_id": "a1b2c3d4e5f60718",
      "bib_id": "b2",
      "raw": "Alfred V Aho. 2007. Compilers: principles, techniques and tools. Pearson Education India.",
      "parsed": { "title": "Compilers: principles, techniques and tools", "year": "2007",
                  "authors": ["Alfred V Aho"], "first_author_surname": "aho", "venue": "Pearson Education India" },
      "ids": { "doi": "", "arxiv": "", "s2": "", "openalex": "" },
      "linked_paper_id": "",
      "citation_style": "author_year",
      "extractor": "grobid",
      "occurrences": [
        { "occ_id": 1, "section": "1 Introduction", "sentence_index": 12, "char_span": [1067, 1093],
          "matched_text": "(Zhangsan 2021, Aho, 2007)", "match_method": "grobid_target", "match_confidence": 1.0, "ambiguous": false },
        { "occ_id": 2, "section": "3 Method",       "sentence_index": 27, "char_span": [2355, 2366],
          "matched_text": "(Aho, 2007)", "match_method": "grobid_target", "match_confidence": 1.0, "ambiguous": false }
      ]
    }
  ]
}
```

读取时，`N=1` 对第 2 次出现（`sentence_index=27`）现算窗口 = `body_sentences[26..28]` 拼接：
*"Our pipeline lexes... · Our compiler reuses classic techniques (Aho, 2007). · We then extend them to a neural setting."* —— 即导师要的 3 句。

#### 4.4.4 与 `paper_schema.references` 的对齐

- **首选**：让 `paper["references"]` 列表的每个元素**就是上面的富对象**（零顶层字段新增，下游 `find_papers_with_non_empty_fields(["references"])` 不用改）。
- `body_sentences` 体量大、与"被引量/标签"无关 → **落 `cache/` 或单列**，不塞进每条 reference。
- ⚠️ `init_indexes` 已建 `references.title` 索引——它**期望 references 是对象数组**（不是导师那种"以 ref_id 为 key 的 dict"）。本设计的 `references` 是**对象数组**，与索引一致；但富对象里 title 在 `parsed.title`，需把索引改成 `references.parsed.title`，或在富对象里冗余一个顶层 `title`。**此点需确认（§7-Q3）。**

---

## 5. 模块设计：`field_processing_pipeline/`

### 5.1 目录树（每文件一句话职责）

```
field_processing_pipeline/
├── __init__.py
├── base.py                      # 富化层抽象基类 BaseEnricher：契约 process(paper)->set_fields（语义是"逐篇处理"非"流式采集"）
│
├── db_ops/
│   └── field_writer.py          # 富化层【专属写库】update_paper_fields(...)：按 _id 直接 $set 覆盖 + $push edit_logs + 置 status flag
│
├── configs/
│   ├── cite_count_config.py     # 功能①：API 优先级 [SS, OpenAlex, Crossref]、base_url、key 占位、限流、缓存目录、匹配阈值
│   └── reference_config.py      # 功能②：GROBID server_url、consolidate 开关、PySBD 语言、默认 window_n、缓存目录
│
├── enrichers/
│   └── cite_count_enricher.py   # 功能①主力 fetch_cite_count(title, ids)：SS 首选 + OpenAlex/Crossref 兜底，归一化为 cite_numbers 快照
│
├── extractors/
│   ├── pdf_provider.py          # 🔴前置占位 ensure_local_pdf(paper)：按 base_urls 下载 PDF，回填 local_pdf_path + status.pdf_downloaded
│   ├── text_extractor.py        # 🔴前置占位 ensure_local_txt(paper)：PDF→正文 .txt，回填 local_txt_path + status.txt_extracted
│   ├── grobid_client.py         # 封装 GROBID HTTP：processFulltextDocument(pdf)->TEI（重试/超时/健康检查）
│   ├── tei_parser.py            # 解析 TEI：<listBibl> 条目 + 正文 <ref type=bibr> 锚点及其 target/所在句/章节
│   ├── sentence_splitter.py     # PySBD 封装 split(text)->[(text,start,end)]（clean=False, char_span=True）
│   ├── s2_context_provider.py   # 路线A：S2 references?fields=contexts,...（MVP/兜底，免 key，仅"本句"）
│   └── reference_extractor.py   # 功能②主力 extract_references_with_context(paper, window_n)：组合上面各件，产出 references 富对象
│
├── api_clients/
│   ├── semantic_scholar.py      # SS Graph API：by title / paperId / DOI / ARXIV，取 citationCount + references(contexts)
│   ├── openalex.py              # OpenAlex：取 cited_by_count（需 api_key）
│   └── crossref.py              # Crossref：取 is-referenced-by-count（DOI 优先，带 mailto）
│
├── cache/
│   ├── json_cache.py            # 通用 JSON 文件缓存 get/set，key=normalize_title 或 external_id（仿学生既有缓存做法）
│   └── store/                   # 落盘目录（.gitignore）：store/semantic_scholar/*.json、store/grobid_tei/*.xml
│
├── pipelines/
│   ├── cite_count_pipeline.py   # 功能①批处理编排：选论文→fetch_cite_count→update_paper_fields；幂等/续跑/限流退避
│   └── reference_pipeline.py    # 功能②批处理编排：选论文→ensure pdf/txt→extract→update_paper_fields（闸门 references_extracted）
│
├── scripts_py/
│   ├── enrich_cite_count.py     # 功能①命令行入口（argparse）
│   └── extract_references.py    # 功能②命令行入口（argparse）
│
└── utils/
    ├── rate_limit.py            # 限流 + 指数退避 + 429/5xx 重试装饰器（api_clients / grobid 复用）
    └── id_utils.py              # 外部 id 归一化（DOI/arXiv 清洗），供缓存 key 与查询复用
```

> **复用而非重写**：`MongoDBClient`、`paper_query` 的 read 函数、`normalize_title`/`paper_id_from_title`、`now_beijing_iso`、`DEFAULT_PAPER_FIELDS`/`CURRENT_SCHEMA_VERSION` 全部从 `ai4research.data_pipeline...` 直接 import。

### 5.2 数据流（读 → 处理 → 写回）

**功能①（纯 API，无需 PDF）**
```
选论文：find_papers_by_field_value("accepted_by"/"seen_in_sources", ...) / get_paper_by_id / 全量游标
        （非 --refresh 时 skip 已有非空 cite_numbers 的文档）
处理  ：fetch_cite_count(title, ids) —— cache → SS → OpenAlex → Crossref
写回  ：update_paper_fields(_id, {"cite_numbers": [...]}, op="enrich cite_numbers", status_flag=None)
```

**功能②（需全文）**
```
选论文：同上 +（非 --force 时 skip processing_status.references_extracted==True）
前置  ：ensure_local_pdf(paper) → ensure_local_txt(paper)   🔴 当前仓库缺失，硬阻塞
处理  ：extract_references_with_context(paper, window_n)
        路线A：s2_context_provider（本句）；路线B：grobid_client→tei_parser→sentence_splitter→组窗
写回  ：update_paper_fields(_id, {"references":[...]}, op="extract references+contexts",
                            status_flag="references_extracted")
```

### 5.3 新写库函数 `update_paper_fields`（核心，①②共用）

```python
# field_processing_pipeline/db_ops/field_writer.py
def update_paper_fields(paper_id, set_fields: dict, op: str, detail: str = "",
                        status_flag: str = None, require_exists: bool = True) -> bool:
    """
    富化层专属写库（与 upsert_paper 分家：这里允许覆盖刷新 cite_numbers/references）。
    实现要点：
      1) 先 find_one({"_id": paper_id}) 判存在；require_exists 且不存在 → 告警 return False（富化不新建论文）
      2) set_fields 支持点路径（"cite_numbers" / "references" / 嵌套）
      3) status_flag 不空 → 并入 {"processing_status.<flag>": True}
      4) edit_log = {"time": now_beijing_iso(), "op": op, "detail": detail}；$push 到 edit_logs
      5) update_one(..., {"$set":{...}, "$push":{"edit_logs":edit_log}}, upsert=False)
      6) 不碰 seen_in_sources / seen_in_categories
    幂等闸门在 pipeline 层判（本函数被调用即代表已决定要写/刷新）。
    """
```

### 5.4 `paper_schema` 改动（最小）

- `references: []` —— **复用，不改结构**；约定每条 ref 为 §4.4.2 的富对象（内嵌 `occurrences`）。
- `cite_numbers: []` —— **复用**，按 §3.4 写入快照对象。
- `processing_status.{references_extracted, pdf_downloaded, txt_extracted}` —— **已存在，直接置位**。
- `body_sentences` —— **不建议进 Mongo**（体量大、中间产物），落 `cache/`；若确需再单列。
- **版本号**：未改字段结构，可暂不 bump `CURRENT_SCHEMA_VERSION`；建议先在 `references`/`cite_numbers` 行补注释说明子结构契约，待功能② 稳定后统一升 v2 并跑一次 `migrate_schema()`（现逻辑只补缺失顶层字段，对老数据无破坏）。

### 5.5 命令行入口 + 文档

```
# python -m ai4research.field_processing_pipeline.scripts_py.enrich_cite_count
--accepted-by / --source / --id / --limit / --refresh / --sleep

# python -m ai4research.field_processing_pipeline.scripts_py.extract_references
--accepted-by / --source / --id / --limit / --window-n(默认2) / --force / --sleep
```
两入口沿用现有模板：先 `MongoDBClient.ping()` + `print("✅ MongoDB connected")`，再调 pipeline。

**`scripts_md/` 续接（仿 0–8 风格）**：
- `9_enrich_cite_count_by_API.md` —— 功能① 用法、多源说明、`--refresh` 刷新。
- `10_extract_references_with_context.md` —— 功能② 用法、`--window-n`、**显式标注硬前置**（需 `local_pdf_path`/`local_txt_path`）、GROBID/PySBD 依赖。
- `11_prepare_pdf_and_text.md` —— 前置占位阶段（`ensure_local_pdf`/`ensure_local_txt`）说明，明确"此阶段落地前功能② 不可端到端运行"。

**`requirements.txt` 增补**：`pysbd`；GROBID 走 `grobid-client-python` 或自封 `requests`；SS/OpenAlex/Crossref 复用现有 `requests` 无需新依赖。

---

## 6. 实施路线图（里程碑）

| 里程碑 | 内容 | 依赖 | 产出 |
|---|---|---|---|
| **M0** | 脚手架：建模块骨架 + `update_paper_fields` + `json_cache` + `rate_limit` | 无 | 可写库、可缓存 |
| **M1** | 功能① **MVP**：单源 Semantic Scholar（强标识符优先 + title 兜底），写 `cite_numbers` | M0 | `enrich_cite_count` 可跑单篇 |
| **M2** | 功能① **多源**：+ OpenAlex/Crossref 对照、缓存、批处理（幂等/续跑/限流） | M1 | 全库可跑，多源快照表 |
| **M3** | 功能② **MVP（路线A）**：S2 `contexts` → 参考文献 + 本句上下文 + 引用意图，写 `references` | M0 | 零部署交一版（**仅本句，不可调 N**） |
| **M4** | 🔴 **前置阶段**：PDF 下载 + 正文抽取（`ensure_local_pdf`/`ensure_local_txt`） | 归属待定（§7-Q5） | `local_pdf_path`/`local_txt_path` 被填 |
| **M5** | 功能② **达标（路线B）**：GROBID + PySBD + 回链 + **可调 N 句窗口**，按 §4.4 落库 | M4 + GROBID 服务 | 完整满足导师需求 |
| **M6** | 引用图富化：`ids`/`linked_paper_id` 把被引文献映射回本库，打通功能①②️ | M2 + M5 | 论文引用图（谁引了谁） |

> 建议节奏：**M0→M1→M3 先快速出可演示成果**（一周内可见东西）；M2 完善功能①；M4/M5 是功能② 真正达标的"重活"，**取决于 PDF→正文阶段的归属与 GROBID 部署决策**。

---

## 7. 待导师拍板的开放问题

1. **被引量要"一个权威数字"还是"多源快照表"？** 若要一个数，以哪家为准（SS/OpenAlex/Crossref/GS）？是否必须**对齐 Google Scholar 口径**（若是，需 SerpAPI 等付费服务 + 预算）？
   *（我的建议：多源并存、分源留痕、记 `queried_at`——正好回应"不统一"的痛点。）*
2. **上下文窗口**确认是"引用方说的话"（已据此设计）；再确认：窗口**能否跨小标题**、能否溢进 References/Acknowledgments 区？（建议：先剥离参考文献节后只在正文切句，窗口不跨章节边界。）
3. **`references` 落库形状**：用对象数组（与现有 `references.title` 索引对齐，但富对象里 title 在 `parsed.title`，索引要改成 `references.parsed.title` 或冗余顶层 title）？外层 id 用 `ref_id`（跨论文稳定）确认 OK？
4. **功能② 里程碑**：是否接受**先交路线 A 的 MVP**（参考文献 + **本句**上下文，无可调 N）作为阶段成果，再上 GROBID 做达标版？还是必须一步到位上 GROBID？
5. 🔴 **PDF 下载 + 正文/OCR 抽取这个前置阶段是不是本任务范围？** 若不是，**谁负责、何时就绪**？这是功能② 的硬阻塞。
6. **批处理规模**：库里现在多少篇、目标处理多少篇？是否允许引入 OpenAlex/SS 的**付费/申请 API key**（放配置不硬编码）？是否需要断点续跑/失败重试（建议需要）？
7. **刷新策略**：允许 `field_processing` **绕开 `upsert_paper` 直接 `$set` 写库**吗（`update_paper_fields`）？还是给 `upsert` 加一条 `force-overwrite` 路径以保持架构统一？
8. **GROBID 运维**：谁来起 Docker、有无 GPU/内存预算、放本机还是单独部署？`consolidateCitations`（联网对齐 DOI，慢、外呼 CrossRef）是否开启？

---

## 8. 风险与高频坑（精选）

- **title 消歧极易出错**：同名/改名/会议版 vs 期刊版 vs arXiv 版会命中不同记录 → 强标识符优先，title 仅兜底，并用 year/authors 二次校验；低置信度标 `low_confidence` 而非静默写入。
- **各源引用量天然不一致**（口径差异，非 bug）→ 严禁相加/取平均当真值，分源存 + 记 `queried_at`。
- **2026 API 现实约束会撞墙**：OpenAlex 强制 key（免费层每天 ≈100 credits）；SS 免 key 是共享池，批量必 429；Crossref 收紧限流 → 批处理必须 1 RPS + 退避重试 + 断点续跑，否则半路全挂。
- **作者年制回链是准确率天花板**：同姓同年要 a/b 消歧、et al. 只能取首作者姓、成组引用必须拆开、叙述式 `Allam (2024) showed` 要把"作者+紧随 (year)"当一个单元；匹配不唯一时返回候选并标 `ambiguous`，**不要静默取第一个**。
- **数字制假阳性**：`[2018]`（年份误当编号）、`[0,1]`（区间）、`[i]`（列表项）——编号必须能在 references 找到对应条目才计为引用。
- **上标数字制在纯 txt 里基本丢失**：PDF→txt 后上标贴成 `method.12` → 纯 txt 场景对上标降级并标 `low_confidence`；要可靠就得用带格式来源（GROBID/HTML）。
- **句子切分在公式/缩写/小数/版本号处会切错** → 用 PySBD(`clean=False, char_span=True`) 并补缩写白名单；窗口要先剥离 References/Acknowledgments。
- **GROBID 的 `ref/@target` 可能为空或指向不存在的 `xml:id`** → 解析时判 `target in bib`，漏链的引用进 `unmatched` 而非丢弃或 KeyError。
- **非英文姓的归一化**：只删非 ASCII 会把 `Müller→mller`、`Łukasz→ukasz` → 用 `unidecode` 去重音而非直接删。

---

### 附：本规划的调研依据

- 仓库实读：`paper_schema.py`、`paper_repository.py`(`upsert_paper`/`merge_missing_fields`)、`paper_query.py`、`text_utils.py`、`base.py`、`acl_anthology_crawler.py`、`mongo_client.py`、`README.md`、`scripts_md/0-8`。
- prior art：`feat/openreview-integration` 分支 `openreview_vault/.cache/{openalex,semanticscholar}.json` 与样例画像 `P42DbV2nuV.json`。
- 外部 API 2026 实测：Semantic Scholar Graph API（`/paper/search/match`、`/paper/{id}/references?fields=contexts,...` 免 key 200）、OpenAlex Works（强制 key、DOI lookup）、Crossref（`is-referenced-by-count`）；GROBID/PySBD 工具能力调研。
