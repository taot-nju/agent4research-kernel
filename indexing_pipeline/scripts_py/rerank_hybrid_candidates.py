"""对已保存 hybrid paper ranking 执行 bge-m3 chunk-level rerank。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from ai4research.indexing_pipeline.reranking import (
    RerankSegment,
    ScoredRerankSegment,
    aggregate_reranked_segments,
    build_rerank_segments,
)
from ai4research.indexing_pipeline.scripts_py.rerank_texts import (
    DEFAULT_API_KEY,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    _post_rerank,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "读取已保存的 hybrid 论文排序，"
            "对其 evidence chunk 执行 OpenAI-compatible rerank，"
            "再聚合为可评估的论文级排序。"
        )
    )
    parser.add_argument(
        "--hybrid-result",
        required=True,
        help="已保存的 hybrid search result JSON 路径",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=(
            "OpenAI-compatible 服务 base URL；默认读取 "
            "AI4RESEARCH_RERANK_BASE_URL，随后回退 embedding 配置"
        ),
    )
    parser.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY,
        help=(
            "服务 API key；默认读取 "
            "AI4RESEARCH_RERANK_API_KEY，"
            "随后回退 embedding 配置"
        ),
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=(
            "rerank 模型；默认读取 "
            "AI4RESEARCH_RERANK_MODEL，"
            "随后回退 embedding 模型配置"
        ),
    )
    parser.add_argument(
        "--candidate-paper-k",
        type=int,
        default=10,
        help="从 hybrid 排名取前多少篇论文进入 rerank，默认 10",
    )
    parser.add_argument(
        "--final-paper-k",
        type=int,
        default=10,
        help="最终输出多少篇论文，默认 10",
    )
    parser.add_argument(
        "--subchunk-max-chars",
        type=int,
        default=3200,
        help=(
            "超过该字符数的 evidence chunk 会完整切成 "
            "rerank segment；默认 3200"
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
        help="终端与 JSON evidence 的文本预览字符数，默认 220",
    )
    parser.add_argument(
        "--save-json",
        required=True,
        help="保存 reranked search result JSON 的路径",
    )
    return parser.parse_args()


def _load_json(path: str) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    data = json.loads(
        resolved.read_text(encoding="utf-8")
    )

    if not isinstance(data, dict):
        raise ValueError(
            "hybrid result 必须是 JSON object"
        )

    return data


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


def _preview(text: str, limit: int) -> str:
    normalized = " ".join(text.split())

    if len(normalized) <= limit:
        return normalized

    return normalized[:limit] + "..."


def _score_segments(
    *,
    query: str,
    segments: Sequence[RerankSegment],
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: int,
    batch_size: int,
) -> tuple[ScoredRerankSegment, ...]:
    if batch_size <= 0:
        raise ValueError(
            "rerank_batch_size 必须大于 0"
        )

    scored: list[ScoredRerankSegment] = []

    for start in range(0, len(segments), batch_size):
        batch = segments[start : start + batch_size]
        response = _post_rerank(
            base_url=base_url,
            api_key=api_key,
            model=model,
            query=query,
            documents=[
                segment.text
                for segment in batch
            ],
            timeout_seconds=timeout_seconds,
        )
        raw_results = response.get("results")

        if not isinstance(raw_results, list):
            raise ValueError(
                "rerank response 缺少 results list"
            )

        scores_by_index: dict[int, float] = {}

        for item in raw_results:
            if not isinstance(item, dict):
                raise ValueError(
                    "rerank result 必须是 object"
                )

            index = int(item["index"])

            if index < 0 or index >= len(batch):
                raise ValueError(
                    "rerank result index 超出 batch 范围"
                )

            if index in scores_by_index:
                raise ValueError(
                    "rerank result 出现重复 index"
                )

            scores_by_index[index] = float(
                item["relevance_score"]
            )

        expected_indices = set(range(len(batch)))

        if set(scores_by_index) != expected_indices:
            raise ValueError(
                "rerank response 未覆盖 batch 的全部 segment"
            )

        for index, segment in enumerate(batch):
            scored.append(
                ScoredRerankSegment(
                    segment=segment,
                    relevance_score=(
                        scores_by_index[index]
                    ),
                )
            )

    return tuple(scored)


def build_result(
    *,
    hybrid_result: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    query = str(
        hybrid_result.get("query", "")
    ).strip()

    if not query:
        raise ValueError(
            "hybrid result 缺少 query"
        )

    if args.candidate_paper_k <= 0:
        raise ValueError(
            "candidate_paper_k 必须大于 0"
        )

    if args.final_paper_k <= 0:
        raise ValueError(
            "final_paper_k 必须大于 0"
        )

    if args.timeout_seconds <= 0:
        raise ValueError(
            "timeout_seconds 必须大于 0"
        )

    if args.preview_chars < 0:
        raise ValueError(
            "preview_chars 不能小于 0"
        )

    segments = build_rerank_segments(
        hybrid_result=hybrid_result,
        candidate_paper_k=args.candidate_paper_k,
        subchunk_max_chars=args.subchunk_max_chars,
        subchunk_overlap_chars=(
            args.subchunk_overlap_chars
        ),
    )

    if not segments:
        raise ValueError(
            "hybrid result 没有可 rerank 的 evidence chunk"
        )

    scored_segments = _score_segments(
        query=query,
        segments=segments,
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model.strip(),
        timeout_seconds=args.timeout_seconds,
        batch_size=args.rerank_batch_size,
    )
    reranked_papers = aggregate_reranked_segments(
        scored_segments=scored_segments,
        top_source_chunks_for_score=(
            args.top_source_chunks_for_score
        ),
    )

    paper_result = hybrid_result.get(
        "paper_search_result",
        {},
    )
    original_hits = paper_result.get("hits", [])
    original_ranks = {
        str(hit.get("paper_id", "")): int(
            hit.get("rank", 0)
        )
        for hit in original_hits
        if isinstance(hit, dict)
    }

    hits: list[dict[str, Any]] = []

    for rank, paper in enumerate(
        reranked_papers[: args.final_paper_k],
        start=1,
    ):
        evidence = []

        for evidence_rank, scored in enumerate(
            paper.evidence,
            start=1,
        ):
            segment = scored.segment
            evidence.append(
                {
                    "rank": evidence_rank,
                    "score": scored.relevance_score,
                    "chunk": dict(segment.chunk),
                    "preview": _preview(
                        segment.text,
                        args.preview_chars,
                    ),
                    "rerank": {
                        "segment_id": segment.segment_id,
                        "source_chunk_id": (
                            segment.source_chunk_id
                        ),
                        "segment_index": (
                            segment.segment_index
                        ),
                        "segment_count": (
                            segment.segment_count
                        ),
                        "char_start": segment.char_start,
                        "char_end": segment.char_end,
                        "sources": list(segment.sources),
                    },
                }
            )

        hits.append(
            {
                "rank": rank,
                "paper_id": paper.paper_id,
                "score": paper.score,
                "score_components": {
                    "rerank_score": paper.score,
                    "original_hybrid_rank": (
                        original_ranks.get(
                            paper.paper_id,
                            0,
                        )
                    ),
                    "top_source_chunks_for_score": (
                        args.top_source_chunks_for_score
                    ),
                },
                "evidence": evidence,
            }
        )

    requested_paper_ids = hybrid_result.get(
        "requested_paper_ids",
        [],
    )
    loaded_paper_ids = hybrid_result.get(
        "loaded_paper_ids",
        [],
    )

    return {
        "success": True,
        "status": "complete",
        "query": query,
        "requested_paper_ids": requested_paper_ids,
        "loaded_paper_ids": loaded_paper_ids,
        "missing_paper_ids": hybrid_result.get(
            "missing_paper_ids",
            [],
        ),
        "paper_search_result": {
            "query": query,
            "chunk_retriever_name": (
                "openai-compatible-rerank"
            ),
            "chunk_retriever_version": "1",
            "corpus_paper_count": min(
                args.candidate_paper_k,
                len(original_hits),
            ),
            "corpus_chunk_count": len(segments),
            "matched_paper_count": len(hits),
            "hits": hits,
            "rerank_config": {
                "model": args.model.strip(),
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
        },
        "errors": {},
    }


def print_result(
    *,
    result: dict[str, Any],
) -> None:
    paper_result = result["paper_search_result"]

    print("=" * 100)
    print("Reranked hybrid paper ranking")
    print("=" * 100)
    print(f"query: {result['query']}")
    print(
        "rerank_segment_count: "
        + str(paper_result["corpus_chunk_count"])
    )
    print("-" * 100)

    for hit in paper_result["hits"]:
        print(
            f"rank={hit['rank']} "
            f"score={hit['score']:.6f} "
            f"paper_id={hit['paper_id']} "
            f"original_hybrid_rank="
            f"{hit['score_components']['original_hybrid_rank']}"
        )

        for evidence in hit["evidence"]:
            rerank = evidence["rerank"]
            print(
                "  evidence "
                f"score={evidence['score']:.6f} "
                f"chunk_id={rerank['source_chunk_id']} "
                f"segment="
                f"{rerank['segment_index'] + 1}/"
                f"{rerank['segment_count']}"
            )

    print("=" * 100)


def main() -> int:
    args = parse_args()
    hybrid_result = _load_json(args.hybrid_result)
    result = build_result(
        hybrid_result=hybrid_result,
        args=args,
    )
    print_result(result=result)
    saved_path = _write_json(
        path=args.save_json,
        payload=result,
    )
    print(f"JSON report saved: {saved_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
