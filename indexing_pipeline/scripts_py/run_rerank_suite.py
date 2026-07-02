"""逐 case 对已保存 hybrid ranking 执行 rerank，并评估 retrieval suite。"""

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
from ai4research.indexing_pipeline.scripts_py.rerank_hybrid_candidates import (
    build_result,
)
from ai4research.indexing_pipeline.scripts_py.rerank_texts import (
    DEFAULT_API_KEY,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
)


DEFAULT_SUITE = (
    "~/ai4research/evaluation_datasets/retrieval/"
    "retrieval_suite_v1.json"
)
DEFAULT_HYBRID_RUN_NAME = (
    "bm25_bge_m3_subchunk_w070_030"
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "读取 retrieval suite，逐 case 对已保存 hybrid "
            "paper ranking 执行 rerank，保存 search output、"
            "metrics 和 suite summary。"
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
        help=(
            "用于解析 suite 内相对路径的项目根目录，"
            "默认 ~/ai4research"
        ),
    )
    parser.add_argument(
        "--hybrid-result-dir",
        required=True,
        help="输入 hybrid search output 所在目录",
    )
    parser.add_argument(
        "--hybrid-pattern",
        default=(
            "{case_id}_{hybrid_run_name}_"
            "search_output.json"
        ),
        help=(
            "hybrid 文件名模式，支持 {case_id} "
            "和 {hybrid_run_name}"
        ),
    )
    parser.add_argument(
        "--hybrid-run-name",
        default=DEFAULT_HYBRID_RUN_NAME,
        help=(
            "hybrid 文件名中的 run name，默认 "
            "bm25_bge_m3_subchunk_w070_030"
        ),
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="rerank suite 输出目录",
    )
    parser.add_argument(
        "--run-name",
        default="bge_m3_rerank",
        help="输出文件名前缀，默认 bge_m3_rerank",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=(
            "OpenAI-compatible 服务 base URL；默认读取 "
            "AI4RESEARCH_RERANK_BASE_URL，随后回退 "
            "embedding 配置"
        ),
    )
    parser.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY,
        help=(
            "服务 API key；默认读取 "
            "AI4RESEARCH_RERANK_API_KEY，随后回退 "
            "embedding 配置"
        ),
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=(
            "rerank 模型；默认读取 "
            "AI4RESEARCH_RERANK_MODEL，随后回退 "
            "embedding 模型配置"
        ),
    )
    parser.add_argument(
        "--candidate-paper-k",
        type=int,
        default=10,
        help="每个 case 从 hybrid 排名取前多少篇进入 rerank，默认 10",
    )
    parser.add_argument(
        "--final-paper-k",
        type=int,
        default=10,
        help="每个 case 最终输出论文数，默认 10",
    )
    parser.add_argument(
        "--subchunk-max-chars",
        type=int,
        default=3200,
        help=(
            "超过该字符数的 evidence chunk 会完整切成 "
            "rerank segment，默认 3200"
        ),
    )
    parser.add_argument(
        "--subchunk-overlap-chars",
        type=int,
        default=200,
        help="rerank segment 之间的重叠字符数，默认 200",
    )
    parser.add_argument(
        "--top-source-chunks-for-score",
        type=int,
        default=3,
        help=(
            "每篇论文取多少个不同原始 chunk 的最高分"
            "做平均聚合，默认 3"
        ),
    )
    parser.add_argument(
        "--rerank-batch-size",
        type=int,
        default=16,
        help="每次 /v1/rerank 请求包含的 segment 数，默认 16",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="单次 HTTP 请求超时秒数，默认 60",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=220,
        help="evidence 文本预览字符数，默认 220",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        help=(
            "只运行指定 case；可重复传入。"
            "默认运行 suite 中所有 case"
        ),
    )
    return parser


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError(f"JSON object expected: {path}")

    return data


def _write_json(
    path: Path,
    data: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _resolve_path(
    repo_root: Path,
    path_text: str,
) -> Path:
    path = Path(path_text).expanduser()

    if path.is_absolute():
        return path

    return repo_root / path


def _safe_name(value: str) -> str:
    return (
        value.strip()
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace(" ", "_")
        .replace("-", "_")
    )


def _single_case_dataset(
    dataset_path: Path,
    *,
    case_id: str,
) -> dict[str, Any]:
    dataset = _load_json(dataset_path)
    cases = dataset.get("cases", [])
    matched = [
        case
        for case in cases
        if case.get("case_id") == case_id
    ]

    if len(matched) != 1:
        raise ValueError(
            "expected exactly one evaluation case "
            f"in {dataset_path}, got {len(matched)}"
        )

    return matched[0]


def _metric_at_k(
    metrics: dict[str, Any],
    k: int,
) -> dict[str, Any]:
    for item in metrics["metrics_at_k"]:
        if int(item["k"]) == k:
            return item

    raise ValueError(f"metrics 缺少 k={k}")


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _hybrid_result_path(
    *,
    directory: Path,
    pattern: str,
    case_id: str,
    hybrid_run_name: str,
) -> Path:
    filename = pattern.format(
        case_id=case_id,
        hybrid_run_name=hybrid_run_name,
    )
    return directory / filename


def _rerank_args(
    *,
    args: argparse.Namespace,
) -> SimpleNamespace:
    return SimpleNamespace(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        candidate_paper_k=args.candidate_paper_k,
        final_paper_k=args.final_paper_k,
        subchunk_max_chars=args.subchunk_max_chars,
        subchunk_overlap_chars=(
            args.subchunk_overlap_chars
        ),
        top_source_chunks_for_score=(
            args.top_source_chunks_for_score
        ),
        rerank_batch_size=args.rerank_batch_size,
        timeout_seconds=args.timeout_seconds,
        preview_chars=args.preview_chars,
    )


def _build_suite_summary(
    *,
    suite_path: Path,
    output_dir: Path,
    run_name: str,
    args: argparse.Namespace,
    case_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    macro = {
        "macro_mrr": _mean([
            case["reciprocal_rank"]
            for case in case_summaries
        ]),
        "macro_ap": _mean([
            case["average_precision"]
            for case in case_summaries
        ]),
        "macro_precision_at_5": _mean([
            case["precision_at_5"]
            for case in case_summaries
        ]),
        "macro_recall_at_5": _mean([
            case["recall_at_5"]
            for case in case_summaries
        ]),
        "macro_ndcg_at_5": _mean([
            case["ndcg_at_5"]
            for case in case_summaries
        ]),
    }

    return {
        "name": (
            "ai4research-retrieval-suite-"
            f"{run_name}-summary"
        ),
        "version": 1,
        "suite_path": str(suite_path),
        "output_dir": str(output_dir),
        "run_name": run_name,
        "rerank_config": {
            "model": args.model,
            "candidate_paper_k": (
                args.candidate_paper_k
            ),
            "final_paper_k": args.final_paper_k,
            "subchunk_max_chars": (
                args.subchunk_max_chars
            ),
            "subchunk_overlap_chars": (
                args.subchunk_overlap_chars
            ),
            "top_source_chunks_for_score": (
                args.top_source_chunks_for_score
            ),
            "rerank_batch_size": (
                args.rerank_batch_size
            ),
            "paper_score": (
                "mean_of_top_distinct_source_chunks"
            ),
        },
        "case_count": len(case_summaries),
        "cases": case_summaries,
        "macro": macro,
        "weakest": {
            "weakest_ap_case": min(
                case_summaries,
                key=lambda case: (
                    case["average_precision"]
                ),
            )["case_id"],
            "weakest_ndcg_at_5_case": min(
                case_summaries,
                key=lambda case: (
                    case["ndcg_at_5"]
                ),
            )["case_id"],
        },
        "notes": [
            "This summary is generated by "
            "run_rerank_suite.py.",
            "Rerank scores evaluate fulltext "
            "reranking inside each case's "
            "metadata candidate set.",
        ],
    }


def run_suite(
    args: argparse.Namespace,
) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    suite_path = Path(args.suite).expanduser().resolve()
    hybrid_result_dir = Path(
        args.hybrid_result_dir
    ).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    suite = _load_json(suite_path)
    run_name = _safe_name(args.run_name)

    if not run_name:
        raise ValueError("run_name 不能为空")

    selected_case_ids = set(args.case_id or [])
    suite_cases = [
        case
        for case in suite["cases"]
        if (
            not selected_case_ids
            or case["case_id"] in selected_case_ids
        )
    ]

    if (
        selected_case_ids
        and len(suite_cases) != len(selected_case_ids)
    ):
        found = {
            case["case_id"]
            for case in suite_cases
        }
        missing = sorted(selected_case_ids - found)
        raise ValueError(
            f"unknown case_id(s): {missing}"
        )

    case_summaries: list[dict[str, Any]] = []

    for index, suite_case in enumerate(
        suite_cases,
        start=1,
    ):
        case_id = suite_case["case_id"]
        dataset_path = _resolve_path(
            repo_root,
            suite_case["dataset_path"],
        )
        evaluation_case = _single_case_dataset(
            dataset_path,
            case_id=case_id,
        )
        minimum_relevance = int(
            suite_case.get(
                "minimum_relevance",
                suite.get(
                    "default_scoring",
                    {},
                ).get("minimum_relevance", 2),
            )
        )
        hybrid_path = _hybrid_result_path(
            directory=hybrid_result_dir,
            pattern=args.hybrid_pattern,
            case_id=case_id,
            hybrid_run_name=args.hybrid_run_name,
        )

        print("=" * 100)
        print(
            f"[{index}/{len(suite_cases)}] "
            f"rerank case: {case_id}"
        )
        print("=" * 100)
        print(f"model: {args.model}")
        print(f"run_name: {run_name}")
        print(
            f"query: {evaluation_case['query']}"
        )
        print(
            "candidate_count: "
            f"{len(evaluation_case['candidate_paper_ids'])}"
        )
        print(f"hybrid_result: {hybrid_path}")

        hybrid_result = _load_json(hybrid_path)
        reranked_result = build_result(
            hybrid_result=hybrid_result,
            args=_rerank_args(args=args),
        )

        search_output_path = (
            output_dir
            / f"{case_id}_{run_name}_search_output.json"
        )
        metrics_path = (
            output_dir
            / f"{case_id}_{run_name}_metrics.json"
        )

        _write_json(
            search_output_path,
            reranked_result,
        )

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
            "case_id": metrics.case_id,
            "query": metrics.query,
            "minimum_relevance": (
                metrics.minimum_relevance
            ),
            "candidate_count": metrics.candidate_count,
            "judged_count": metrics.judged_count,
            "relevant_count": metrics.relevant_count,
            "retrieved_count": metrics.retrieved_count,
            "reciprocal_rank": (
                metrics.reciprocal_rank
            ),
            "average_precision": (
                metrics.average_precision
            ),
            "precision_at_5": k5["precision"],
            "recall_at_5": k5["recall"],
            "ndcg_at_5": k5["ndcg"],
            "hybrid_result_path": str(hybrid_path),
            "search_output_path": str(
                search_output_path
            ),
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
        run_name=run_name,
        args=args,
        case_summaries=case_summaries,
    )
    summary_path = (
        output_dir
        / f"retrieval_suite_v1_{run_name}_summary.json"
    )
    _write_json(summary_path, summary)

    macro = summary["macro"]
    weakest = summary["weakest"]

    print("=" * 100)
    print("Rerank suite summary")
    print("=" * 100)
    print(f"model: {args.model}")
    print(f"run_name: {run_name}")
    print(f"case_count: {summary['case_count']}")
    print(f"macro_mrr: {macro['macro_mrr']:.4f}")
    print(f"macro_ap: {macro['macro_ap']:.4f}")
    print(
        "macro_precision_at_5: "
        f"{macro['macro_precision_at_5']:.4f}"
    )
    print(
        "macro_recall_at_5: "
        f"{macro['macro_recall_at_5']:.4f}"
    )
    print(
        "macro_ndcg_at_5: "
        f"{macro['macro_ndcg_at_5']:.4f}"
    )
    print(
        f"weakest_ap_case: "
        f"{weakest['weakest_ap_case']}"
    )
    print(
        "weakest_ndcg_at_5_case: "
        f"{weakest['weakest_ndcg_at_5_case']}"
    )
    print(f"summary_json: {summary_path}")
    print("=" * 100)

    return summary


def main() -> None:
    args = build_argument_parser().parse_args()
    run_suite(args)


if __name__ == "__main__":
    main()
