"""Chunk embedding pipeline.

把 DocumentChunk 转换为 ChunkEmbedding。
当前先支持注入任意 TextEmbeddingProvider，默认可用 deterministic demo provider。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

from ai4research.indexing_pipeline.embeddings import TextEmbeddingProvider
from ai4research.indexing_pipeline.repositories.jsonl_embedding import (
    JsonlChunkEmbeddingRepository,
    JsonlEmbeddingWriteResult,
)
from ai4research.indexing_pipeline.schemas.chunk_embedding import ChunkEmbedding
from ai4research.indexing_pipeline.schemas.document_chunk import DocumentChunk


class ChunkEmbeddingRepository(Protocol):
    def write_embeddings(
        self,
        *,
        path: Path,
        embeddings: Iterable[ChunkEmbedding],
    ) -> JsonlEmbeddingWriteResult:
        ...


@dataclass(frozen=True)
class ChunkEmbeddingPipelineResult:
    path: Path
    embedding_count: int
    embedding_model: str
    embedding_model_version: str
    embedding_dimension: int


class ChunkEmbeddingPipeline:
    """生成并保存 chunk embeddings。"""

    def __init__(
        self,
        *,
        embedding_provider: TextEmbeddingProvider,
        repository: ChunkEmbeddingRepository | None = None,
        subchunk_max_chars: int | None = None,
        subchunk_overlap_chars: int = 0,
    ) -> None:
        if subchunk_max_chars is not None and subchunk_max_chars <= 0:
            raise ValueError("subchunk_max_chars must be positive")
        if subchunk_overlap_chars < 0:
            raise ValueError("subchunk_overlap_chars must be non-negative")
        if (
            subchunk_max_chars is not None
            and subchunk_overlap_chars >= subchunk_max_chars
        ):
            raise ValueError(
                "subchunk_overlap_chars must be smaller than subchunk_max_chars"
            )

        self.embedding_provider = embedding_provider
        self.repository = repository or JsonlChunkEmbeddingRepository()
        self.subchunk_max_chars = subchunk_max_chars
        self.subchunk_overlap_chars = subchunk_overlap_chars

    def _iter_text_segments(
        self,
        text: str,
    ) -> tuple[tuple[str, int, int], ...]:
        if (
            self.subchunk_max_chars is None
            or len(text) <= self.subchunk_max_chars
        ):
            return ((text, 0, len(text)),)

        segments: list[tuple[str, int, int]] = []
        step = self.subchunk_max_chars - self.subchunk_overlap_chars
        start = 0

        while start < len(text):
            end = min(start + self.subchunk_max_chars, len(text))
            segment = text[start:end]

            if segment.strip():
                segments.append((segment, start, end))

            if end >= len(text):
                break

            start += step

        return tuple(segments)

    def embed_chunks(
        self,
        *,
        chunks: Iterable[DocumentChunk],
    ) -> tuple[ChunkEmbedding, ...]:
        embeddings: list[ChunkEmbedding] = []

        for chunk in chunks:
            segments = self._iter_text_segments(chunk.text)
            subchunk_count = len(segments)

            for subchunk_index, (
                segment_text,
                char_start,
                char_end,
            ) in enumerate(segments):
                vector = self.embedding_provider.embed_text(segment_text)

                if subchunk_count == 1:
                    embedding_chunk_id = chunk.chunk_id
                else:
                    embedding_chunk_id = (
                        f"{chunk.chunk_id}::subchunk-{subchunk_index:04d}"
                    )

                metadata = {
                    "chunk_index": chunk.chunk_index,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "section_path": list(chunk.section_path),
                    "source_markdown_relative_path": (
                        chunk.source_markdown_relative_path
                    ),
                    "source_chunk_id": chunk.chunk_id,
                    "subchunk_index": subchunk_index,
                    "subchunk_count": subchunk_count,
                    "char_start": char_start,
                    "char_end": char_end,
                    "is_subchunk": subchunk_count > 1,
                }

                embeddings.append(
                    ChunkEmbedding(
                        chunk_id=embedding_chunk_id,
                        paper_id=chunk.paper_id,
                        embedding_model=self.embedding_provider.embedding_model,
                        embedding_model_version=self.embedding_provider.embedding_model_version,
                        embedding_dimension=self.embedding_provider.embedding_dimension,
                        vector=vector,
                        source_chunk_sha256=chunk.content_sha256,
                        metadata=metadata,
                    )
                )

        return tuple(embeddings)

    def write_chunk_embeddings(
        self,
        *,
        path: Path,
        chunks: Iterable[DocumentChunk],
    ) -> ChunkEmbeddingPipelineResult:
        embeddings = self.embed_chunks(chunks=chunks)
        write_result = self.repository.write_embeddings(
            path=path,
            embeddings=embeddings,
        )

        return ChunkEmbeddingPipelineResult(
            path=write_result.path,
            embedding_count=write_result.embedding_count,
            embedding_model=self.embedding_provider.embedding_model,
            embedding_model_version=self.embedding_provider.embedding_model_version,
            embedding_dimension=self.embedding_provider.embedding_dimension,
        )
