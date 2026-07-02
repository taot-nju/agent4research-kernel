"""从真实 topic workflow 与 hybrid JSON 生成可核查的 Markdown evidence dossier。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "读取 process_research_topic workflow JSON 与 "
            "search_topic_hybrid JSON，生成带论文标题、排名、"
            "页码、section 和 evidence 文本的 Markdown dossier。"
            "本工具不调用 LLM，也不自动生成未经证据支持的结论。"
        )
    )
    parser.add_argument(
        "--topic-workflow-json",
        required=True,
        help="process_research_topic --save-json 的 workflow JSON 路径",
    )
    parser.add_argument(
        "--hybrid-result-json",
        required=True,
        help="search_topic_hybrid --save-json 的 hybrid JSON 路径",
    )
    parser.add_argument(
        "--output-md",
        required=True,
        help="输出 Markdown dossier 路径",
    )
    parser.add_argument(
        "--top-papers",
        type=int,
        default=5,
        help="写入前多少篇论文，默认 5",
    )
    parser.add_argument(
        "--evidence-per-source",
        type=int,
        default=1,
        help="每篇论文、每个检索来源写入多少条 evidence，默认 1",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=600,
        help="每条 evidence 文本预览字符数，默认 600",
    )
    return parser


def _load_json(path: str) -> tuple[Path, dict[str, Any]]:
    resolved = Path(path).expanduser().resolve()
    data = json.loads(resolved.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError(
            f"JSON 必须是 object: {resolved}"
        )

    return resolved, data


def _clean_text(
    text: str,
    limit: int,
) -> str:
    normalized = " ".join(text.split())

    if len(normalized) <= limit:
        return normalized

    return normalized[:limit] + "..."


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace(
        "\n",
        " ",
    )


def _title_map(
    workflow: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    outcomes = workflow.get("outcomes")

    if not isinstance(outcomes, list):
        raise ValueError(
            "workflow JSON 缺少 outcomes list"
        )

    return {
        str(outcome.get("paper_id", "")): outcome
        for outcome in outcomes
        if isinstance(outcome, dict)
        and str(outcome.get("paper_id", ""))
    }


def _source_evidence(
    wrapper: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    source = str(wrapper.get("source", "")).strip()
    source_hit = wrapper.get("hit", {})

    if not isinstance(source_hit, dict):
        source_hit = {}

    evidence = source_hit.get("evidence", [])

    if not isinstance(evidence, list):
        evidence = []

    return source or "unknown", [
        item
        for item in evidence
        if isinstance(item, dict)
    ]


def build_dossier_markdown(
    *,
    workflow_path: Path,
    workflow: dict[str, Any],
    hybrid_path: Path,
    hybrid: dict[str, Any],
    top_papers: int,
    evidence_per_source: int,
    preview_chars: int,
) -> str:
    if top_papers <= 0:
        raise ValueError("top_papers 必须大于 0")

    if evidence_per_source <= 0:
        raise ValueError(
            "evidence_per_source 必须大于 0"
        )

    if preview_chars <= 0:
        raise ValueError(
            "preview_chars 必须大于 0"
        )

    workflow_topic = str(
        workflow.get("topic", "")
    ).strip()

    if not workflow_topic:
        raise ValueError("workflow JSON 缺少 topic")

    query = str(hybrid.get("query", "")).strip()

    if not query:
        raise ValueError("hybrid JSON 缺少 query")

    paper_result = hybrid.get(
        "paper_search_result",
    )

    if not isinstance(paper_result, dict):
        raise ValueError(
            "hybrid JSON 缺少 paper_search_result"
        )

    hits = paper_result.get("hits")

    if not isinstance(hits, list):
        raise ValueError(
            "hybrid JSON 缺少 paper_search_result.hits"
        )

    titles = _title_map(workflow)
    execution = hybrid.get("hybrid_execution", {})

    if not isinstance(execution, dict):
        execution = {}

    lines = [
        "# Topic Evidence Dossier",
        "",
        "## Scope",
        "",
        f"- Workflow topic: `{workflow_topic}`",
        f"- Retrieval query: `{query}`",
        f"- Workflow JSON: `{workflow_path}`",
        f"- Hybrid JSON: `{hybrid_path}`",
        f"- Strategy: `{execution.get('strategy', 'unknown')}`",
        (
            "- Fusion weights: "
            f"BM25={execution.get('bm25_weight', 'unknown')}; "
            f"bge-m3={execution.get('vector_weight', 'unknown')}"
        ),
        (
            "- Evidence policy: this dossier reports retrieved "
            "source text and metadata; it does not infer unsupported "
            "mechanisms, claims, or limitations."
        ),
        "",
        "## Ranked Paper Overview",
        "",
        "| rank | paper | hybrid score | BM25 evidence section | bge-m3 evidence section |",
        "|---:|---|---:|---|---|",
    ]

    selected_hits = [
        hit
        for hit in hits[:top_papers]
        if isinstance(hit, dict)
    ]

    for hit in selected_hits:
        paper_id = str(hit.get("paper_id", ""))
        outcome = titles.get(paper_id, {})
        title = str(outcome.get("title", paper_id))
        sections: dict[str, str] = {}

        wrappers = hit.get("evidence", [])

        if not isinstance(wrappers, list):
            wrappers = []

        for wrapper in wrappers:
            if not isinstance(wrapper, dict):
                continue

            source, evidence_items = _source_evidence(wrapper)

            if not evidence_items:
                continue

            chunk = evidence_items[0].get("chunk", {})

            if not isinstance(chunk, dict):
                continue

            section_path = chunk.get("section_path", [])

            if isinstance(section_path, list):
                sections[source] = " > ".join(
                    str(item)
                    for item in section_path
                )
            else:
                sections[source] = str(section_path)

        lines.append(
            "| {rank} | {title} | {score:.6f} | {bm25} | {vector} |".format(
                rank=hit.get("rank", ""),
                title=_markdown_cell(title),
                score=float(hit.get("score", 0.0)),
                bm25=_markdown_cell(
                    sections.get("bm25", "")
                ),
                vector=_markdown_cell(
                    sections.get("bge-m3", "")
                ),
            )
        )

    lines.extend([
        "",
        "## Paper Evidence",
        "",
    ])

    for hit in selected_hits:
        paper_id = str(hit.get("paper_id", ""))
        outcome = titles.get(paper_id, {})
        title = str(outcome.get("title", paper_id))
        accepted_by = str(
            outcome.get("accepted_by", "")
        )
        hybrid_score = float(hit.get("score", 0.0))

        lines.extend([
            f"### {hit.get('rank', '')}. {title}",
            "",
            f"- Paper ID: `{paper_id}`",
            f"- Hybrid score: `{hybrid_score:.6f}`",
            (
                "- Topic workflow status: "
                f"PDF=`{outcome.get('pdf_status', '')}`; "
                f"document=`{outcome.get('document_status', '')}`; "
                f"quality=`{outcome.get('quality_status', '')}`"
            ),
        ])

        if accepted_by:
            lines.append(
                f"- Venue / source: `{accepted_by}`"
            )

        lines.append("")
        lines.append("#### Retrieved Evidence")

        wrappers = hit.get("evidence", [])

        if not isinstance(wrappers, list):
            wrappers = []

        for wrapper in wrappers:
            if not isinstance(wrapper, dict):
                continue

            source, evidence_items = _source_evidence(wrapper)

            for evidence_index, evidence in enumerate(
                evidence_items[:evidence_per_source],
                start=1,
            ):
                chunk = evidence.get("chunk", {})

                if not isinstance(chunk, dict):
                    continue

                section_path = chunk.get(
                    "section_path",
                    [],
                )

                if isinstance(section_path, list):
                    section = " > ".join(
                        str(item)
                        for item in section_path
                    )
                else:
                    section = str(section_path)

                text = _clean_text(
                    str(chunk.get("text", "")),
                    preview_chars,
                )

                lines.extend([
                    "",
                    f"##### {source} evidence {evidence_index}",
                    "",
                    (
                        "- Chunk score: "
                        f"`{float(evidence.get('score', 0.0)):.6f}`"
                    ),
                    (
                        "- Location: "
                        f"pages `{chunk.get('page_start', '')}`"
                        f"-`{chunk.get('page_end', '')}`; "
                        f"section `{section}`"
                    ),
                    (
                        "- Chunk ID: "
                        f"`{chunk.get('chunk_id', '')}`"
                    ),
                    "",
                    "> " + text,
                ])

        lines.extend([
            "",
            "#### Analyst Notes",
            "",
            (
                "- Mechanism hypothesis (to verify against "
                "the cited evidence):"
            ),
            "- Relevance to the topic:",
            "- Limitations / open questions:",
            "",
        ])

    lines.extend([
        "## Cross-paper Analysis Prompts",
        "",
        "- Which papers address persistent agent memory directly, "
        "and which address adjacent long-context or retention mechanisms?",
        "- What information is retained, compressed, replayed, "
        "or selectively forgotten in each approach?",
        "- Which claims have direct evidence above, and which "
        "would need additional targeted retrieval before synthesis?",
        "",
    ])

    return "\n".join(lines)


def main(
    argv: Sequence[str] | None = None,
) -> int:
    args = build_argument_parser().parse_args(argv)

    try:
        workflow_path, workflow = _load_json(
            args.topic_workflow_json
        )
        hybrid_path, hybrid = _load_json(
            args.hybrid_result_json
        )
        markdown = build_dossier_markdown(
            workflow_path=workflow_path,
            workflow=workflow,
            hybrid_path=hybrid_path,
            hybrid=hybrid,
            top_papers=args.top_papers,
            evidence_per_source=(
                args.evidence_per_source
            ),
            preview_chars=args.preview_chars,
        )
    except Exception as error:
        print("EVIDENCE_DOSSIER_ERROR")
        print(f"{type(error).__name__}: {error}")
        return 1

    output_path = Path(args.output_md).expanduser().resolve()
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output_path.write_text(
        markdown + "\n",
        encoding="utf-8",
    )

    print("=" * 100)
    print("Topic evidence dossier")
    print("=" * 100)
    print(f"workflow_topic: {workflow['topic']}")
    print(f"retrieval_query: {hybrid['query']}")
    print(f"paper_count: {min(args.top_papers, len(hybrid['paper_search_result']['hits']))}")
    print(f"evidence_per_source: {args.evidence_per_source}")
    print(f"output_md: {output_path}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
