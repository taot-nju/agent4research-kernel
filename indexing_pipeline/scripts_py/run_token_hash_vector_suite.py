"""运行 token-hash vector retrieval suite。

这是一个 operator-facing CLI / 手工测试入口。

它读取 retrieval suite manifest，对每个 case：

1. 读取人工标注 dataset，拿到 query 和 candidate_paper_ids；
2. 调用 search_candidate_vector_demo 的核心函数生成 token-hash vector search output；
3. 调用 retrieval evaluation runner 计算 metrics；
4. 写出每个 case 的 search output 和 metrics；
5. 写出 suite-level summary。

注意：token-hash 不是语义 embedding，只是 demo vector baseline。
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ai4research.indexing_pipeline.evaluation.runner import (
    evaluate_saved_paper_ranking,
)
from ai4research.indexing_pipeline.scripts_py.search_candidate_vector_demo import (
    DEFAULT_SPLITTER_NAME,
    DEFAULT_SPLITTER_OPTIONS,
    DEFAULT_SPLITTER_VERSION,
    build_result,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "读取 retrieval suite，逐 case 运行 token-hash demo vector search，"
            "保存 search output、metrics 和 suite summary。"
        )
    )
    parser.add_argument(
        "--suite",
        default="~/ai4research/evaluation_datasets/retrieval/retrieval_suite_v1.json",
        help="retrieval suite manifest JSON 路径",
    )
    parser.add_argument(
        "--repo-root",
        default="~/ai4research",
        help="用于解析 suite 内相对路径的项目根目录，默认 ~/ai4research",
    )
    parser.add_argument(
        "--output-dir",
        default="~/ai4research/evaluation_datasets/retrieval/token_hash_vector_v1",
        help="token-hash vector suite 输出目录",
    )
    parser.add_argument(
        "--embedding-cache-dir",
        default="/tmp/ai4research_demo_vector_suite_embeddings",
        help="token-hash embedding JSONL 缓存目录",
    )
    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=256,
        help="token-hash embedding 维度，默认 256",
    )
    parser.add_argument(
        "--chunk-recall-k",
        type=int,
        default=300,
        help="vector chunk 召回数，默认 300",
    )
    parser.add_argument(
        "--final-paper-k",
        type=int,
        default=10,
        help="每个 case 最终论文数，默认 10",
    )
    parser.add_argument(
        "--evidence-chunks-per-paper",
        type=int,
        default=3,
        help="每篇论文返回 evidence chunk 数，默认 3",
    )
    parser.add_argument(
        "--top-chunks-for-score",
        type=int,
        default=3,
        help="论文聚合评分使用的 top chunk 数，默认 3",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=220,
        help="证据文本预览字符数，默认 220",
    )
    parser.add_argument(
        "--reuse-embeddings",
        action="store_true",
        help="如果 token-hash embeddings 已存在，则复用缓存",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        help="只运行指定 case；可重复传入。默认运行 suite 中所有 case",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _resolve_path(repo_root: Path, path_text: str) -> Path:
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return path
    return repo_root / path


def _single_case_dataset(dataset_path: Path, *, case_id: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    dataset = _load_json(dataset_path)
    cases = dataset.get("cases", [])

    if case_id:
        matched = [
            case
            for case in cases
            if case.get("case_id") == case_id
        ]
    else:
        matched = cases

    if len(matched) != 1:
        raise ValueError(
            f"expected exactly one evaluation case in {dataset_path}, got {len(matched)}"
        )

    return dataset, matched[0]


def _metrics_to_dict(metrics: Any) -> dict[str, Any]:
    return asdict(metrics)


def _metric_at_k(metrics: dict[str, Any], k: int) -> dict[str, Any] | None:
    for item in metrics.get("metrics_at_k", []):
        if int(item["k"]) == k:
            return item
    return None


def _mean(values: list[float | None]) -> float | None:
    values = [
        value
        for value in values
        if value is not None
    ]
    return sum(values) / len(values) if values else None


def _search_args_for_case(
    *,
    query: str,
    paper_ids: list[str],
    args: argparse.Namespace,
) -> SimpleNamespace:
    return SimpleNamespace(
        query=query,
        paper_id=paper_ids,
        data_root="/data/ai4research_assets",
        splitter_name=DEFAULT_SPLITTER_NAME,
        splitter_version=DEFAULT_SPLITTER_VERSION,
        target_chars=DEFAULT_SPLITTER_OPTIONS["target_chars"],
        max_chars=DEFAULT_SPLITTER_OPTIONS["max_chars"],
        overlap_chars=DEFAULT_SPLITTER_OPTIONS["overlap_chars"],
        min_chars_before_heading_break=DEFAULT_SPLITTER_OPTIONS[
            "min_chars_before_heading_break"
        ],
        embedding_dim=args.embedding_dim,
        chunk_recall_k=args.chunk_recall_k,
        final_paper_k=args.final_paper_k,
        evidence_chunks_per_paper=args.evidence_chunks_per_paper,
        top_chunks_for_score=args.top_chunks_for_score,
        preview_chars=args.preview_chars,
        embedding_cache_dir=args.embedding_cache_dir,
        reuse_embeddings=args.reuse_embeddings,
        save_json=None,
    )


def _build_suite_summary(
    *,
    suite_path: Path,
    output_dir: Path,
    case_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    macro = {
        "macro_mrr": _mean([case["reciprocal_rank"] for case in case_summaries]),
        "macro_ap": _mean([case["average_precision"] for case in case_summaries]),
        "macro_precision_at_5": _mean([case["precision_at_5"] for case in case_summaries]),
        "macro_recall_at_5": _mean([case["recall_at_5"] for case in case_summaries]),
        "macro_ndcg_at_5": _mean([case["ndcg_at_5"] for case in case_summaries]),
    }

    return {
        "name": "ai4research-retrieval-suite-token-hash-vector-summary",
        "version": "1",
        "suite_path": str(suite_path),
        "output_dir": str(output_dir),
        "baseline": {
            "name": "token-hash-vector-demo",
            "description": "Local token-hash demo vector baseline; not a semantic embedding model.",
        },
        "case_count": len(case_summaries),
        "cases": case_summaries,
        "macro": macro,
        "weakest": {
            "weakest_ap_case": min(case_summaries, key=lambda case: case["average_precision"])["case_id"],
            "weakest_ndcg_at_5_case": min(case_summaries, key=lambda case: case["ndcg_at_5"])["case_id"],
        },
        "notes": [
            "Token-hash is a deterministic local demo embedding, not a semantic embedding model.",
            "This runner verifies that vector retrieval can be evaluated with the same retrieval suite protocol as BM25.",
        ],
    }


def run_suite(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    suite_path = Path(args.suite).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    suite = _load_json(suite_path)

    selected_case_ids = set(args.case_id or [])
    suite_cases = [
        case
        for case in suite["cases"]
        if not selected_case_ids or case["case_id"] in selected_case_ids
    ]

    if selected_case_ids and len(suite_cases) != len(selected_case_ids):
        found = {
            case["case_id"]
            for case in suite_cases
        }
        missing = sorted(selected_case_ids - found)
        raise ValueError(f"unknown case_id(s): {missing}")

    case_summaries: list[dict[str, Any]] = []

    for index, suite_case in enumerate(suite_cases, start=1):
        case_id = suite_case["case_id"]
        dataset_path = _resolve_path(
            repo_root,
            suite_case["dataset_path"],
        )
        _, evaluation_case = _single_case_dataset(
            dataset_path,
            case_id=case_id,
        )

        query = str(evaluation_case["query"])
        candidate_paper_ids = list(evaluation_case["candidate_paper_ids"])
        minimum_relevance = int(
            suite_case.get(
                "minimum_relevance",
                suite.get("default_scoring", {}).get("minimum_relevance", 2),
            )
        )

        print("=" * 100)
        print(
            f"[{index}/{len(suite_cases)}] token-hash vector case: {case_id}"
        )
        print("=" * 100)
        print(f"query: {query}")
        print(f"candidate_count: {len(candidate_paper_ids)}")

        search_result = build_result(
            args=_search_args_for_case(
                query=query,
                paper_ids=candidate_paper_ids,
                args=args,
            )
        )

        search_output_path = output_dir / f"{case_id}_token_hash_vector_search_output.json"
        metrics_path = output_dir / f"{case_id}_token_hash_vector_metrics.json"

        _write_json(search_output_path, search_result)

        metrics = evaluate_saved_paper_ranking(
            dataset_path=dataset_path,
            search_result_path=search_output_path,
            case_id=case_id,
            k_values=(1, 3, 5, 10),
            minimum_relevance=minimum_relevance,
        )
        metrics_dict = _metrics_to_dict(metrics)
        _write_json(metrics_path, metrics_dict)

        k5 = _metric_at_k(metrics_dict, 5)
        case_summary = {
            "case_id": metrics_dict["case_id"],
            "query": metrics_dict["query"],
            "minimum_relevance": metrics_dict["minimum_relevance"],
            "candidate_count": metrics_dict["candidate_count"],
            "judged_count": metrics_dict["judged_count"],
            "relevant_count": metrics_dict["relevant_count"],
            "retrieved_count": metrics_dict["retrieved_count"],
            "reciprocal_rank": metrics_dict["reciprocal_rank"],
            "average_precision": metrics_dict["average_precision"],
            "precision_at_5": k5["precision"] if k5 else None,
            "recall_at_5": k5["recall"] if k5 else None,
            "ndcg_at_5": k5["ndcg"] if k5 else None,
            "search_result_path": str(search_output_path),
            "metrics_path": str(metrics_path),
        }
        case_summaries.append(case_summary)

        print(
            "metrics: "
            f"MRR={case_summary['reciprocal_rank']:.4f} "
            f"AP={case_summary['average_precision']:.4f} "
            f"P@5={case_summary['precision_at_5']:.4f} "
            f"R@5={case_summary['recall_at_5']:.4f} "
            f"nDCG@5={case_summary['ndcg_at_5']:.4f}"
        )
        print(f"search_output: {search_output_path}")
        print(f"metrics_json:   {metrics_path}")

    summary = _build_suite_summary(
        suite_path=suite_path,
        output_dir=output_dir,
        case_summaries=case_summaries,
    )
    summary_path = output_dir / "retrieval_suite_v1_token_hash_vector_summary.json"
    _write_json(summary_path, summary)

    print("=" * 100)
    print("Token-hash vector suite summary")
    print("=" * 100)
    print(f"case_count: {summary['case_count']}")
    for key, value in summary["macro"].items():
        print(f"{key}: {value:.4f}" if value is not None else f"{key}: None")
    print(f"weakest_ap_case: {summary['weakest']['weakest_ap_case']}")
    print(f"weakest_ndcg_at_5_case: {summary['weakest']['weakest_ndcg_at_5_case']}")
    print(f"summary_json: {summary_path}")
    print("=" * 100)

    return summary


def main() -> None:
    args = parse_args()
    run_suite(args)


if __name__ == "__main__":
    main()
