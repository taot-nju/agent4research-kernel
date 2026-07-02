"""根据 paper ID 生成可引用的 chunk JSONL 资产。"""

from __future__ import annotations

import argparse
import sys

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.fulltext_pipeline.utils.storage_paths import (
    resolve_asset_path,
)
from ai4research.indexing_pipeline.pipelines.document_chunk_pipeline import (
    DocumentChunkPipelineRequest,
    process_document_chunks,
)
from ai4research.indexing_pipeline.repositories.document_source import (
    load_indexable_document_source,
)
from ai4research.indexing_pipeline.repositories.jsonl import (
    JsonlChunkRepository,
)
from ai4research.indexing_pipeline.splitters.markdown_block_splitter import (
    MarkdownBlockSplitter,
    MarkdownBlockSplitterConfig,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "读取通过质量检查的 OCR Markdown，"
            "生成页码感知的 chunk JSONL 与 manifest。"
        )
    )

    parser.add_argument(
        "--paper-id",
        required=True,
        help="目标论文的稳定 paper ID",
    )
    parser.add_argument(
        "--target-chars",
        type=int,
        default=2400,
        help="目标 chunk 字符数，默认 2400",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=3200,
        help="普通 chunk 最大字符数，默认 3200",
    )
    parser.add_argument(
        "--overlap-chars",
        type=int,
        default=300,
        help="相邻 chunk 目标重叠字符数，默认 300",
    )
    parser.add_argument(
        "--min-chars-before-heading-break",
        type=int,
        default=800,
        help=(
            "遇到标题前触发分块所需的最小字符数，"
            "默认 800"
        ),
    )
    parser.add_argument(
        "--passed-only",
        action="store_true",
        help="只允许 quality_status=passed",
    )

    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    allowed_quality_statuses = (
        ("passed",)
        if args.passed_only
        else ("passed", "warning")
    )

    try:
        config = MarkdownBlockSplitterConfig(
            target_chars=args.target_chars,
            max_chars=args.max_chars,
            overlap_chars=args.overlap_chars,
            min_chars_before_heading_break=(
                args
                .min_chars_before_heading_break
            ),
        )

        MongoDBClient.ping()

        source = (
            load_indexable_document_source(
                paper_id=args.paper_id,
                allowed_quality_statuses=(
                    allowed_quality_statuses
                ),
            )
        )

        splitter = MarkdownBlockSplitter(
            config
        )
        repository = JsonlChunkRepository()

        request = DocumentChunkPipelineRequest(
            paper_id=source.paper_id,
            markdown_path=source.markdown_path,
            source_markdown_relative_path=(
                source.markdown_relative_path
            ),
            source_pdf_sha256=(
                source.source_pdf_sha256
            ),
            source_parser_name=(
                source.parser_name
            ),
            source_parser_version=(
                source.parser_version
            ),
            title=source.title,
        )

        result = process_document_chunks(
            request=request,
            splitter=splitter,
            repository=repository,
        )

    except Exception as error:
        print(
            "CHUNK_PIPELINE_ERROR",
            file=sys.stderr,
        )
        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error

    print("=" * 100)
    print("论文 chunk 处理结果")
    print("=" * 100)
    print(f"paper_id:       {source.paper_id}")
    print(f"title:          {source.title}")
    print(
        f"quality_status: {source.quality_status}"
    )
    print(f"status:         {result.status}")
    print(f"chunk_count:    {result.chunk_count}")
    print(
        f"splitter:       "
        f"{result.splitter_name}:"
        f"{result.splitter_version}"
    )
    print(
        f"options:        "
        f"{dict(result.splitter_options)}"
    )
    print(
        f"markdown_sha256:"
        f" {result.source_markdown_sha256}"
    )

    if result.warnings:
        print(
            f"warnings:       "
            f"{list(result.warnings)}"
        )

    if result.metadata:
        print(
            f"metadata:       "
            f"{dict(result.metadata)}"
        )

    if not result.success:
        print(
            f"error:          {result.error}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    chunks_absolute_path = (
        resolve_asset_path(
            result.chunks_relative_path
        )
    )
    manifest_absolute_path = (
        resolve_asset_path(
            result.manifest_relative_path
        )
    )

    print(
        f"chunks:         "
        f"{chunks_absolute_path}"
    )
    print(
        f"manifest:       "
        f"{manifest_absolute_path}"
    )
    print("=" * 100)


if __name__ == "__main__":
    main()
