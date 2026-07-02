"""从 JSONL 与 manifest 加载候选论文 chunk 语料。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from ai4research.indexing_pipeline.repositories.reader import (
    ChunkCorpusReader,
    ChunkCorpusReadRequest,
    ChunkCorpusReadResult,
)
from ai4research.indexing_pipeline.schemas.document_chunk import (
    DocumentChunk,
)
from ai4research.indexing_pipeline.utils.storage_paths import (
    build_chunk_asset_paths,
    to_data_root_relative_path,
)


def _normalize_options(
    options: Mapping[str, Any],
) -> dict[str, Any]:
    encoded = json.dumps(
        dict(options),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

    decoded = json.loads(encoded)

    if not isinstance(decoded, dict):
        raise TypeError(
            "splitter_options 必须是 JSON object"
        )

    return decoded


def _load_chunk_record(
    record: dict[str, Any],
) -> DocumentChunk:
    normalized_record = dict(record)

    normalized_record["section_path"] = tuple(
        normalized_record.get(
            "section_path",
            (),
        )
    )
    normalized_record["splitter_options"] = dict(
        normalized_record.get(
            "splitter_options",
            {},
        )
    )

    return DocumentChunk(
        **normalized_record
    )


def _validate_manifest_and_chunks(
    *,
    paper_id: str,
    manifest: dict[str, Any],
    chunks: tuple[DocumentChunk, ...],
    chunks_bytes: bytes,
    expected_splitter_name: str,
    expected_splitter_version: str,
    expected_splitter_options: Mapping[
        str,
        Any,
    ],
    expected_chunks_relative_path: str,
) -> None:
    if manifest.get("paper_id") != paper_id:
        raise ValueError(
            "manifest paper_id 不一致"
        )

    if (
        manifest.get("splitter_name")
        != expected_splitter_name
    ):
        raise ValueError(
            "manifest splitter_name 不一致"
        )

    if (
        manifest.get("splitter_version")
        != expected_splitter_version
    ):
        raise ValueError(
            "manifest splitter_version 不一致"
        )

    if (
        _normalize_options(
            manifest.get(
                "splitter_options",
                {},
            )
        )
        != _normalize_options(
            expected_splitter_options
        )
    ):
        raise ValueError(
            "manifest splitter_options 不一致"
        )

    if (
        manifest.get("chunks_relative_path")
        != expected_chunks_relative_path
    ):
        raise ValueError(
            "manifest chunks 路径不一致"
        )

    if manifest.get("chunk_count") != len(
        chunks
    ):
        raise ValueError(
            "manifest chunk_count 不一致"
        )

    expected_chunk_ids = [
        chunk.chunk_id
        for chunk in chunks
    ]

    if (
        manifest.get("chunk_ids")
        != expected_chunk_ids
    ):
        raise ValueError(
            "manifest chunk_ids 不一致"
        )

    actual_chunks_sha256 = hashlib.sha256(
        chunks_bytes
    ).hexdigest()

    if (
        manifest.get("chunks_sha256")
        != actual_chunks_sha256
    ):
        raise ValueError(
            "chunks.jsonl SHA256 不一致"
        )

    for expected_index, chunk in enumerate(
        chunks
    ):
        if chunk.paper_id != paper_id:
            raise ValueError(
                "chunk paper_id 不一致"
            )

        if chunk.chunk_index != expected_index:
            raise ValueError(
                "chunk_index 必须从 0 连续递增"
            )

        if (
            chunk.source_markdown_sha256
            != manifest.get(
                "source_markdown_sha256"
            )
        ):
            raise ValueError(
                "chunk Markdown SHA256 "
                "与 manifest 不一致"
            )

        if (
            chunk.source_pdf_sha256
            != manifest.get(
                "source_pdf_sha256"
            )
        ):
            raise ValueError(
                "chunk PDF SHA256 "
                "与 manifest 不一致"
            )

        if (
            chunk.source_parser_name
            != manifest.get(
                "source_parser_name"
            )
            or chunk.source_parser_version
            != manifest.get(
                "source_parser_version"
            )
        ):
            raise ValueError(
                "chunk 解析器信息 "
                "与 manifest 不一致"
            )


class JsonlChunkCorpusReader(
    ChunkCorpusReader
):
    """读取并完整校验 JSONL chunk 资产。"""

    def read(
        self,
        request: ChunkCorpusReadRequest,
    ) -> ChunkCorpusReadResult:
        loaded_paper_ids: list[str] = []
        missing_paper_ids: list[str] = []
        all_chunks: list[DocumentChunk] = []
        manifest_relative_paths: dict[
            str,
            str,
        ] = {}
        errors: dict[str, str] = {}

        for paper_id in request.paper_ids:
            try:
                paths = build_chunk_asset_paths(
                    paper_id=paper_id,
                    splitter_name=(
                        request.splitter_name
                    ),
                    splitter_version=(
                        request.splitter_version
                    ),
                    splitter_options=(
                        request.splitter_options
                    ),
                )

                if (
                    not paths.chunks_jsonl_path.is_file()
                    or not paths.manifest_path.is_file()
                ):
                    raise FileNotFoundError(
                        "chunk_assets_missing"
                    )

                chunks_bytes = (
                    paths.chunks_jsonl_path
                    .read_bytes()
                )
                manifest = json.loads(
                    paths.manifest_path.read_text(
                        encoding="utf-8"
                    )
                )

                if not isinstance(manifest, dict):
                    raise TypeError(
                        "manifest 必须是 JSON object"
                    )

                records = [
                    json.loads(line)
                    for line in chunks_bytes
                    .decode("utf-8")
                    .splitlines()
                    if line.strip()
                ]

                if not all(
                    isinstance(record, dict)
                    for record in records
                ):
                    raise TypeError(
                        "JSONL 每行必须是 JSON object"
                    )

                chunks = tuple(
                    _load_chunk_record(record)
                    for record in records
                )

                if not chunks:
                    raise ValueError(
                        "chunks.jsonl 不能为空"
                    )

                chunks_relative_path = (
                    to_data_root_relative_path(
                        paths.chunks_jsonl_path
                    ).as_posix()
                )

                _validate_manifest_and_chunks(
                    paper_id=paper_id,
                    manifest=manifest,
                    chunks=chunks,
                    chunks_bytes=chunks_bytes,
                    expected_splitter_name=(
                        request.splitter_name
                    ),
                    expected_splitter_version=(
                        request.splitter_version
                    ),
                    expected_splitter_options=(
                        request.splitter_options
                    ),
                    expected_chunks_relative_path=(
                        chunks_relative_path
                    ),
                )

                loaded_paper_ids.append(
                    paper_id
                )
                all_chunks.extend(chunks)
                manifest_relative_paths[
                    paper_id
                ] = (
                    to_data_root_relative_path(
                        paths.manifest_path
                    ).as_posix()
                )

            except Exception as error:
                missing_paper_ids.append(
                    paper_id
                )
                errors[paper_id] = (
                    f"{type(error).__name__}: "
                    f"{error}"
                )[:4000]

        return ChunkCorpusReadResult(
            requested_paper_ids=(
                request.paper_ids
            ),
            loaded_paper_ids=tuple(
                loaded_paper_ids
            ),
            missing_paper_ids=tuple(
                missing_paper_ids
            ),
            chunks=tuple(all_chunks),
            manifest_relative_paths=(
                manifest_relative_paths
            ),
            errors=errors,
        )
