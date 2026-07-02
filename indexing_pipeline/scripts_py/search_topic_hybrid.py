"""从已保存的 topic workflow JSON 读取 ready 论文，执行推荐 hybrid 检索。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence

from ai4research.indexing_pipeline.scripts_py.search_candidate_hybrid import (
    build_result as build_hybrid_result,
    print_result as print_hybrid_result,
)


DEFAULT_EMBEDDING_CACHE_DIR = (
    "/tmp/ai4research_topic_hybrid_embeddings"
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "读取 process_research_topic --save-json 的 workflow "
            "结果，只使用 ready=True 的论文，执行当前推荐的 "
            "BM25 0.7 + bge-m3 subchunk vector 0.3 hybrid 检索。"
        )
    )
    parser.add_argument(
        "--topic-workflow-json",
        required=True,
        help=(
            "process_research_topic --save-json "
            "生成的 workflow JSON 路径"
        ),
    )
    parser.add_argument(
        "--query",
        help=(
            "可选：覆盖 workflow JSON 中的 topic；"
            "默认直接使用 workflow topic"
        ),
    )
    parser.add_argument(
        "--data-root",
        default="/data/ai4research_assets",
        help="资产根目录，默认 /data/ai4research_assets",
    )
    parser.add_argument(
        "--chunk-recall-k",
        type=int,
        default=300,
        help="BM25/vector chunk 召回数，默认 300",
    )
    parser.add_argument(
        "--final-paper-k",
        type=int,
        default=5,
        help="最终论文数，默认 5",
    )
    parser.add_argument(
        "--evidence-chunks-per-paper",
        type=int,
        default=3,
        help="每篇论文保留 evidence chunk 数，默认 3",
    )
    parser.add_argument(
        "--top-chunks-for-score",
        type=int,
        default=3,
        help="论文聚合评分使用的 top chunk 数，默认 3",
    )
    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=1024,
        help=(
            "bge-m3 embedding 维度；必须匹配 "
            "AI4RESEARCH_EMBEDDING_DIMENSION，默认 1024"
        ),
    )
    parser.add_argument(
        "--embedding-cache-dir",
        default=DEFAULT_EMBEDDING_CACHE_DIR,
        help=(
            "bge-m3 embedding JSONL 缓存目录，默认 "
            "/tmp/ai4research_topic_hybrid_embeddings"
        ),
    )
    parser.add_argument(
        "--reuse-embeddings",
        action="store_true",
        help="如果 embeddings 已存在，则复用缓存",
    )
    parser.add_argument(
        "--subchunk-max-chars",
        type=int,
        default=3200,
        help=(
            "超过该字符数的 chunk 会完整切成 "
            "subchunk embedding，默认 3200"
        ),
    )
    parser.add_argument(
        "--subchunk-overlap-chars",
        type=int,
        default=200,
        help="subchunk 之间的重叠字符数，默认 200",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=220,
        help="终端 evidence 文本预览字符数，默认 220",
    )
    parser.add_argument(
        "--save-json",
        help="可选：保存完整 topic hybrid search result JSON",
    )
    return parser


def _load_topic_workflow(
    path: str,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    resolved = Path(path).expanduser().resolve()
    workflow = json.loads(
        resolved.read_text(encoding="utf-8")
    )

    if not isinstance(workflow, dict):
        raise ValueError(
            "topic workflow JSON 必须是 object"
        )

    topic = str(workflow.get("topic", "")).strip()

    if not topic:
        raise ValueError(
            "topic workflow JSON 缺少 topic"
        )

    outcomes = workflow.get("outcomes")

    if not isinstance(outcomes, list):
        raise ValueError(
            "topic workflow JSON 缺少 outcomes list；"
            "请使用 process_research_topic --save-json 的输出"
        )

    ready_paper_ids = tuple(
        dict.fromkeys(
            str(outcome.get("paper_id", "")).strip()
            for outcome in outcomes
            if isinstance(outcome, dict)
            and outcome.get("ready") is True
            and str(outcome.get("paper_id", "")).strip()
        )
    )

    if not ready_paper_ids:
        raise ValueError(
            "workflow 中没有 ready=True 的论文；"
            "请先完成 PDF/OCR/质量检查，并确认 chunk 资产已生成"
        )

    workflow["_source_path"] = str(resolved)
    workflow["_outcome_count"] = len(outcomes)
    workflow["_ready_outcome_count"] = len(
        ready_paper_ids
    )

    return workflow, ready_paper_ids


def _hybrid_args(
    *,
    query: str,
    paper_ids: tuple[str, ...],
    args: argparse.Namespace,
) -> SimpleNamespace:
    return SimpleNamespace(
        query=query,
        paper_id=list(paper_ids),
        data_root=args.data_root,
        target_chars=2400,
        max_chars=3200,
        overlap_chars=300,
        min_chars_before_heading_break=800,
        chunk_recall_k=args.chunk_recall_k,
        final_paper_k=args.final_paper_k,
        evidence_chunks_per_paper=(
            args.evidence_chunks_per_paper
        ),
        top_chunks_for_score=(
            args.top_chunks_for_score
        ),
        bm25_k1=1.5,
        bm25_b=0.75,
        section_term_multiplier=2,
        embedding_dim=args.embedding_dim,
        embedding_cache_dir=(
            args.embedding_cache_dir
        ),
        reuse_embeddings=args.reuse_embeddings,
        subchunk_max_chars=args.subchunk_max_chars,
        subchunk_overlap_chars=(
            args.subchunk_overlap_chars
        ),
        bm25_weight=0.7,
        vector_weight=0.3,
        preview_chars=args.preview_chars,
    )


def build_result(
    *,
    args: argparse.Namespace,
) -> dict[str, Any]:
    workflow, ready_paper_ids = _load_topic_workflow(
        args.topic_workflow_json
    )
    query = str(args.query or workflow["topic"]).strip()

    if not query:
        raise ValueError("query 不能为空")

    result = build_hybrid_result(
        args=_hybrid_args(
            query=query,
            paper_ids=ready_paper_ids,
            args=args,
        )
    )
    result["topic_workflow"] = {
        "source_path": workflow["_source_path"],
        "topic": workflow["topic"],
        "query": query,
        "outcome_count": workflow["_outcome_count"],
        "ready_outcome_count": (
            workflow["_ready_outcome_count"]
        ),
        "ready_paper_ids": list(ready_paper_ids),
        "selection_rule": "outcome.ready == true",
    }

    return result


def _write_json(
    *,
    path: str,
    payload: dict[str, Any],
) -> Path:
    resolved = Path(path).expanduser().resolve()
    resolved.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    resolved.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return resolved


def main(
    argv: Sequence[str] | None = None,
) -> int:
    args = build_argument_parser().parse_args(argv)

    try:
        result = build_result(args=args)
    except Exception as error:
        print("TOPIC_HYBRID_SEARCH_ERROR", file=sys.stderr)
        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1

    topic_workflow = result["topic_workflow"]

    print("=" * 100)
    print("Topic workflow → recommended hybrid")
    print("=" * 100)
    print(
        "workflow_topic:        "
        + topic_workflow["topic"]
    )
    print(
        "workflow_ready_papers: "
        + str(topic_workflow["ready_outcome_count"])
    )
    print(
        "workflow_outcomes:     "
        + str(topic_workflow["outcome_count"])
    )
    print(
        "selection_rule:        "
        + topic_workflow["selection_rule"]
    )
    print("=" * 100)

    print_hybrid_result(
        result=result,
        preview_chars=args.preview_chars,
    )

    if args.save_json:
        saved_path = _write_json(
            path=args.save_json,
            payload=result,
        )
        print(f"JSON result saved: {saved_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
