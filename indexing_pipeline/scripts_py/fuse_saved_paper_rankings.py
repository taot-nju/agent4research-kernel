"""融合两个已保存的论文级检索结果。

这是 operator-facing CLI，用于手工测试 hybrid retrieval。

输入：
- 一个 primary search result JSON，例如 BM25；
- 一个 secondary search result JSON，例如 vector；

输出：
- 一个 hybrid search result JSON；
- 结构兼容 evaluate_saved_retrieval。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="融合两个已保存的论文级检索结果，生成可评估的 hybrid search JSON。"
    )
    parser.add_argument(
        "--primary-result",
        required=True,
        help="primary search result JSON，例如 BM25",
    )
    parser.add_argument(
        "--secondary-result",
        required=True,
        help="secondary search result JSON，例如 vector",
    )
    parser.add_argument(
        "--primary-name",
        default="primary",
        help="primary 结果名称，默认 primary",
    )
    parser.add_argument(
        "--secondary-name",
        default="secondary",
        help="secondary 结果名称，默认 secondary",
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
        help="输出论文数，默认 10",
    )
    parser.add_argument(
        "--save-json",
        required=True,
        help="保存 hybrid search result JSON 的路径",
    )
    return parser.parse_args()


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def _write_json(path: str | Path, data: dict[str, Any]) -> Path:
    resolved = Path(path).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return resolved


def _paper_hits(result: dict[str, Any]) -> list[dict[str, Any]]:
    return list(result.get("paper_search_result", {}).get("hits", []))


def _relative_scores(hits: list[dict[str, Any]]) -> dict[str, float]:
    if not hits:
        return {}

    max_score = max(float(hit.get("score", 0.0)) for hit in hits)
    min_score = min(float(hit.get("score", 0.0)) for hit in hits)

    if max_score == min_score:
        return {
            str(hit["paper_id"]): 1.0
            for hit in hits
        }

    return {
        str(hit["paper_id"]): (
            (float(hit.get("score", 0.0)) - min_score)
            / (max_score - min_score)
        )
        for hit in hits
    }


def _rank_scores(hits: list[dict[str, Any]]) -> dict[str, float]:
    if not hits:
        return {}

    n = len(hits)
    if n == 1:
        return {
            str(hits[0]["paper_id"]): 1.0
        }

    return {
        str(hit["paper_id"]): 1.0 - ((rank - 1) / (n - 1))
        for rank, hit in enumerate(hits, start=1)
    }


def _hit_by_paper(hits: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(hit["paper_id"]): hit
        for hit in hits
    }


def build_hybrid_result(
    *,
    primary_result: dict[str, Any],
    secondary_result: dict[str, Any],
    primary_name: str,
    secondary_name: str,
    primary_weight: float,
    secondary_weight: float,
    final_paper_k: int,
) -> dict[str, Any]:
    if final_paper_k <= 0:
        raise ValueError("final_paper_k must be positive")
    if primary_weight < 0 or secondary_weight < 0:
        raise ValueError("fusion weights must be non-negative")
    if primary_weight + secondary_weight <= 0:
        raise ValueError("at least one fusion weight must be positive")

    primary_hits = _paper_hits(primary_result)
    secondary_hits = _paper_hits(secondary_result)

    primary_relative = _relative_scores(primary_hits)
    secondary_relative = _relative_scores(secondary_hits)
    primary_rank = _rank_scores(primary_hits)
    secondary_rank = _rank_scores(secondary_hits)

    primary_by_paper = _hit_by_paper(primary_hits)
    secondary_by_paper = _hit_by_paper(secondary_hits)

    paper_ids = sorted(
        set(primary_by_paper) | set(secondary_by_paper)
    )

    fused_items = []
    for paper_id in paper_ids:
        p_score = primary_relative.get(paper_id, 0.0)
        s_score = secondary_relative.get(paper_id, 0.0)
        p_rank_score = primary_rank.get(paper_id, 0.0)
        s_rank_score = secondary_rank.get(paper_id, 0.0)

        fused_score = (
            primary_weight * p_score
            + secondary_weight * s_score
        )
        fused_rank_score = (
            primary_weight * p_rank_score
            + secondary_weight * s_rank_score
        )

        evidence = []
        if paper_id in primary_by_paper:
            evidence.append({
                "source": primary_name,
                "hit": primary_by_paper[paper_id],
            })
        if paper_id in secondary_by_paper:
            evidence.append({
                "source": secondary_name,
                "hit": secondary_by_paper[paper_id],
            })

        fused_items.append(
            {
                "paper_id": paper_id,
                "score": fused_score,
                "rank_score": fused_rank_score,
                "score_components": {
                    f"{primary_name}_relative_score": p_score,
                    f"{secondary_name}_relative_score": s_score,
                    f"{primary_name}_rank_score": p_rank_score,
                    f"{secondary_name}_rank_score": s_rank_score,
                    "primary_weight": primary_weight,
                    "secondary_weight": secondary_weight,
                },
                "evidence": evidence,
            }
        )

    fused_items.sort(
        key=lambda item: (
            item["score"],
            item["rank_score"],
            item["paper_id"],
        ),
        reverse=True,
    )

    hits = []
    for rank, item in enumerate(fused_items[:final_paper_k], start=1):
        hits.append({
            "rank": rank,
            "paper_id": item["paper_id"],
            "score": item["score"],
            "score_components": item["score_components"],
            "evidence": item["evidence"],
        })

    return {
        "success": True,
        "status": "complete",
        "query": primary_result.get("query", secondary_result.get("query", "")),
        "requested_paper_ids": primary_result.get(
            "requested_paper_ids",
            secondary_result.get("requested_paper_ids", []),
        ),
        "loaded_paper_ids": primary_result.get(
            "loaded_paper_ids",
            secondary_result.get("loaded_paper_ids", []),
        ),
        "missing_paper_ids": sorted(
            set(primary_result.get("missing_paper_ids", []))
            | set(secondary_result.get("missing_paper_ids", []))
        ),
        "paper_search_result": {
            "query": primary_result.get("query", secondary_result.get("query", "")),
            "chunk_retriever_name": "hybrid-fusion",
            "chunk_retriever_version": "1",
            "corpus_paper_count": len(paper_ids),
            "corpus_chunk_count": 0,
            "matched_paper_count": len(hits),
            "hits": hits,
            "fusion_config": {
                "primary_name": primary_name,
                "secondary_name": secondary_name,
                "primary_weight": primary_weight,
                "secondary_weight": secondary_weight,
                "final_paper_k": final_paper_k,
                "score_normalization": "minmax_per_result_set",
                "rank_score": "linear_rank_score_tiebreaker",
            },
        },
        "errors": {},
    }


def print_result(result: dict[str, Any]) -> None:
    print("=" * 100)
    print("Hybrid paper ranking")
    print("=" * 100)
    print(f"query: {result['query']}")
    print("-" * 100)

    for hit in result["paper_search_result"]["hits"]:
        print(f"rank={hit['rank']} score={hit['score']:.4f}")
        print(f"paper_id: {hit['paper_id']}")
        print(f"components: {hit['score_components']}")
        print("-" * 100)

    print("=" * 100)


def main() -> None:
    args = parse_args()

    primary = _load_json(args.primary_result)
    secondary = _load_json(args.secondary_result)

    result = build_hybrid_result(
        primary_result=primary,
        secondary_result=secondary,
        primary_name=args.primary_name,
        secondary_name=args.secondary_name,
        primary_weight=args.primary_weight,
        secondary_weight=args.secondary_weight,
        final_paper_k=args.final_paper_k,
    )

    print_result(result)
    saved_path = _write_json(args.save_json, result)
    print(f"JSON report saved: {saved_path}")


if __name__ == "__main__":
    main()
