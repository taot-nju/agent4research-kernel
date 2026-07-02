"""Run hybrid retrieval over a retrieval suite.

Operator-facing CLI for manually evaluating BM25 + vector hybrid results.

Inputs:
- retrieval suite manifest
- primary result directory, e.g. BM25 saved search outputs
- secondary result directory, e.g. bge-m3 vector saved search outputs

Outputs:
- per-case hybrid search output JSON
- per-case metrics JSON
- suite summary JSON
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai4research.indexing_pipeline.evaluation.runner import (
    evaluate_saved_paper_ranking,
)
from ai4research.indexing_pipeline.scripts_py.fuse_saved_paper_rankings import (
    build_hybrid_result,
)


DEFAULT_SUITE = (
    "~/ai4research/evaluation_datasets/retrieval/retrieval_suite_v1.json"
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "读取 retrieval suite，逐 case 融合 primary 与 secondary "
            "paper ranking，保存 hybrid search output、metrics 和 suite summary。"
        )
    )
    parser.add_argument(
        "--suite",
        default=DEFAULT_SUITE,
        help="retrieval suite manifest JSON 路径",
    )
    parser.add_argument(
        "--repo-root",
        default="~/ai4research",
        help="用于解析 suite 内相对路径的项目根目录，默认 ~/ai4research",
    )
    parser.add_argument(
        "--primary-result-dir",
        help="primary search output 所在目录；省略时使用 suite case 的 search_result_path",
    )
    parser.add_argument(
        "--secondary-result-dir",
        required=True,
        help="secondary search output 所在目录，例如 vector 结果目录",
    )
    parser.add_argument(
        "--primary-pattern",
        default="{case_id}_search_output.json",
        help="primary 文件名模式，支持 {case_id}",
    )
    parser.add_argument(
        "--secondary-pattern",
        default="{case_id}_{secondary_run_name}_search_output.json",
        help="secondary 文件名模式，支持 {case_id} 和 {secondary_run_name}",
    )
    parser.add_argument(
        "--primary-name",
        default="bm25",
        help="primary 结果名称，默认 bm25",
    )
    parser.add_argument(
        "--secondary-name",
        default="bge-m3",
        help="secondary 结果名称，默认 bge-m3",
    )
    parser.add_argument(
        "--secondary-run-name",
        default="bge_m3_truncated_3200",
        help="secondary 文件名中的 run name，默认 bge_m3_truncated_3200",
    )
    parser.add_argument(
        "--primary-weight",
        type=float,
        default=0.5,
        help="primary 融合权重，默认 0.5",
    )
    parser.add_argument(
        "--secondary-weight",
        type=float,
        default=0.5,
        help="secondary 融合权重，默认 0.5",
    )
    parser.add_argument(
        "--final-paper-k",
        type=int,
        default=10,
        help="每个 case 输出论文数，默认 10",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="hybrid suite 输出目录",
    )
    parser.add_argument(
        "--run-name",
        default="bm25_bge_m3_hybrid",
        help="输出文件名前缀，默认 bm25_bge_m3_hybrid",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        help="只运行指定 case；可重复传入。默认运行 suite 中所有 case",
    )
    return parser


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.expanduser().read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return resolved


def _resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return repo_root / path


def _single_case_dataset(
    dataset_path: Path,
    *,
    case_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    dataset = _load_json(dataset_path)
    cases = list(dataset.get("cases", []))

    for case in cases:
        if str(case.get("case_id")) == case_id:
            return dataset, case

    raise ValueError(f"case_id not found in dataset: {case_id}")


def _metric_at_k(metrics_dict: dict[str, Any], k: int) -> dict[str, Any]:
    for item in metrics_dict["metrics_at_k"]:
        if int(item["k"]) == k:
            return item
    raise ValueError(f"metric k={k} not found")


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _result_path(
    *,
    directory: Path,
    pattern: str,
    case_id: str,
    secondary_run_name: str,
) -> Path:
    return directory / pattern.format(
        case_id=case_id,
        secondary_run_name=secondary_run_name,
    )


def _build_suite_summary(
    *,
    suite_path: Path,
    output_dir: Path,
    run_name: str,
    primary_name: str,
    secondary_name: str,
    primary_weight: float,
    secondary_weight: float,
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
        "name": f"ai4research-retrieval-suite-{run_name}-summary",
        "version": "1",
        "suite_path": str(suite_path),
        "output_dir": str(output_dir),
        "baseline": {
            "name": run_name,
            "primary_name": primary_name,
            "secondary_name": secondary_name,
            "primary_weight": primary_weight,
            "secondary_weight": secondary_weight,
            "description": "Hybrid retrieval suite run.",
        },
        "case_count": len(case_summaries),
        "cases": case_summaries,
        "macro": macro,
        "weakest": {
            "weakest_ap_case": min(case_summaries, key=lambda case: case["average_precision"])["case_id"],
            "weakest_ndcg_at_5_case": min(case_summaries, key=lambda case: case["ndcg_at_5"])["case_id"],
        },
        "notes": [
            "This summary is generated by run_hybrid_suite.py.",
            "Hybrid result is generated by fuse_saved_paper_rankings.build_hybrid_result.",
        ],
    }


def run_suite(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    suite_path = Path(args.suite).expanduser().resolve()
    primary_dir = (
        Path(args.primary_result_dir).expanduser().resolve()
        if args.primary_result_dir
        else None
    )
    secondary_dir = Path(args.secondary_result_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    suite = _load_json(suite_path)
    selected_case_ids = set(args.case_id or [])
    suite_cases = [
        case
        for case in suite["cases"]
        if not selected_case_ids or case["case_id"] in selected_case_ids
    ]

    if selected_case_ids and len(suite_cases) != len(selected_case_ids):
        found = {case["case_id"] for case in suite_cases}
        missing = sorted(selected_case_ids - found)
        raise ValueError(f"unknown case_id(s): {missing}")

    case_summaries: list[dict[str, Any]] = []

    for index, suite_case in enumerate(suite_cases, start=1):
        case_id = suite_case["case_id"]
        dataset_path = _resolve_path(repo_root, suite_case["dataset_path"])
        _, evaluation_case = _single_case_dataset(
            dataset_path,
            case_id=case_id,
        )
        minimum_relevance = int(
            suite_case.get(
                "minimum_relevance",
                suite.get("default_scoring", {}).get("minimum_relevance", 2),
            )
        )

        if primary_dir is None:
            primary_path = _resolve_path(
                repo_root,
                suite_case["search_result_path"],
            )
        else:
            primary_path = _result_path(
                directory=primary_dir,
                pattern=args.primary_pattern,
                case_id=case_id,
                secondary_run_name=args.secondary_run_name,
            )
        secondary_path = _result_path(
            directory=secondary_dir,
            pattern=args.secondary_pattern,
            case_id=case_id,
            secondary_run_name=args.secondary_run_name,
        )

        print("=" * 100)
        print(f"[{index}/{len(suite_cases)}] hybrid case: {case_id}")
        print("=" * 100)
        print(f"query: {evaluation_case['query']}")
        print(f"candidate_count: {len(evaluation_case['candidate_paper_ids'])}")
        print(f"primary_result:   {primary_path}")
        print(f"secondary_result: {secondary_path}")

        primary = _load_json(primary_path)
        secondary = _load_json(secondary_path)

        hybrid = build_hybrid_result(
            primary_result=primary,
            secondary_result=secondary,
            primary_name=args.primary_name,
            secondary_name=args.secondary_name,
            primary_weight=args.primary_weight,
            secondary_weight=args.secondary_weight,
            final_paper_k=args.final_paper_k,
        )

        search_output_path = output_dir / f"{case_id}_{args.run_name}_search_output.json"
        metrics_path = output_dir / f"{case_id}_{args.run_name}_metrics.json"

        _write_json(search_output_path, hybrid)

        metrics = evaluate_saved_paper_ranking(
            dataset_path=dataset_path,
            search_result_path=search_output_path,
            case_id=case_id,
            k_values=(1, 3, 5, 10),
            minimum_relevance=minimum_relevance,
        )
        metrics_dict = asdict(metrics)
        _write_json(metrics_path, metrics_dict)

        k5 = _metric_at_k(metrics_dict, 5)
        case_summary = {
            "case_id": case_id,
            "query": metrics.query,
            "relevant_count": metrics.relevant_count,
            "retrieved_count": metrics.retrieved_count,
            "minimum_relevance": metrics.minimum_relevance,
            "reciprocal_rank": metrics.reciprocal_rank,
            "average_precision": metrics.average_precision,
            "precision_at_5": k5["precision"],
            "recall_at_5": k5["recall"],
            "ndcg_at_5": k5["ndcg"],
            "search_output_path": str(search_output_path),
            "metrics_path": str(metrics_path),
        }
        case_summaries.append(case_summary)

        print(
            "metrics: "
            f"MRR={metrics.reciprocal_rank:.4f} "
            f"AP={metrics.average_precision:.4f} "
            f"P@5={k5['precision']:.4f} "
            f"R@5={k5['recall']:.4f} "
            f"nDCG@5={k5['ndcg']:.4f}"
        )
        print(f"search_output: {search_output_path}")
        print(f"metrics_json:   {metrics_path}")

    summary = _build_suite_summary(
        suite_path=suite_path,
        output_dir=output_dir,
        run_name=args.run_name,
        primary_name=args.primary_name,
        secondary_name=args.secondary_name,
        primary_weight=args.primary_weight,
        secondary_weight=args.secondary_weight,
        case_summaries=case_summaries,
    )

    summary_path = output_dir / f"retrieval_suite_v1_{args.run_name}_summary.json"
    _write_json(summary_path, summary)

    macro = summary["macro"]
    weakest = summary["weakest"]

    print("=" * 100)
    print("Hybrid suite summary")
    print("=" * 100)
    print(f"run_name: {args.run_name}")
    print(f"case_count: {len(case_summaries)}")
    print(f"macro_mrr: {macro['macro_mrr']:.4f}")
    print(f"macro_ap: {macro['macro_ap']:.4f}")
    print(f"macro_precision_at_5: {macro['macro_precision_at_5']:.4f}")
    print(f"macro_recall_at_5: {macro['macro_recall_at_5']:.4f}")
    print(f"macro_ndcg_at_5: {macro['macro_ndcg_at_5']:.4f}")
    print(f"weakest_ap_case: {weakest['weakest_ap_case']}")
    print(f"weakest_ndcg_at_5_case: {weakest['weakest_ndcg_at_5_case']}")
    print(f"summary_json: {summary_path}")
    print("=" * 100)

    return summary


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()
    run_suite(args)


if __name__ == "__main__":
    main()
