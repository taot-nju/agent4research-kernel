"""
解析 GROBID 的 TEI XML，产出：
  - references[]        每条参考文献的富对象（含 occurrences：正文每次被引处）
  - body_sentences[]    正文按句切分的有序数组（带运行字符偏移 + 章节），窗口的真相源
  - unmatched_citations[]  正文里 @target 缺失/悬空（GROBID 没链到某条 bib）的引用，不丢弃

设计要点（对齐 field_processing_pipeline/PLAN.md §4.4）：
  - ref_id = sha1(paper_id + ':' + bib_id)[:16]，稳定可复现（取代随机外层 key）
  - 不预存 windows_N；不存 times（= len(occurrences)）
  - 悬空 @target -> unmatched_citations（绝不 KeyError，绝不静默丢）
  - 跳过 References / Bibliography / Acknowledgments / Appendix 章节的句子
"""

import hashlib
import re

from lxml import etree
from unidecode import unidecode

from ai4research.field_processing_pipeline.configs.reference_config import (
    REFERENCES_HEAD_RE,
)

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

_WS_RE = re.compile(r"\s+")


def _norm_ws(text: str) -> str:
    return _WS_RE.sub(" ", (text or "")).strip()


def _clean_marker(text: str) -> str:
    """清洗 in-text 引用文本：去多余空白，去掉落单的半个括号（GROBID 常见脏数据）。"""
    t = _norm_ws(text)
    if t.endswith(")") and "(" not in t:
        t = t[:-1].rstrip()
    if t.startswith("(") and ")" not in t:
        t = t[1:].lstrip()
    # 去掉分组引用切分后落在两端的分隔符（如 "Ying et al., 2019;" -> "Ying et al., 2019"）
    t = t.strip(" ;,")
    return t


def _ref_id(paper_id: str, bib_id: str) -> str:
    return hashlib.sha1(f"{paper_id}:{bib_id}".encode("utf-8")).hexdigest()[:16]


def _text_of(el) -> str:
    return _norm_ws("".join(el.itertext())) if el is not None else ""


def _first_author_surname(authors_persname_els) -> str:
    if not authors_persname_els:
        return ""
    surname = authors_persname_els[0].find("tei:surname", TEI_NS)
    if surname is not None and (surname.text or "").strip():
        return unidecode(surname.text.strip()).lower()
    return ""


def _parse_biblstruct(b, paper_id: str, idx: int) -> dict:
    bib_id = b.get(XML_ID) or f"idx{idx}"

    raw_note = b.find(".//tei:note[@type='raw_reference']", TEI_NS)
    raw = _text_of(raw_note)

    # 注意：不能用 `a or b`，lxml element 的真值测试基于子元素数量，会误判（FutureWarning）。
    title_el = b.find(".//tei:title[@level='a']", TEI_NS)
    if title_el is None:
        title_el = b.find(".//tei:title[@level='m']", TEI_NS)
    if title_el is None:
        title_el = b.find(".//tei:title", TEI_NS)
    title = _text_of(title_el)

    date_el = b.find(".//tei:date", TEI_NS)
    year = ""
    if date_el is not None:
        when = date_el.get("when") or _text_of(date_el)
        m = re.search(r"\d{4}", when or "")
        year = m.group(0) if m else ""

    persnames = b.findall(".//tei:author//tei:persName", TEI_NS)
    authors = []
    for pn in persnames:
        forenames = [f.text.strip() for f in pn.findall("tei:forename", TEI_NS) if (f.text or "").strip()]
        surname = pn.find("tei:surname", TEI_NS)
        full = " ".join(forenames + ([surname.text.strip()] if surname is not None and (surname.text or "").strip() else []))
        if full:
            authors.append(full)

    doi_el = b.find(".//tei:idno[@type='DOI']", TEI_NS)
    doi = _text_of(doi_el)

    return {
        "ref_id": _ref_id(paper_id, bib_id),
        "bib_id": bib_id,
        "title": title,  # 顶层冗余一份，兼容现有 references.title 索引
        "raw": raw,
        "parsed": {
            "title": title,
            "year": year,
            "authors": authors,
            "first_author_surname": _first_author_surname(persnames),
            "doi": doi,
        },
        "extractor": "grobid",
        "occurrences": [],
    }


def _nearest_section(s_el) -> str:
    """向上找最近的 <div>，取其直接子 <head> 文本作为章节名。"""
    node = s_el.getparent()
    while node is not None:
        if node.tag == f"{{{TEI_NS['tei']}}}div":
            head = node.find("tei:head", TEI_NS)
            if head is not None:
                return _text_of(head)
        node = node.getparent()
    return ""


def parse_tei(tei: str, paper_id: str) -> dict:
    root = etree.fromstring(tei.encode("utf-8") if isinstance(tei, str) else tei)

    # ---- (a) 参考文献条目（全部，无论是否被正文引用） ----
    biblstructs = root.findall(".//tei:listBibl/tei:biblStruct", TEI_NS)
    refs = []
    ref_by_bibid = {}
    for i, b in enumerate(biblstructs):
        ref = _parse_biblstruct(b, paper_id, i)
        refs.append(ref)
        ref_by_bibid[ref["bib_id"]] = ref

    # ---- (b) 正文句子 + (c) in-text 引用回链，单趟文档顺序遍历 ----
    body = root.find(".//tei:body", TEI_NS)
    body_sentences = []
    unmatched = []
    occ_counter = {}  # ref_id -> 已分配的 occ_id 数

    if body is not None:
        cursor = 0
        s_idx = 0
        for s in body.findall(".//tei:p/tei:s", TEI_NS):
            section = _nearest_section(s)
            if REFERENCES_HEAD_RE.match(section or ""):
                continue  # 跳过参考文献/致谢/附录章节

            text = _norm_ws("".join(s.itertext()))
            char_start = cursor
            char_end = char_start + len(text)
            body_sentences.append({
                "s_idx": s_idx,
                "text": text,
                "char_start": char_start,
                "char_end": char_end,
                "section": section,
            })

            search_pos = 0
            for ref in s.findall(".//tei:ref[@type='bibr']", TEI_NS):
                matched_text = _clean_marker("".join(ref.itertext()))
                # 在归一化后的句子文本里定位（按出现顺序，支持同句多次）
                off = text.find(matched_text, search_pos) if matched_text else -1
                if off >= 0:
                    span = [char_start + off, char_start + off + len(matched_text)]
                    search_pos = off + max(1, len(matched_text))
                else:
                    span = [char_start, char_end]

                target = (ref.get("target") or "").lstrip("#")
                if target and target in ref_by_bibid:
                    rid = ref_by_bibid[target]["ref_id"]
                    occ_counter[rid] = occ_counter.get(rid, 0) + 1
                    ref_by_bibid[target]["occurrences"].append({
                        "occ_id": occ_counter[rid],
                        "section": section,
                        "sentence_index": s_idx,
                        "char_span": span,
                        "matched_text": matched_text,
                        "match_method": "grobid_target",
                        "match_confidence": 1.0,
                        "ambiguous": False,
                    })
                else:
                    # @target 缺失或指向不存在的 xml:id —— 不丢，进 unmatched
                    unmatched.append({
                        "raw_target": ref.get("target") or "",
                        "matched_text": matched_text,
                        "section": section,
                        "sentence_index": s_idx,
                        "char_span": span,
                    })

            cursor = char_end + 1
            s_idx += 1

    return {
        "references": refs,
        "body_sentences": body_sentences,
        "unmatched_citations": unmatched,
    }


def summarize(parsed: dict) -> dict:
    """统计信息，便于日志/质检（不入库）。"""
    refs = parsed["references"]
    n_occ = sum(len(r["occurrences"]) for r in refs)
    n_cited = sum(1 for r in refs if r["occurrences"])
    return {
        "n_refs": len(refs),
        "n_cited_refs": n_cited,
        "n_occurrences": n_occ,
        "n_sentences": len(parsed["body_sentences"]),
        "n_unmatched": len(parsed["unmatched_citations"]),
    }
