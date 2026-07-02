import json
from pathlib import Path

from ai4research.indexing_pipeline.scripts_py.build_topic_research_brief import build_brief


def test_build_brief_generates_minimal_markdown() -> None:
    workflow = {
        "topic": "agent memory",
        "outcomes": [
            {"paper_id": "paper-1", "ready": True},
            {"paper_id": "paper-2", "ready": True},
        ],
    }

    dossier_text = """# Topic Evidence Dossier

## Ranked Paper Overview

| rank | paper | hybrid score | BM25 evidence section | bge-m3 evidence section |
|---:|---|---:|---|---|
| 1 | Paper One | 1.0 | Intro | Method |

## Paper Evidence

### 1. Paper One

- Paper ID: `paper-1`

#### Retrieved Evidence

##### bm25 evidence 1

> some evidence

### 2. Paper Two

- Paper ID: `paper-2`

#### Retrieved Evidence

##### bm25 evidence 1

> other evidence

## Cross-paper Analysis Prompts

- prompt
"""

    brief = build_brief(
        workflow=workflow,
        dossier_text=dossier_text,
        workflow_path=Path("/tmp/workflow.json"),
        dossier_path=Path("/tmp/dossier.md"),
        top_papers=1,
    )

    assert "# Topic Research Brief" in brief
    assert "## Topic" in brief
    assert "## One-screen Summary" in brief
    assert "## Ranked Paper Overview" in brief
    assert "## Per-paper Notes" in brief
    assert "### 1. Paper One" in brief
    assert "### 2. Paper Two" not in brief
    assert "## Evidence Gaps" in brief
    assert "`agent memory`" in brief
