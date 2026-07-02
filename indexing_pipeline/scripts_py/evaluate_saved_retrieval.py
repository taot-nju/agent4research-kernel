"""评估已保存的候选论文检索排序。"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from ai4research.indexing_pipeline.evaluation.runner import (
    evaluate_saved_paper_ranking,
)


DEFAULT_K_VALUES = (1, 3, 5, 10)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "读取人工标注的检索评估集和已保存的论文检索结果，"
            "计算 Precision、Recall、nDCG、MRR 与 AP。"
        )
    )
    parser.add_argument(
        "--dataset",
        required=True,
        help="检索评估数据集 JSON 路径",
    )
    parser.add_argument(
        "--search-result",
        required=True,
        help="已保存的候选全文检索结果 JSON 路径",
    )
    parser.add_argument(
        "--case-id",
        help="评估 case ID；数据集只有一个 case 时可以省略",
    )
    parser.add_argument(
        "--k",
        dest="k_values",
        action="append",
        type=int,
        help="评估截断位置，可重复传入；默认 1、3、5、10",
    )
    parser.add_argument(
        "--minimum-relevance",
        type=int,
        default=1,
        help="视为相关论文的最低等级，默认 1",
    )
    parser.add_argument(
        "--save-json",
        help="可选：保存完整评估报告 JSON",
    )
    return parser


def _save_json(path: str | Path, payload: dict[str, object]) -> Path:
    resolved_path = Path(path).expanduser().resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return resolved_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    k_values = tuple(args.k_values or DEFAULT_K_VALUES)
    result = evaluate_saved_paper_ranking(
        dataset_path=args.dataset,
        search_result_path=args.search_result,
        case_id=args.case_id,
        k_values=k_values,
        minimum_relevance=args.minimum_relevance,
    )
    payload = asdict(result)

    print("=" * 100)
    print("论文检索评估结果")
    print("=" * 100)
    print(f"case_id:             {result.case_id}")
    print(f"query:               {result.query}")
    print(f"candidate_count:     {result.candidate_count}")
    print(f"judged_count:        {result.judged_count}")
    print(f"relevant_count:      {result.relevant_count}")
    print(f"retrieved_count:     {result.retrieved_count}")
    print(f"minimum_relevance:   {result.minimum_relevance}")
    print(f"reciprocal_rank:     {result.reciprocal_rank:.4f}")
    print(f"average_precision:   {result.average_precision:.4f}")
    print("-" * 100)

    for item in result.metrics_at_k:
        print(
            f"k={item.k:<4} "
            f"precision={item.precision:.4f} "
            f"recall={item.recall:.4f} "
            f"ndcg={item.ndcg:.4f}"
        )

    print("-" * 100)
    print("ranked_paper_ids:")

    for rank, paper_id in enumerate(result.ranked_paper_ids, start=1):
        print(f"  {rank:>3}. {paper_id}")

    if args.save_json:
        saved_path = _save_json(args.save_json, payload)
        print("-" * 100)
        print(f"JSON report saved: {saved_path}")

    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
