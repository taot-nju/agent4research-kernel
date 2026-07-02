"""Research Topic 到论文级全文证据的一体化 CLI。"""

from __future__ import annotations

import argparse
import sys

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.document_pipeline.config import (
    load_ocr_service_config,
)
from ai4research.document_pipeline.ocr_backends.openai_compatible import (
    OpenAICompatibleOCRBackend,
)
from ai4research.document_pipeline.parsers.ocr_document_parser import (
    OCRDocumentParser,
)
from ai4research.document_pipeline.quality_checks.basic import (
    BasicDocumentQualityChecker,
)
from ai4research.fulltext_pipeline.utils.storage_paths import (
    resolve_asset_path,
)
from ai4research.indexing_pipeline.pipelines.candidate_fulltext_search import (
    RAW_SCORE_SEMANTICS,
    RELATIVE_SCORE_SEMANTICS,
)
from ai4research.indexing_pipeline.repositories.jsonl import (
    JsonlChunkRepository,
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
from ai4research.research_pipeline.pipelines.topic_to_documents import (
    run_topic_to_documents,
    select_processable_topic_candidates,
)
from ai4research.research_pipeline.pipelines.topic_to_evidence import (
    run_topic_to_evidence,
)
from ai4research.research_pipeline.retrieval.mongo_lexical import (
    MongoLexicalTopicRetriever,
)
from ai4research.research_pipeline.scripts_py.process_research_topic import (
    build_worker_id,
    print_candidates,
    save_result_json,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "元数据粗筛候选论文，补齐 PDF/OCR/chunk，"
            "再执行全文 BM25 和论文级聚合。"
        )
    )

    parser.add_argument(
        "--topic",
        required=True,
        help="Research Topic",
    )
    parser.add_argument(
        "--metadata-candidate-k",
        type=int,
        default=30,
        help="元数据粗筛并准备全文的论文数，默认 30",
    )
    parser.add_argument(
        "--final-paper-k",
        type=int,
        default=5,
        help="全文二次检索最终返回论文数，默认 5",
    )
    parser.add_argument(
        "--candidate-scan-limit",
        type=int,
        default=100,
        help="为无 PDF 候选补位而扫描的论文数，默认 100",
    )
    parser.add_argument(
        "--candidate-pool-size",
        type=int,
        default=1000,
        help="MongoDB 初始候选池上限，默认 1000",
    )
    parser.add_argument(
        "--chunk-recall-k",
        type=int,
        default=300,
        help="BM25 chunk 召回数，默认 300",
    )
    parser.add_argument(
        "--evidence-chunks-per-paper",
        type=int,
        default=3,
        help="每篇论文返回证据 chunk 数，默认 3",
    )
    parser.add_argument(
        "--top-chunks-for-score",
        type=int,
        default=3,
        help="论文聚合评分使用的最佳 chunk 数，默认 3",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="只预览元数据粗筛，不下载、不 OCR、不切分",
    )
    parser.add_argument(
        "--download-workers",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--page-workers",
        type=int,
        default=4,
    )
    parser.add_argument(
        "--render-dpi",
        type=int,
        default=200,
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=8192,
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
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
        "--preview-chars",
        type=int,
        default=260,
    )
    parser.add_argument(
        "--worker-id",
        default="",
    )
    parser.add_argument(
        "--save-json",
        default="",
    )

    return parser


def validate_arguments(
    args: argparse.Namespace,
) -> None:
    positive_values = {
        "--metadata-candidate-k": (
            args.metadata_candidate_k
        ),
        "--final-paper-k": (
            args.final_paper_k
        ),
        "--candidate-scan-limit": (
            args.candidate_scan_limit
        ),
        "--candidate-pool-size": (
            args.candidate_pool_size
        ),
        "--chunk-recall-k": (
            args.chunk_recall_k
        ),
        "--evidence-chunks-per-paper": (
            args.evidence_chunks_per_paper
        ),
        "--top-chunks-for-score": (
            args.top_chunks_for_score
        ),
        "--download-workers": (
            args.download_workers
        ),
        "--page-workers": args.page_workers,
        "--render-dpi": args.render_dpi,
        "--max-tokens": args.max_tokens,
        "--preview-chars": (
            args.preview_chars
        ),
    }

    for name, value in positive_values.items():
        if value <= 0:
            raise ValueError(
                f"{name} 必须大于 0"
            )

    if (
        args.final_paper_k
        > args.metadata_candidate_k
    ):
        raise ValueError(
            "--final-paper-k 不能大于 "
            "--metadata-candidate-k"
        )

    if (
        args.candidate_scan_limit
        < args.metadata_candidate_k
    ):
        raise ValueError(
            "--candidate-scan-limit 不能小于 "
            "--metadata-candidate-k"
        )

    if (
        args.candidate_pool_size
        < args.candidate_scan_limit
    ):
        raise ValueError(
            "--candidate-pool-size 不能小于 "
            "--candidate-scan-limit"
        )

    if args.temperature < 0:
        raise ValueError(
            "--temperature 不能小于 0"
        )

    if not args.topic.strip():
        raise ValueError(
            "--topic 不能为空"
        )


def _load_metadata(
    paper_ids: tuple[str, ...],
) -> dict[str, dict]:
    collection = MongoDBClient.get_collection()

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


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    try:
        validate_arguments(args)

        MongoDBClient.ping()
        print(
            "✅ MongoDB connected successfully."
        )

        retriever = (
            MongoLexicalTopicRetriever(
                candidate_pool_size=(
                    args.candidate_pool_size
                )
            )
        )

        if args.preview:
            candidates = (
                select_processable_topic_candidates(
                    topic=args.topic,
                    top_k=(
                        args.metadata_candidate_k
                    ),
                    candidate_scan_limit=(
                        args.candidate_scan_limit
                    ),
                    retriever=retriever,
                )
            )

            print_candidates(candidates)
            print("=" * 100)
            print(
                "✅ Preview completed; "
                "没有下载、OCR、切分或修改数据库。"
            )
            return

        service_config = (
            load_ocr_service_config()
        )
        ocr_backend = (
            OpenAICompatibleOCRBackend(
                config=service_config
            )
        )

        print(
            "🔎 Checking OCR service..."
        )
        ocr_backend.check_health()
        print("✅ OCR service is ready.")

        document_parser = OCRDocumentParser(
            backend=ocr_backend
        )
        quality_checker = (
            BasicDocumentQualityChecker()
        )
        worker_id = build_worker_id(
            args.worker_id
        )

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

        paper_aggregator = (
            PaperScoreAggregator(
                PaperAggregationConfig(
                    top_chunks_for_score=(
                        args
                        .top_chunks_for_score
                    ),
                    evidence_chunks_per_paper=(
                        args
                        .evidence_chunks_per_paper
                    ),
                )
            )
        )

        print("=" * 100)
        print("Topic Evidence 工作流配置")
        print("=" * 100)
        print(f"topic:                {args.topic}")
        print(
            f"metadata_candidate_k: "
            f"{args.metadata_candidate_k}"
        )
        print(
            f"final_paper_k:        "
            f"{args.final_paper_k}"
        )
        print(
            f"chunk_recall_k:       "
            f"{args.chunk_recall_k}"
        )
        print(
            f"download_workers:     "
            f"{args.download_workers}"
        )
        print(
            f"page_workers:         "
            f"{args.page_workers}"
        )
        print(
            f"worker_id:            "
            f"{worker_id}"
        )
        print("=" * 100)

        topic_result = run_topic_to_documents(
            topic=args.topic,
            top_k=args.metadata_candidate_k,
            candidate_scan_limit=(
                args.candidate_scan_limit
            ),
            retriever=retriever,
            document_parser=(
                document_parser
            ),
            quality_checker=(
                quality_checker
            ),
            worker_id_prefix=worker_id,
            parser_options={
                "render_dpi": args.render_dpi,
                "max_page_workers": (
                    args.page_workers
                ),
                "max_tokens": (
                    args.max_tokens
                ),
                "temperature": (
                    args.temperature
                ),
            },
            download_workers=(
                args.download_workers
            ),
            pdf_lease_seconds=600,
            document_lease_seconds=3600,
            max_attempts=3,
            retry_delay_seconds=60,
            recheck_quality=False,
        )

        evidence_result = (
            run_topic_to_evidence(
                topic_result=topic_result,
                query=args.topic,
                splitter=splitter,
                chunk_repository=(
                    JsonlChunkRepository()
                ),
                corpus_reader=(
                    JsonlChunkCorpusReader()
                ),
                chunk_retriever=(
                    chunk_retriever
                ),
                paper_aggregator=(
                    paper_aggregator
                ),
                chunk_recall_limit=(
                    args.chunk_recall_k
                ),
                final_paper_limit=(
                    args.final_paper_k
                ),
            )
        )

    except Exception as error:
        print(
            "TOPIC_EVIDENCE_ERROR",
            file=sys.stderr,
        )
        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error

    print_candidates(
        topic_result.candidates
    )

    print("=" * 100)
    print("PDF / OCR / 质量阶段")
    print("=" * 100)
    print(
        "PDF:",
        topic_result.pdf_summary,
    )
    print(
        "Document:",
        topic_result.document_summary,
    )
    print(
        "Quality:",
        topic_result.quality_summary,
    )

    print("=" * 100)
    print("CHUNK_OUTCOMES")
    print("=" * 100)

    for outcome in (
        evidence_result.chunk_outcomes
    ):
        print(
            outcome.paper_id,
            f"status={outcome.status}",
            f"chunks={outcome.chunk_count}",
            f"error={outcome.error}",
        )

    fulltext_result = (
        evidence_result.fulltext_result
    )

    if (
        not evidence_result.success
        or fulltext_result is None
    ):
        print(
            f"error: {evidence_result.error}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    paper_result = (
        fulltext_result.paper_search_result
    )

    assert paper_result is not None

    candidate_paper_ids = tuple(
        candidate.paper_id
        for candidate
        in topic_result.candidates
    )
    metadata = _load_metadata(
        candidate_paper_ids
    )

    print("=" * 100)
    print("全文二次检索")
    print("=" * 100)
    print(
        f"loaded_chunk_papers:  "
        f"{len(fulltext_result.loaded_paper_ids)}"
    )
    print(
        f"missing_chunk_papers: "
        f"{len(fulltext_result.missing_paper_ids)}"
    )
    print(
        f"raw_score:            "
        f"{RAW_SCORE_SEMANTICS}"
    )
    print(
        f"relative_score:       "
        f"{RELATIVE_SCORE_SEMANTICS}"
    )

    print("=" * 100)
    print("FINAL_EVIDENCE_PAPERS")
    print("=" * 100)

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
            fulltext_result.relative_scores[
                paper_hit.paper_id
            ]
        )

        print("-" * 100)
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
            f"{relative_score:.1f}/100.0"
        )
        print(
            f"query_coverage:  "
            f"{paper_hit.score_components.get('query_coverage', 0.0):.4f}"
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
                (
                    f"pages="
                    f"{chunk.page_start}-"
                    f"{chunk.page_end}"
                ),
                f"score={evidence.score:.4f}",
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
        saved_path = save_result_json(
            output_path=args.save_json,
            result=(
                evidence_result.to_dict()
            ),
        )

        print("=" * 100)
        print(
            f"JSON result saved: {saved_path}"
        )


if __name__ == "__main__":
    main()
