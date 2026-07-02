"""在已有 chunk JSONL 上运行本地 token-hash vector search demo。

这个脚本不调用外部 embedding API，只用 TokenHashEmbeddingProvider 生成 demo 向量。
它的目的不是证明语义检索质量，而是验证真实 chunk 资产上的 vector 检索链路：

chunks.jsonl
  -> token-hash embeddings.jsonl
  -> query vector
  -> vector chunk search
  -> paper aggregation
  -> evidence 输出
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai4research.indexing_pipeline.embeddings import TokenHashEmbeddingProvider
from ai4research.indexing_pipeline.pipelines.chunk_embedding_pipeline import (
    ChunkEmbeddingPipeline,
)
from ai4research.indexing_pipeline.repositories.jsonl_embedding import (
    JsonlChunkEmbeddingRepository,
)
from ai4research.indexing_pipeline.schemas.document_chunk import DocumentChunk
from ai4research.indexing_pipeline.retrieval.vector import CosineVectorRetriever
from ai4research.indexing_pipeline.retrieval.vector_paper_aggregation import (
    VectorPaperAggregationConfig,
    VectorPaperAggregator,
)


def _read_chunks_jsonl(path: Path) -> tuple[DocumentChunk, ...]:
    chunks: list[DocumentChunk] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                record = json.loads(stripped)
                record["section_path"] = tuple(record.get("section_path", ()))
                record["splitter_options"] = dict(record.get("splitter_options", {}))
                chunks.append(DocumentChunk(**record))
            except Exception as exc:
                raise ValueError(
                    f"invalid chunk jsonl line {line_number}: {exc}"
                ) from exc

    return tuple(chunks)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="读取已有 chunks.jsonl，用 token-hash demo embedding 执行 vector search。"
    )
    parser.add_argument(
        "--chunks-jsonl",
        required=True,
        help="已有 chunks.jsonl 路径",
    )
    parser.add_argument(
        "--query",
        required=True,
        help="检索 query",
    )
    parser.add_argument(
        "--embeddings-jsonl",
        help="可选：保存或复用 token-hash embeddings JSONL 的路径；默认写到 /tmp/ai4research_demo_embeddings/",
    )
    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=256,
        help="token-hash embedding 维度，默认 256",
    )
    parser.add_argument(
        "--chunk-top-k",
        type=int,
        default=20,
        help="vector chunk 召回数，默认 20",
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
        help="每篇论文展示 evidence chunk 数，默认 3",
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
        "--reuse-embeddings",
        action="store_true",
        help="如果 embeddings-jsonl 已存在，则直接复用，不重新生成",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    chunks_path = Path(args.chunks_jsonl).expanduser().resolve()
    embeddings_path = (
        Path(args.embeddings_jsonl).expanduser().resolve()
        if args.embeddings_jsonl
        else (
            Path("/tmp")
            / "ai4research_demo_embeddings"
            / chunks_path.stem
            / "token_hash_embeddings.jsonl"
        )
    )

    provider = TokenHashEmbeddingProvider(embedding_dimension=args.embedding_dim)
    embedding_repository = JsonlChunkEmbeddingRepository()

    chunks = _read_chunks_jsonl(chunks_path)

    if args.reuse_embeddings and embeddings_path.exists():
        embedding_read_result = embedding_repository.read_embeddings(
            path=embeddings_path,
        )
        embedding_status = "reused"
    else:
        pipeline = ChunkEmbeddingPipeline(
            embedding_provider=provider,
            repository=embedding_repository,
        )
        pipeline.write_chunk_embeddings(
            path=embeddings_path,
            chunks=chunks,
        )
        embedding_read_result = embedding_repository.read_embeddings(
            path=embeddings_path,
        )
        embedding_status = "written"

    query_vector = provider.embed_text(args.query)

    chunk_result = CosineVectorRetriever().search(
        query_vector=query_vector,
        embeddings=embedding_read_result.embeddings,
        top_k=args.chunk_top_k,
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

    print("=" * 100)
    print("Token-hash vector search demo")
    print("=" * 100)
    print(f"query:              {args.query}")
    print(f"chunks_jsonl:       {chunks_path}")
    print(f"embeddings_jsonl:   {embeddings_path}")
    print(f"embedding_status:   {embedding_status}")
    print(f"embedding_model:    {provider.embedding_model}:{provider.embedding_model_version}")
    print(f"embedding_dim:      {provider.embedding_dimension}")
    print(f"chunk_count:        {len(chunks)}")
    print(f"embedding_count:    {embedding_read_result.embedding_count}")
    print(f"chunk_top_k:        {args.chunk_top_k}")
    print(f"final_paper_k:      {args.final_paper_k}")
    print("=" * 100)

    print("PAPER RANKING")
    print("-" * 100)
    for paper_hit in paper_result.hits:
        print(f"rank={paper_hit.rank} score={paper_hit.score:.4f}")
        print(f"paper_id: {paper_hit.paper_id}")
        print(f"components: {paper_hit.score_components}")

        for evidence in paper_hit.evidence:
            chunk = next(
                chunk
                for chunk in chunks
                if chunk.chunk_id == evidence.embedding.chunk_id
            )
            preview = " ".join(chunk.text.split())[: args.preview_chars]
            section = " > ".join(chunk.section_path)
            print(
                f"  evidence chunk_rank={evidence.rank} "
                f"score={evidence.score:.4f} "
                f"pages={chunk.page_start}-{chunk.page_end}"
            )
            print(f"  section: {section}")
            print(f"  text: {preview}")

        print("-" * 100)

    print("CHUNK HITS")
    print("-" * 100)
    for hit in chunk_result.hits:
        chunk = next(
            chunk
            for chunk in chunks
            if chunk.chunk_id == hit.embedding.chunk_id
        )
        section = " > ".join(chunk.section_path)
        preview = " ".join(chunk.text.split())[: args.preview_chars]
        print(
            f"{hit.rank}. score={hit.score:.4f} "
            f"paper_id={hit.embedding.paper_id} "
            f"pages={chunk.page_start}-{chunk.page_end}"
        )
        print(f"   section: {section}")
        print(f"   text: {preview}")

    print("=" * 100)


if __name__ == "__main__":
    main()
