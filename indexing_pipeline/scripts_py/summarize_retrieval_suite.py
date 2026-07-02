"""汇总 retrieval suite 的评估指标。

这个脚本读取 retrieval_suite_v1.json 中登记的多个评估案例，
再读取每个案例对应的 metrics JSON，生成 suite 级别的 baseline summary。

示例：

PYTHONPATH="$HOME" python -m ai4research.indexing_pipeline.scripts_py.summarize_retrieval_suite \
  --suite ~/ai4research/evaluation_datasets/retrieval/retrieval_suite_v1.json \
  --save-json ~/ai4research/evaluation_datasets/retrieval/retrieval_suite_v1_bm25_baseline_summary.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_path(repo_root: Path, path_text: str) -> Path:
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return path
    return repo_root / path


def _mean(values: list[float | None]) -> float | None:
    available = [value for value in values if value is not None]
    if not available:
        return None
    return sum(available) / len(available)


def _metric_at_k(metrics: dict[str, Any], k: int) -> dict[str, Any] | None:
    for item in metrics.get("metrics_at_k", []):
        if int(item["k"]) == k:
            return item
    return None


def build_summary(*, suite_path: Path, repo_root: Path, baseline_name: str) -> dict[str, Any]:
    suite = _load_json(suite_path)
    case_summaries: list[dict[str, Any]] = []

    for case in suite["cases"]:
        metrics_path = _resolve_path(repo_root, case["metrics_path"])
        metrics = _load_json(metrics_path)
        k5 = _metric_at_k(metrics, 5)

        case_summaries.append(
            {
                "case_id": metrics["case_id"],
                "query": metrics["query"],
                "minimum_relevance": metrics["minimum_relevance"],
                "candidate_count": metrics["candidate_count"],
                "judged_count": metrics["judged_count"],
                "relevant_count": metrics["relevant_count"],
                "retrieved_count": metrics["retrieved_count"],
                "reciprocal_rank": metrics["reciprocal_rank"],
                "average_precision": metrics["average_precision"],
                "precision_at_5": k5["precision"] if k5 else None,
                "recall_at_5": k5["recall"] if k5 else None,
                "ndcg_at_5": k5["ndcg"] if k5 else None,
                "dataset_path": case["dataset_path"],
                "search_result_path": case["search_result_path"],
                "metrics_path": case["metrics_path"],
            }
        )

    macro = {
        "macro_mrr": _mean([case["reciprocal_rank"] for case in case_summaries]),
        "macro_ap": _mean([case["average_precision"] for case in case_summaries]),
        "macro_precision_at_5": _mean([case["precision_at_5"] for case in case_summaries]),
        "macro_recall_at_5": _mean([case["recall_at_5"] for case in case_summaries]),
        "macro_ndcg_at_5": _mean([case["ndcg_at_5"] for case in case_summaries]),
    }

    weakest = {
        "weakest_ap_case": min(case_summaries, key=lambda case: case["average_precision"])["case_id"],
        "weakest_ndcg_at_5_case": min(case_summaries, key=lambda case: case["ndcg_at_5"])["case_id"],
    }

    return {
        "name": f"ai4research-retrieval-suite-{baseline_name}-summary",
        "version": "1",
        "suite_path": str(suite_path),
        "baseline": suite.get("baseline", {"name": baseline_name}),
        "case_count": len(case_summaries),
        "cases": case_summaries,
        "macro": macro,
        "weakest": weakest,
        "notes": [
            "This summary is generated from saved per-case retrieval metrics.",
            "Scores evaluate fulltext reranking inside each case's metadata candidate set, not global recall over the full database.",
        ],
    }


def print_summary(summary: dict[str, Any]) -> None:
    print("=" * 100)
    print("Retrieval suite summary")
    print("=" * 100)
    print(f"name:       {summary['name']}")
    print(f"case_count: {summary['case_count']}")
    print("-" * 100)
    print(f"{'case_id':40s} {'rel':>4s} {'MRR':>7s} {'AP':>7s} {'P@5':>7s} {'R@5':>7s} {'nDCG@5':>8s}")
    print("-" * 100)

    for case in summary["cases"]:
        print(
            f"{case['case_id']:40s} "
            f"{case['relevant_count']:4d} "
            f"{case['reciprocal_rank']:7.4f} "
            f"{case['average_precision']:7.4f} "
            f"{case['precision_at_5']:7.4f} "
            f"{case['recall_at_5']:7.4f} "
            f"{case['ndcg_at_5']:8.4f}"
        )

    print("-" * 100)
    macro = summary["macro"]
    for key in ("macro_mrr", "macro_ap", "macro_precision_at_5", "macro_recall_at_5", "macro_ndcg_at_5"):
        value = macro[key]
        print(f"{key}: {value:.4f}" if value is not None else f"{key}: None")

    weakest = summary["weakest"]
    print(f"weakest_ap_case: {weakest['weakest_ap_case']}")
    print(f"weakest_ndcg_at_5_case: {weakest['weakest_ndcg_at_5_case']}")
    print("=" * 100)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="读取 retrieval suite manifest 和已保存 metrics，生成 suite 级检索评估汇总。"
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
        "--baseline-name",
        default="bm25-baseline",
        help="写入 summary name 的 baseline 名称，默认 bm25-baseline",
    )
    parser.add_argument(
        "--save-json",
        help="可选：保存 summary JSON 到指定路径",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    suite_path = Path(args.suite).expanduser().resolve()

    summary = build_summary(
        suite_path=suite_path,
        repo_root=repo_root,
        baseline_name=args.baseline_name,
    )

    print_summary(summary)

    if args.save_json:
        save_path = Path(args.save_json).expanduser().resolve()
        save_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"JSON report saved: {save_path}")


if __name__ == "__main__":
    main()
