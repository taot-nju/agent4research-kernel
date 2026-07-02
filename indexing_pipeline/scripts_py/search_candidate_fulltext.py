"""在指定候选论文集合内执行全文 BM25 二次检索。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.fulltext_pipeline.utils.storage_paths import (
    resolve_asset_path,
)
from ai4research.indexing_pipeline.pipelines.candidate_fulltext_search import (
    CandidateFullTextSearchRequest,
    RAW_SCORE_SEMANTICS,
    RELATIVE_SCORE_SEMANTICS,
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
from ai4research.indexing_pipeline.splitters.markdown_block_splitter import (
    MarkdownBlockSplitter,
    MarkdownBlockSplitterConfig,
)
from ai4research.indexing_pipeline.utils.storage_paths import (
    build_chunk_asset_paths,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "在一组候选论文的 chunk 资产中执行 BM25，"
            "聚合为论文级排名并返回页码证据。"
        )
    )

    parser.add_argument(
        "--query",
        required=True,
        help="全文二次检索查询",
    )
    parser.add_argument(
        "--paper-id",
        action="append",
        required=True,
        help=(
            "候选 paper ID；可重复传入多次"
        ),
    )
    parser.add_argument(
        "--chunk-recall-k",
        type=int,
        default=300,
        help="BM25 chunk 召回数，默认 300",
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
        help="每篇论文返回的证据 chunk 数，默认 3",
    )
    parser.add_argument(
        "--top-chunks-for-score",
        type=int,
        default=3,
        help="论文聚合评分使用的最佳 chunk 数，默认 3",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=260,
        help="每条证据预览字符数，默认 260",
    )
    parser.add_argument(
        "--target-chars",
        type=int,
        default=2400,
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=3200,
    )
    parser.add_argument(
        "--overlap-chars",
        type=int,
        default=300,
    )
    parser.add_argument(
        "--min-chars-before-heading-break",
        type=int,
        default=800,
    )
    parser.add_argument(
        "--bm25-k1",
        type=float,
        default=1.5,
    )
    parser.add_argument(
        "--bm25-b",
        type=float,
        default=0.75,
    )
    parser.add_argument(
        "--section-term-multiplier",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--save-json",
        default="",
        help="可选：保存完整 JSON 结果",
    )

    return parser


def _load_metadata(
    paper_ids: tuple[str, ...],
) -> dict[str, dict]:
    try:
        MongoDBClient.ping()
        collection = (
            MongoDBClient.get_collection()
        )

        return {
            str(document["_id"]): document
            for document in collection.find(
                {
                    "_id": {
                        "$in": list(paper_ids),
                    }
                },
                {
                    "_id": 1,
                    "title": 1,
                    "accepted_by": 1,
                    "pdf_asset.relative_path": 1,
                    "document_asset.markdown_relative_path": 1,
                    "document_asset.quality_status": 1,
                },
            )
        }

    except Exception as error:
        print(
            "⚠️ MongoDB metadata unavailable: "
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return {}


def _absolute_asset_path(
    relative_path: str,
) -> str:
    normalized = str(
        relative_path or ""
    ).strip()

    if not normalized:
        return "<unavailable>"

    try:
        return str(
            resolve_asset_path(normalized)
        )
    except Exception:
        return "<invalid path>"


def _save_json(
    output_path: str,
    payload: dict,
) -> Path:
    path = Path(
        output_path
    ).expanduser().resolve()
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )
    temporary_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)

    return path


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    paper_ids = tuple(
        dict.fromkeys(
            paper_id.strip()
            for paper_id in args.paper_id
            if paper_id.strip()
        )
    )

    if not paper_ids:
        parser.error(
            "至少需要一个有效 --paper-id"
        )

    if args.preview_chars <= 0:
        parser.error(
            "--preview-chars 必须大于 0"
        )

    try:
        splitter = MarkdownBlockSplitter(
            MarkdownBlockSplitterConfig(
                target_chars=(
                    args.target_chars
                ),
                max_chars=args.max_chars,
                overlap_chars=(
                    args.overlap_chars
                ),
                min_chars_before_heading_break=(
                    args
                    .min_chars_before_heading_break
                ),
            )
        )

        chunk_retriever = (
            BM25ChunkRetriever(
                BM25ChunkRetrieverConfig(
                    k1=args.bm25_k1,
                    b=args.bm25_b,
                    section_term_multiplier=(
                        args
                        .section_term_multiplier
                    ),
                )
            )
        )

        aggregator = PaperScoreAggregator(
            PaperAggregationConfig(
                top_chunks_for_score=(
                    args.top_chunks_for_score
                ),
                evidence_chunks_per_paper=(
                    args
                    .evidence_chunks_per_paper
                ),
            )
        )

        request = (
            CandidateFullTextSearchRequest(
                query=args.query,
                candidate_paper_ids=paper_ids,
                splitter_name=splitter.name,
                splitter_version=(
                    splitter.version
                ),
                splitter_options=(
                    splitter.options
                ),
                chunk_recall_limit=(
                    args.chunk_recall_k
                ),
                final_paper_limit=(
                    args.final_paper_k
                ),
            )
        )

        result = search_candidate_fulltext(
            request=request,
            corpus_reader=(
                JsonlChunkCorpusReader()
            ),
            chunk_retriever=(
                chunk_retriever
            ),
            paper_aggregator=aggregator,
        )

    except Exception as error:
        print(
            "FULLTEXT_SEARCH_ERROR",
            file=sys.stderr,
        )
        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error

    metadata = _load_metadata(paper_ids)

    print("=" * 100)
    print("候选论文全文二次检索")
    print("=" * 100)
    print(f"query:                 {args.query}")
    print(
        f"candidate_papers:      {len(paper_ids)}"
    )
    print(
        f"loaded_chunk_papers:   "
        f"{len(result.loaded_paper_ids)}"
    )
    print(
        f"missing_chunk_papers:  "
        f"{len(result.missing_paper_ids)}"
    )
    print(f"status:                {result.status}")
    print(
        f"raw_score:             "
        f"{RAW_SCORE_SEMANTICS}"
    )
    print(
        f"relative_score:        "
        f"{RELATIVE_SCORE_SEMANTICS}"
    )

    if result.missing_paper_ids:
        print("-" * 100)
        print("MISSING_CHUNK_PAPERS")

        for paper_id in result.missing_paper_ids:
            print(
                paper_id,
                result.errors.get(
                    paper_id,
                    "",
                ),
            )

    if not result.success:
        print(
            f"error: {result.error}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    paper_result = (
        result.paper_search_result
    )
    chunk_result = (
        result.chunk_search_result
    )

    assert paper_result is not None
    assert chunk_result is not None

    print("-" * 100)
    print(
        f"corpus_chunks:         "
        f"{chunk_result.corpus_chunk_count}"
    )
    print(
        f"chunk_hits:            "
        f"{len(chunk_result.hits)}"
    )
    print(
        f"matched_papers:        "
        f"{paper_result.matched_paper_count}"
    )
    print("=" * 100)
    print("FINAL_PAPER_RESULTS")

    if not paper_result.hits:
        print("<none>")

    for paper_hit in paper_result.hits:
        paper = metadata.get(
            paper_hit.paper_id,
            {},
        )
        pdf_asset = paper.get(
            "pdf_asset",
            {},
        )
        document_asset = paper.get(
            "document_asset",
            {},
        )

        if not isinstance(pdf_asset, dict):
            pdf_asset = {}

        if not isinstance(
            document_asset,
            dict,
        ):
            document_asset = {}

        chunk_paths = build_chunk_asset_paths(
            paper_id=paper_hit.paper_id,
            splitter_name=splitter.name,
            splitter_version=(
                splitter.version
            ),
            splitter_options=(
                splitter.options
            ),
        )

        relative_score = (
            result.relative_scores[
                paper_hit.paper_id
            ]
        )

        print("=" * 100)
        print(f"rank:            {paper_hit.rank}")
        print(
            f"paper_id:        "
            f"{paper_hit.paper_id}"
        )
        print(
            f"title:           "
            f"{paper.get('title', '')}"
        )
        print(
            f"accepted_by:     "
            f"{paper.get('accepted_by', '')}"
        )
        print(
            f"raw_score:       "
            f"{paper_hit.score:.4f} "
            f"(unbounded)"
        )
        print(
            f"relative_score:  "
            f"{relative_score:.1f}/100.0 "
            f"(this result set only)"
        )
        print(
            f"query_coverage:  "
            f"{paper_hit.score_components.get('query_coverage', 0.0):.4f}"
        )
        print(
            f"matched_terms:   "
            f"{paper_hit.matched_terms}"
        )
        print(
            "pdf:             "
            + _absolute_asset_path(
                pdf_asset.get(
                    "relative_path",
                    "",
                )
            )
        )
        print(
            "ocr_markdown:    "
            + _absolute_asset_path(
                document_asset.get(
                    "markdown_relative_path",
                    "",
                )
            )
        )
        print(
            f"chunks:          "
            f"{chunk_paths.chunks_jsonl_path}"
        )
        print(
            f"manifest:        "
            f"{chunk_paths.manifest_path}"
        )
        print("evidence:")

        for evidence in paper_hit.evidence:
            chunk = evidence.chunk
            preview = " ".join(
                chunk.text.split()
            )[: args.preview_chars]

            print(
                "  -",
                f"chunk_rank={evidence.rank}",
                f"chunk_score={evidence.score:.4f}",
                (
                    f"pages="
                    f"{chunk.page_start}-"
                    f"{chunk.page_end}"
                ),
                f"chunk_id={chunk.chunk_id}",
            )
            print(
                "    section:",
                " > ".join(
                    chunk.section_path
                ),
            )
            print(
                "    text:",
                preview,
            )

    if args.save_json:
        payload = result.to_dict()
        payload["paper_metadata"] = {
            paper_id: {
                "title": str(
                    metadata.get(
                        paper_id,
                        {},
                    ).get("title", "")
                ),
                "accepted_by": str(
                    metadata.get(
                        paper_id,
                        {},
                    ).get(
                        "accepted_by",
                        "",
                    )
                ),
            }
            for paper_id in paper_ids
        }

        saved_path = _save_json(
            args.save_json,
            payload,
        )
        print("=" * 100)
        print(
            f"JSON result saved: {saved_path}"
        )


if __name__ == "__main__":
    main()
