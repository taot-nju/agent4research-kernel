"""在一组候选论文的 chunk 资产中执行当前推荐的 hybrid 检索。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence

from ai4research.indexing_pipeline.pipelines.candidate_fulltext_search import (
    CandidateFullTextSearchRequest,
    search_candidate_fulltext,
)
from ai4research.indexing_pipeline.repositories.jsonl_reader import (
    JsonlChunkCorpusReader,
)
from ai4research.indexing_pipeline.retrieval.bm25 import (
    BM25ChunkRetriever,
    BM25ChunkRetrieverConfig,
)
from ai4research.indexing_pipeline.retrieval.paper_aggregation import (
    PaperAggregationConfig,
    PaperScoreAggregator,
)
from ai4research.indexing_pipeline.scripts_py.fuse_saved_paper_rankings import (
    build_hybrid_result,
)
from ai4research.indexing_pipeline.scripts_py.search_candidate_vector_demo import (
    DEFAULT_SPLITTER_NAME,
    DEFAULT_SPLITTER_VERSION,
    build_result as build_vector_result,
)
from ai4research.indexing_pipeline.splitters.markdown_block_splitter import (
    MarkdownBlockSplitter,
    MarkdownBlockSplitterConfig,
)


DEFAULT_EMBEDDING_CACHE_DIR = (
    "/tmp/ai4research_hybrid_candidate_embeddings"
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "在一组候选论文的 chunk 资产中执行当前推荐的 "
            "BM25 0.7 + bge-m3 subchunk vector 0.3 hybrid "
            "检索，返回论文级排序与 evidence。"
        )
    )
    parser.add_argument(
        "--query",
        required=True,
        help="检索 query",
    )
    parser.add_argument(
        "--paper-id",
        action="append",
        required=True,
        help="候选 paper ID；可重复传入多次",
    )
    parser.add_argument(
        "--data-root",
        default="/data/ai4research_assets",
        help="资产根目录，默认 /data/ai4research_assets",
    )
    parser.add_argument(
        "--target-chars",
        type=int,
        default=2400,
        help="chunk splitter target_chars，默认 2400",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=3200,
        help="chunk splitter max_chars，默认 3200",
    )
    parser.add_argument(
        "--overlap-chars",
        type=int,
        default=300,
        help="chunk splitter overlap_chars，默认 300",
    )
    parser.add_argument(
        "--min-chars-before-heading-break",
        type=int,
        default=800,
        help=(
            "chunk splitter "
            "min_chars_before_heading_break，默认 800"
        ),
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
        "--bm25-k1",
        type=float,
        default=1.5,
        help="BM25 k1，默认 1.5",
    )
    parser.add_argument(
        "--bm25-b",
        type=float,
        default=0.75,
        help="BM25 b，默认 0.75",
    )
    parser.add_argument(
        "--section-term-multiplier",
        type=int,
        default=2,
        help="BM25 section term multiplier，默认 2",
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
            "/tmp/ai4research_hybrid_candidate_embeddings"
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
        "--bm25-weight",
        type=float,
        default=0.7,
        help="BM25 融合权重，默认推荐值 0.7",
    )
    parser.add_argument(
        "--vector-weight",
        type=float,
        default=0.3,
        help="bge-m3 vector 融合权重，默认推荐值 0.3",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=220,
        help="终端 evidence 文本预览字符数，默认 220",
    )
    parser.add_argument(
        "--save-json",
        help="可选：保存完整 hybrid search result JSON",
    )
    return parser


def _normalized_paper_ids(
    paper_ids: Sequence[str],
) -> tuple[str, ...]:
    normalized = tuple(
        dict.fromkeys(
            paper_id.strip()
            for paper_id in paper_ids
            if paper_id.strip()
        )
    )

    if not normalized:
        raise ValueError(
            "至少需要一个非空 paper_id"
        )

    return normalized


def _build_bm25_result(
    *,
    args: argparse.Namespace,
    paper_ids: tuple[str, ...],
) -> dict[str, Any]:
    splitter = MarkdownBlockSplitter(
        MarkdownBlockSplitterConfig(
            target_chars=args.target_chars,
            max_chars=args.max_chars,
            overlap_chars=args.overlap_chars,
            min_chars_before_heading_break=(
                args.min_chars_before_heading_break
            ),
        )
    )
    chunk_retriever = BM25ChunkRetriever(
        BM25ChunkRetrieverConfig(
            k1=args.bm25_k1,
            b=args.bm25_b,
            section_term_multiplier=(
                args.section_term_multiplier
            ),
        )
    )
    aggregator = PaperScoreAggregator(
        PaperAggregationConfig(
            top_chunks_for_score=(
                args.top_chunks_for_score
            ),
            evidence_chunks_per_paper=(
                args.evidence_chunks_per_paper
            ),
        )
    )
    request = CandidateFullTextSearchRequest(
        query=args.query,
        candidate_paper_ids=paper_ids,
        splitter_name=splitter.name,
        splitter_version=splitter.version,
        splitter_options=splitter.options,
        chunk_recall_limit=args.chunk_recall_k,
        final_paper_limit=args.final_paper_k,
    )
    result = search_candidate_fulltext(
        request=request,
        corpus_reader=JsonlChunkCorpusReader(),
        chunk_retriever=chunk_retriever,
        paper_aggregator=aggregator,
    )

    if not result.success:
        raise RuntimeError(
            "BM25 candidate search failed: "
            + str(result.error)
        )

    return result.to_dict()


def _vector_args(
    *,
    args: argparse.Namespace,
    paper_ids: tuple[str, ...],
) -> SimpleNamespace:
    return SimpleNamespace(
        query=args.query,
        paper_id=list(paper_ids),
        data_root=args.data_root,
        splitter_name=DEFAULT_SPLITTER_NAME,
        splitter_version=DEFAULT_SPLITTER_VERSION,
        target_chars=args.target_chars,
        max_chars=args.max_chars,
        overlap_chars=args.overlap_chars,
        min_chars_before_heading_break=(
            args.min_chars_before_heading_break
        ),
        provider="openai-compatible",
        embedding_dim=args.embedding_dim,
        embedding_input_max_chars=0,
        subchunk_max_chars=args.subchunk_max_chars,
        subchunk_overlap_chars=(
            args.subchunk_overlap_chars
        ),
        chunk_recall_k=args.chunk_recall_k,
        final_paper_k=args.final_paper_k,
        evidence_chunks_per_paper=(
            args.evidence_chunks_per_paper
        ),
        top_chunks_for_score=(
            args.top_chunks_for_score
        ),
        preview_chars=args.preview_chars,
        embedding_cache_dir=(
            args.embedding_cache_dir
        ),
        reuse_embeddings=args.reuse_embeddings,
        save_json=None,
    )


def build_result(
    *,
    args: argparse.Namespace,
) -> dict[str, Any]:
    paper_ids = _normalized_paper_ids(args.paper_id)

    if not args.query.strip():
        raise ValueError("query 不能为空")

    if args.preview_chars <= 0:
        raise ValueError(
            "preview_chars 必须大于 0"
        )

    bm25_result = _build_bm25_result(
        args=args,
        paper_ids=paper_ids,
    )
    vector_result = build_vector_result(
        args=_vector_args(
            args=args,
            paper_ids=paper_ids,
        )
    )
    hybrid_result = build_hybrid_result(
        primary_result=bm25_result,
        secondary_result=vector_result,
        primary_name="bm25",
        secondary_name="bge-m3",
        primary_weight=args.bm25_weight,
        secondary_weight=args.vector_weight,
        final_paper_k=args.final_paper_k,
    )

    hybrid_result["hybrid_execution"] = {
        "strategy": (
            "bm25_bge_m3_subchunk_hybrid"
        ),
        "bm25_weight": args.bm25_weight,
        "vector_weight": args.vector_weight,
        "embedding_provider": "openai-compatible",
        "embedding_model": vector_result[
            "embedding_provider"
        ]["embedding_model"],
        "embedding_dimension": vector_result[
            "embedding_provider"
        ]["embedding_dimension"],
        "subchunk_max_chars": (
            args.subchunk_max_chars
        ),
        "subchunk_overlap_chars": (
            args.subchunk_overlap_chars
        ),
        "embedding_cache_dir": (
            args.embedding_cache_dir
        ),
    }

    return hybrid_result


def _preview(text: str, limit: int) -> str:
    normalized = " ".join(text.split())

    if len(normalized) <= limit:
        return normalized

    return normalized[:limit] + "..."


def print_result(
    *,
    result: dict[str, Any],
    preview_chars: int,
) -> None:
    paper_result = result["paper_search_result"]
    execution = result["hybrid_execution"]

    print("=" * 100)
    print("Recommended hybrid candidate paper ranking")
    print("=" * 100)
    print(f"query: {result['query']}")
    print(
        "requested_papers: "
        + str(len(result["requested_paper_ids"]))
    )
    print(
        "loaded_papers:    "
        + str(len(result["loaded_paper_ids"]))
    )
    print(
        "missing_papers:   "
        + str(len(result["missing_paper_ids"]))
    )
    print(
        "strategy:         "
        + execution["strategy"]
    )
    print(
        "weights:          "
        f"bm25={execution['bm25_weight']:.2f} "
        f"bge-m3={execution['vector_weight']:.2f}"
    )
    print(
        "embedding_model:  "
        + execution["embedding_model"]
    )
    print("-" * 100)

    for hit in paper_result["hits"]:
        print(
            f"rank={hit['rank']} "
            f"score={hit['score']:.6f} "
            f"paper_id={hit['paper_id']}"
        )

        for wrapper in hit["evidence"]:
            source = str(wrapper.get("source", ""))
            source_hit = wrapper.get("hit", {})
            evidence_items = source_hit.get(
                "evidence",
                [],
            )

            if not evidence_items:
                print(f"  source={source}: <no evidence>")
                continue

            first_evidence = evidence_items[0]
            chunk = first_evidence.get("chunk", {})
            preview = _preview(
                str(chunk.get("text", "")),
                preview_chars,
            )
            print(
                f"  source={source} "
                f"chunk_id={chunk.get('chunk_id', '')} "
                f"pages={chunk.get('page_start', '')}-"
                f"{chunk.get('page_end', '')}"
            )
            print(f"    text: {preview}")

    print("=" * 100)


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


def main() -> int:
    args = build_argument_parser().parse_args()

    try:
        result = build_result(args=args)
    except Exception as error:
        print("HYBRID_SEARCH_ERROR", file=sys.stderr)
        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1

    print_result(
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
