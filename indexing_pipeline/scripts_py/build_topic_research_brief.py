"""Build an evidence-backed topic research brief from workflow and dossier assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "读取 topic workflow JSON 与 evidence dossier Markdown，"
            "生成最小 evidence-backed research brief。"
        )
    )
    parser.add_argument(
        "--topic-workflow-json",
        required=True,
        help="process_research_topic --save-json 的 workflow JSON 路径",
    )
    parser.add_argument(
        "--evidence-dossier-md",
        required=True,
        help="build_topic_evidence_dossier 生成的 Markdown dossier 路径",
    )
    parser.add_argument(
        "--output-md",
        required=True,
        help="输出 Markdown research brief 路径",
    )
    parser.add_argument(
        "--top-papers",
        type=int,
        default=5,
        help="brief 中写入前多少篇论文，默认 5",
    )
    return parser


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_ranked_paper_overview(dossier_text: str) -> str:
    heading = "## Ranked Paper Overview"
    start = dossier_text.find(heading)
    if start < 0:
        return "_Ranked Paper Overview not found in dossier._\n"

    next_heading = dossier_text.find("\n## ", start + len(heading))
    if next_heading < 0:
        next_heading = len(dossier_text)

    section = dossier_text[start:next_heading].strip()
    return section + "\n"


def _extract_paper_sections(
    dossier_text: str,
    top_papers: int,
) -> str:
    paper_heading = "## Paper Evidence"
    start = dossier_text.find(paper_heading)
    if start < 0:
        return "_Paper evidence sections not found in dossier._\n"

    next_heading = dossier_text.find("\n## Cross-paper Analysis Prompts", start)
    if next_heading < 0:
        next_heading = len(dossier_text)

    block = dossier_text[start:next_heading]
    parts = block.split("\n### ")
    sections: list[str] = []

    for part in parts[1: 1 + top_papers]:
        sections.append("### " + part.strip())

    if not sections:
        return "_No per-paper sections found in dossier._\n"

    return "\n\n".join(sections) + "\n"


def build_brief(
    *,
    workflow: dict,
    dossier_text: str,
    workflow_path: Path,
    dossier_path: Path,
    top_papers: int,
) -> str:
    topic = workflow.get("topic", "")
    outcomes = workflow.get("outcomes", [])
    ready_outcomes = [
        outcome
        for outcome in outcomes
        if outcome.get("ready") is True
    ]

    ranked_overview = _extract_ranked_paper_overview(dossier_text)
    paper_sections = _extract_paper_sections(
        dossier_text=dossier_text,
        top_papers=top_papers,
    )

    lines = [
        "# Topic Research Brief",
        "",
        "## Topic",
        "",
        f"- Topic: `{topic}`",
        f"- Workflow JSON: `{workflow_path}`",
        f"- Evidence dossier: `{dossier_path}`",
        f"- Ready paper count: `{len(ready_outcomes)}`",
        f"- Top papers requested: `{top_papers}`",
        "",
        "## One-screen Summary",
        "",
        "- This brief is derived from the existing evidence dossier and does not add unsupported claims.",
        f"- The current workflow topic is `{topic}`.",
        f"- The workflow currently contains `{len(ready_outcomes)}` ready papers for evidence-backed review.",
        "- The ranked overview and per-paper notes below are copied from dossier-backed evidence sections.",
        "",
        ranked_overview.strip(),
        "",
        "## Per-paper Notes",
        "",
        paper_sections.strip(),
        "",
        "## Evidence Gaps",
        "",
        "- Mechanism summaries still need tighter human-written synthesis from the cited evidence.",
        "- Cross-paper comparisons should be written only after verifying the cited sections directly.",
        "- Any claim not directly supported by the dossier should be treated as a follow-up question, not a conclusion.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    workflow_path = Path(args.topic_workflow_json).expanduser()
    dossier_path = Path(args.evidence_dossier_md).expanduser()
    output_path = Path(args.output_md).expanduser()

    workflow = _read_json(workflow_path)
    dossier_text = dossier_path.read_text(encoding="utf-8")

    brief = build_brief(
        workflow=workflow,
        dossier_text=dossier_text,
        workflow_path=workflow_path,
        dossier_path=dossier_path,
        top_papers=args.top_papers,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(brief, encoding="utf-8")

    print("=" * 100)
    print("Topic research brief")
    print("=" * 100)
    print(f"topic: {workflow.get('topic', '')}")
    print(f"ready_paper_count: {sum(1 for item in workflow.get('outcomes', []) if item.get('ready') is True)}")
    print(f"top_papers: {args.top_papers}")
    print(f"output_md: {output_path}")
    print("=" * 100)


if __name__ == "__main__":
    main()
