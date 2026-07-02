"""在候选论文 chunk 资产中运行 vector search。

这是一个可手工调用的 CLI entrypoint，用于验证 vector 检索链路能否接入
候选论文集合，并输出可被 evaluate_saved_retrieval 评估的 JSON 结果。

注意：这里使用 TokenHashEmbeddingProvider，不是真实语义 embedding。
它的用途是打通：

candidate paper ids
  -> chunk assets
  -> token-hash embeddings
  -> vector chunk search
  -> paper aggregation
  -> saved search result JSON
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ai4research.indexing_pipeline.embeddings import TokenHashEmbeddingProvider
from ai4research.indexing_pipeline.embedding_config import (
    load_embedding_service_config,
)
from ai4research.indexing_pipeline.openai_compatible_embedding import (
    OpenAICompatibleEmbeddingProvider,
)
from ai4research.indexing_pipeline.pipelines.chunk_embedding_pipeline import (
    ChunkEmbeddingPipeline,
)
from ai4research.indexing_pipeline.repositories.jsonl_embedding import (
    JsonlChunkEmbeddingRepository,
)
from ai4research.indexing_pipeline.repositories.jsonl_reader import (
    JsonlChunkCorpusReader,
)
from ai4research.indexing_pipeline.repositories.reader import (
    ChunkCorpusReadRequest,
)
from ai4research.indexing_pipeline.retrieval.vector import CosineVectorRetriever
from ai4research.indexing_pipeline.retrieval.vector_paper_aggregation import (
    VectorPaperAggregationConfig,
    VectorPaperAggregator,
)


DEFAULT_SPLITTER_NAME = "markdown-block-splitter"
DEFAULT_SPLITTER_VERSION = "1"
DEFAULT_SPLITTER_OPTIONS = {
    "target_chars": 2400,
    "max_chars": 3200,
    "overlap_chars": 300,
    "min_chars_before_heading_break": 800,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "在一组候选论文的 chunk 资产中执行 vector search，"
            "聚合为论文级排名，并可保存 JSON 结果。"
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
        "--splitter-name",
        default=DEFAULT_SPLITTER_NAME,
        help=f"chunk splitter 名称，默认 {DEFAULT_SPLITTER_NAME}",
    )
    parser.add_argument(
        "--splitter-version",
        default=DEFAULT_SPLITTER_VERSION,
        help=f"chunk splitter 版本，默认 {DEFAULT_SPLITTER_VERSION}",
    )
    parser.add_argument(
        "--target-chars",
        type=int,
        default=DEFAULT_SPLITTER_OPTIONS["target_chars"],
        help="chunk splitter target_chars，默认 2400",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_SPLITTER_OPTIONS["max_chars"],
        help="chunk splitter max_chars，默认 3200",
    )
    parser.add_argument(
        "--overlap-chars",
        type=int,
        default=DEFAULT_SPLITTER_OPTIONS["overlap_chars"],
        help="chunk splitter overlap_chars，默认 300",
    )
    parser.add_argument(
        "--min-chars-before-heading-break",
        type=int,
        default=DEFAULT_SPLITTER_OPTIONS["min_chars_before_heading_break"],
        help="chunk splitter min_chars_before_heading_break，默认 800",
    )
    parser.add_argument(
        "--provider",
        choices=("token-hash", "openai-compatible"),
        default="token-hash",
        help="embedding provider，默认 token-hash",
    )
    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=256,
        help="embedding 维度；token-hash 默认 256；openai-compatible 必须匹配 AI4RESEARCH_EMBEDDING_DIMENSION",
    )
    parser.add_argument(
        "--embedding-input-max-chars",
        type=int,
        default=0,
        help="openai-compatible embedding 输入最大字符数；0 表示不截断",
    )
    parser.add_argument(
        "--subchunk-max-chars",
        type=int,
        default=0,
        help="超过该字符数的 chunk 会切成 subchunk；0 表示不开启",
    )
    parser.add_argument(
        "--subchunk-overlap-chars",
        type=int,
        default=0,
        help="subchunk 之间的重叠字符数，默认 0",
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
        default=5,
        help="最终论文数，默认 5",
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
        default=260,
        help="证据文本预览字符数，默认 260",
    )
    parser.add_argument(
        "--embedding-cache-dir",
        default="/tmp/ai4research_candidate_embeddings",
        help="embedding JSONL 缓存目录，默认 /tmp/ai4research_candidate_embeddings",
    )
    parser.add_argument(
        "--reuse-embeddings",
        action="store_true",
        help="如果 paper 的 embeddings 已存在，则复用缓存",
    )
    parser.add_argument(
        "--save-json",
        help="可选：保存完整 JSON 结果",
    )
    return parser.parse_args()


def _splitter_options_from_args(args: argparse.Namespace) -> dict[str, int]:
    return {
        "target_chars": args.target_chars,
        "max_chars": args.max_chars,
        "overlap_chars": args.overlap_chars,
        "min_chars_before_heading_break": args.min_chars_before_heading_break,
    }


def _build_embedding_provider(args: argparse.Namespace):
    if args.provider == "token-hash":
        return TokenHashEmbeddingProvider(
            embedding_dimension=args.embedding_dim,
        )

    if args.provider == "openai-compatible":
        config = load_embedding_service_config()
        if args.embedding_dim != config.embedding_dimension:
            raise ValueError(
                "embedding_dim must match AI4RESEARCH_EMBEDDING_DIMENSION "
                f"for openai-compatible provider: expected={config.embedding_dimension}, got={args.embedding_dim}"
            )
        input_max_chars = args.embedding_input_max_chars or None
        return OpenAICompatibleEmbeddingProvider(
            config=config,
            input_max_chars=input_max_chars,
        )

    raise ValueError(f"unsupported provider: {args.provider}")


def _embedding_path_for_paper(
    *,
    cache_dir: Path,
    paper_id: str,
    embedding_model: str,
    embedding_model_version: str,
    embedding_dimension: int,
) -> Path:
    return (
        cache_dir
        / paper_id[:2]
        / paper_id[2:4]
        / paper_id
        / embedding_model
        / f"{embedding_model_version}-{embedding_dimension}"
        / "embeddings.jsonl"
    )


def _preview(text: str, limit: int) -> str:
    return " ".join(text.split())[:limit]


def build_result(
    *,
    args: argparse.Namespace,
) -> dict[str, Any]:
    data_root = Path(args.data_root).expanduser().resolve()
    cache_dir = Path(args.embedding_cache_dir).expanduser().resolve()
    paper_ids = tuple(args.paper_id)
    splitter_options = _splitter_options_from_args(args)

    corpus_reader = JsonlChunkCorpusReader()
    corpus_result = corpus_reader.read(
        ChunkCorpusReadRequest(
            paper_ids=paper_ids,
            splitter_name=args.splitter_name,
            splitter_version=args.splitter_version,
            splitter_options=splitter_options,
        )
    )

    provider = _build_embedding_provider(args)
    embedding_repository = JsonlChunkEmbeddingRepository()
    embedding_pipeline = ChunkEmbeddingPipeline(
        embedding_provider=provider,
        repository=embedding_repository,
        subchunk_max_chars=args.subchunk_max_chars or None,
        subchunk_overlap_chars=args.subchunk_overlap_chars,
    )

    embeddings = []
    embedding_outcomes = []

    chunks_by_paper = {}
    for chunk in corpus_result.chunks:
        chunks_by_paper.setdefault(chunk.paper_id, []).append(chunk)

    for paper_id in corpus_result.loaded_paper_ids:
        paper_chunks = tuple(chunks_by_paper.get(paper_id, ()))
        embedding_path = _embedding_path_for_paper(
            cache_dir=cache_dir,
            paper_id=paper_id,
            embedding_model=provider.embedding_model,
            embedding_model_version=provider.embedding_model_version,
            embedding_dimension=provider.embedding_dimension,
        )

        if args.reuse_embeddings and embedding_path.exists():
            read_result = embedding_repository.read_embeddings(
                path=embedding_path,
            )
            status = "reused"
        else:
            embedding_pipeline.write_chunk_embeddings(
                path=embedding_path,
                chunks=paper_chunks,
            )
            read_result = embedding_repository.read_embeddings(
                path=embedding_path,
            )
            status = "written"

        embeddings.extend(read_result.embeddings)
        embedding_outcomes.append(
            {
                "paper_id": paper_id,
                "status": status,
                "embedding_count": read_result.embedding_count,
                "path": str(embedding_path),
            }
        )

    query_vector = provider.embed_text(args.query)

    chunk_result = CosineVectorRetriever().search(
        query_vector=query_vector,
        embeddings=embeddings,
        top_k=args.chunk_recall_k,
    )

    paper_result = VectorPaperAggregator().aggregate(
        query_vector_dimension=chunk_result.query_vector_dimension,
        chunk_hits=chunk_result.hits,
        config=VectorPaperAggregationConfig(
            final_paper_k=args.final_paper_k,
            evidence_chunks_per_paper=args.evidence_chunks_per_paper,
            top_chunks_for_score=args.top_chunks_for_score,
        ),
    )

    chunks_by_id = {
        chunk.chunk_id: chunk
        for chunk in corpus_result.chunks
    }

    paper_hits = []
    for paper_hit in paper_result.hits:
        evidence = []
        for vector_hit in paper_hit.evidence:
            source_chunk_id = str(
                vector_hit.embedding.metadata.get(
                    "source_chunk_id",
                    vector_hit.embedding.chunk_id,
                )
            )
            chunk = chunks_by_id[source_chunk_id]
            evidence.append(
                {
                    "rank": vector_hit.rank,
                    "score": vector_hit.score,
                    "chunk": chunk.to_dict(),
                    "embedding": vector_hit.embedding.to_dict(),
                    "preview": _preview(chunk.text, args.preview_chars),
                }
            )

        paper_hits.append(
            {
                "rank": paper_hit.rank,
                "paper_id": paper_hit.paper_id,
                "score": paper_hit.score,
                "score_components": paper_hit.score_components,
                "evidence": evidence,
            }
        )

    return {
        "success": True,
        "status": "complete",
        "query": args.query,
        "data_root": str(data_root),
        "data_root_note": "JsonlChunkCorpusReader currently uses the configured default chunk asset root.",
        "requested_paper_ids": list(paper_ids),
        "loaded_paper_ids": list(corpus_result.loaded_paper_ids),
        "missing_paper_ids": list(corpus_result.missing_paper_ids),
        "embedding_provider": {
            "provider": args.provider,
            "embedding_model": provider.embedding_model,
            "embedding_model_version": provider.embedding_model_version,
            "embedding_dimension": provider.embedding_dimension,
            "input_max_chars": args.embedding_input_max_chars or None,
            "subchunk_max_chars": args.subchunk_max_chars or None,
            "subchunk_overlap_chars": args.subchunk_overlap_chars,
        },
        "embedding_outcomes": embedding_outcomes,
        "chunk_search_result": chunk_result.to_dict(),
        "paper_search_result": {
            "query": args.query,
            "chunk_retriever_name": chunk_result.retriever_name,
            "chunk_retriever_version": chunk_result.retriever_version,
            "corpus_paper_count": len(corpus_result.loaded_paper_ids),
            "corpus_chunk_count": len(corpus_result.chunks),
            "matched_paper_count": paper_result.matched_paper_count,
            "hits": paper_hits,
            "aggregation_config": {
                "final_paper_k": args.final_paper_k,
                "evidence_chunks_per_paper": args.evidence_chunks_per_paper,
                "top_chunks_for_score": args.top_chunks_for_score,
            },
        },
        "errors": dict(corpus_result.errors),
    }


def print_result(result: dict[str, Any], *, preview_chars: int) -> None:
    print("=" * 100)
    print("Candidate vector search")
    print("=" * 100)
    print(f"query:              {result['query']}")
    print(f"requested_papers:   {len(result['requested_paper_ids'])}")
    print(f"loaded_papers:      {len(result['loaded_paper_ids'])}")
    print(f"missing_papers:     {len(result['missing_paper_ids'])}")
    print(f"provider:           {result['embedding_provider']['provider']}")
    print(f"embedding_model:    {result['embedding_provider']['embedding_model']}:{result['embedding_provider']['embedding_model_version']}")
    print(f"embedding_dim:      {result['embedding_provider']['embedding_dimension']}")
    print("-" * 100)
    print("embedding_outcomes:")
    for outcome in result["embedding_outcomes"]:
        print(
            f"  {outcome['paper_id']} "
            f"status={outcome['status']} "
            f"embedding_count={outcome['embedding_count']}"
        )
    print("=" * 100)
    print("PAPER RANKING")
    print("-" * 100)

    for hit in result["paper_search_result"]["hits"]:
        print(f"rank={hit['rank']} score={hit['score']:.4f}")
        print(f"paper_id: {hit['paper_id']}")
        print(f"components: {hit['score_components']}")

        for evidence in hit["evidence"]:
            chunk = evidence["chunk"]
            section = " > ".join(chunk.get("section_path", []))
            print(
                f"  evidence chunk_rank={evidence['rank']} "
                f"score={evidence['score']:.4f} "
                f"pages={chunk.get('page_start')}-{chunk.get('page_end')}"
            )
            print(f"  section: {section}")
            print(f"  text: {evidence['preview'][:preview_chars]}")

        print("-" * 100)

    if result["missing_paper_ids"] or result["errors"]:
        print("MISSING / ERRORS")
        print("-" * 100)
        print(f"missing_paper_ids: {result['missing_paper_ids']}")
        print(f"errors: {result['errors']}")

    print("=" * 100)


def main() -> None:
    args = parse_args()
    result = build_result(args=args)
    print_result(result, preview_chars=args.preview_chars)

    if args.save_json:
        save_path = Path(args.save_json).expanduser().resolve()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"JSON report saved: {save_path}")


if __name__ == "__main__":
    main()
