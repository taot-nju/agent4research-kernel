"""JSONL chunk embedding repository.

这个 repository 负责把 ChunkEmbedding 记录保存成 JSONL，
并能按文件读取回来。它先服务最小 embedding 闭环：
chunk -> embedding -> JSONL -> corpus reader -> vector search。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ai4research.indexing_pipeline.schemas.chunk_embedding import ChunkEmbedding


@dataclass(frozen=True)
class JsonlEmbeddingWriteResult:
    path: Path
    embedding_count: int


@dataclass(frozen=True)
class JsonlEmbeddingReadResult:
    path: Path
    embeddings: tuple[ChunkEmbedding, ...]

    @property
    def embedding_count(self) -> int:
        return len(self.embeddings)


class JsonlChunkEmbeddingRepository:
    """把 ChunkEmbedding 写入/读出 JSONL 文件。"""

    def write_embeddings(
        self,
        *,
        path: Path,
        embeddings: Iterable[ChunkEmbedding],
    ) -> JsonlEmbeddingWriteResult:
        normalized_path = Path(path).expanduser()
        normalized_path.parent.mkdir(parents=True, exist_ok=True)

        count = 0
        with normalized_path.open("w", encoding="utf-8") as handle:
            for embedding in embeddings:
                handle.write(
                    json.dumps(
                        embedding.to_dict(),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
                count += 1

        return JsonlEmbeddingWriteResult(
            path=normalized_path,
            embedding_count=count,
        )

    def read_embeddings(
        self,
        *,
        path: Path,
    ) -> JsonlEmbeddingReadResult:
        normalized_path = Path(path).expanduser()
        embeddings: list[ChunkEmbedding] = []

        with normalized_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                    embeddings.append(ChunkEmbedding.from_dict(data))
                except Exception as exc:
                    raise ValueError(
                        f"invalid embedding jsonl line {line_number}: {exc}"
                    ) from exc

        return JsonlEmbeddingReadResult(
            path=normalized_path,
            embeddings=tuple(embeddings),
        )
