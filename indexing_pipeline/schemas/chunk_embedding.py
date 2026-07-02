"""Chunk embedding 数据结构。

这个模块只定义 embedding 记录本身，不绑定具体模型服务。

兼容两套字段命名：

1. 早期契约：
   - embedding
   - embedding_dim
   - text_hash
   - source_path
   - to_json_dict / from_json_dict

2. 当前规范化契约：
   - vector
   - embedding_dimension
   - source_chunk_sha256
   - to_dict / from_dict
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any


SCHEMA_VERSION = 1


def normalize_embedding_vector(vector: tuple[float, ...] | list[float]) -> tuple[float, ...]:
    """把 embedding 向量规范化为非空 float tuple。"""

    if not vector:
        raise ValueError("embedding vector must not be empty")

    normalized: list[float] = []
    for value in vector:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("embedding vector values must be finite")
        normalized.append(number)

    return tuple(normalized)


def compute_embedding_record_id(
    *,
    chunk_id: str,
    embedding_model: str,
    embedding_model_version: str,
    embedding_dimension: int,
    source_chunk_sha256: str,
) -> str:
    """生成稳定 embedding record id。

    参数名保留 source_chunk_sha256，但为了兼容旧 text_hash，
    调用方也可以传入任意稳定 source fingerprint。
    """

    payload = "\n".join(
        [
            chunk_id.strip(),
            embedding_model.strip(),
            embedding_model_version.strip(),
            str(int(embedding_dimension)),
            source_chunk_sha256.strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _looks_like_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    return all(char in "0123456789abcdefABCDEF" for char in value)


@dataclass(frozen=True, init=False)
class ChunkEmbedding:
    """单个 chunk 的 embedding 记录。"""

    chunk_id: str
    paper_id: str
    embedding_model: str
    embedding_model_version: str
    embedding_dimension: int
    vector: tuple[float, ...]
    source_chunk_sha256: str
    text_hash: str
    source_path: str
    schema_version: int = SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding_id: str = ""

    def __init__(
        self,
        *,
        chunk_id: str,
        paper_id: str,
        embedding_model: str,
        embedding_model_version: str = "legacy",
        embedding_dimension: int | None = None,
        vector: tuple[float, ...] | list[float] | None = None,
        source_chunk_sha256: str = "",
        schema_version: int = SCHEMA_VERSION,
        metadata: dict[str, Any] | None = None,
        embedding_id: str = "",
        embedding: tuple[float, ...] | list[float] | None = None,
        embedding_dim: int | None = None,
        text_hash: str = "",
        source_path: str = "",
    ) -> None:
        if vector is None:
            vector = embedding
        elif embedding is not None and normalize_embedding_vector(vector) != normalize_embedding_vector(embedding):
            raise ValueError("vector and embedding aliases disagree")

        if embedding_dimension is None:
            embedding_dimension = embedding_dim
        elif embedding_dim is not None and int(embedding_dimension) != int(embedding_dim):
            raise ValueError("embedding_dimension and embedding_dim aliases disagree")

        if embedding_dimension is None:
            raise ValueError("embedding_dimension/embedding_dim must be provided")
        if vector is None:
            raise ValueError("embedding vector must not be empty")

        normalized_chunk_id = chunk_id.strip()
        normalized_paper_id = paper_id.strip()
        normalized_model = embedding_model.strip()
        normalized_model_version = embedding_model_version.strip()
        normalized_source_sha = source_chunk_sha256.strip()
        normalized_text_hash = text_hash.strip()
        normalized_source_path = source_path.strip()
        normalized_vector = normalize_embedding_vector(vector)
        normalized_dimension = int(embedding_dimension)

        if not normalized_chunk_id:
            raise ValueError("chunk_id must not be empty")
        if not normalized_paper_id:
            raise ValueError("paper_id must not be empty")
        if not normalized_model:
            raise ValueError("embedding_model must not be empty")
        if not normalized_model_version:
            raise ValueError("embedding_model_version must not be empty")
        if normalized_dimension <= 0:
            raise ValueError("embedding_dimension/embedding_dim must be positive")
        if normalized_dimension != len(normalized_vector):
            raise ValueError(
                "embedding_dimension must match vector length; "
                "embedding length does not match embedding_dim"
            )
        if normalized_source_sha and not _looks_like_sha256(normalized_source_sha):
            raise ValueError("source_chunk_sha256 must be a sha256 hex digest")
        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version: {schema_version}")

        source_fingerprint = (
            normalized_source_sha
            or normalized_text_hash
            or normalized_source_path
        )
        normalized_embedding_id = embedding_id.strip() or compute_embedding_record_id(
            chunk_id=normalized_chunk_id,
            embedding_model=normalized_model,
            embedding_model_version=normalized_model_version,
            embedding_dimension=normalized_dimension,
            source_chunk_sha256=source_fingerprint,
        )

        if not _looks_like_sha256(normalized_embedding_id):
            raise ValueError("embedding_id must be a sha256 hex digest")

        object.__setattr__(self, "chunk_id", normalized_chunk_id)
        object.__setattr__(self, "paper_id", normalized_paper_id)
        object.__setattr__(self, "embedding_model", normalized_model)
        object.__setattr__(self, "embedding_model_version", normalized_model_version)
        object.__setattr__(self, "embedding_dimension", normalized_dimension)
        object.__setattr__(self, "vector", normalized_vector)
        object.__setattr__(self, "source_chunk_sha256", normalized_source_sha)
        object.__setattr__(self, "text_hash", normalized_text_hash)
        object.__setattr__(self, "source_path", normalized_source_path)
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "metadata", dict(metadata or {}))
        object.__setattr__(self, "embedding_id", normalized_embedding_id)

    @property
    def embedding(self) -> tuple[float, ...]:
        """旧字段名 alias。"""

        return self.vector

    @property
    def embedding_dim(self) -> int:
        """旧字段名 alias。"""

        return self.embedding_dimension

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "embedding_id": self.embedding_id,
            "chunk_id": self.chunk_id,
            "paper_id": self.paper_id,
            "embedding_model": self.embedding_model,
            "embedding_model_version": self.embedding_model_version,
            "embedding_dimension": self.embedding_dimension,
            "vector": list(self.vector),
            "source_chunk_sha256": self.source_chunk_sha256,
            "text_hash": self.text_hash,
            "source_path": self.source_path,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChunkEmbedding":
        vector = data.get("vector", data.get("embedding"))
        embedding_dimension = data.get(
            "embedding_dimension",
            data.get("embedding_dim"),
        )

        return cls(
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            embedding_id=str(data.get("embedding_id", "")),
            chunk_id=str(data["chunk_id"]),
            paper_id=str(data["paper_id"]),
            embedding_model=str(data["embedding_model"]),
            embedding_model_version=str(data.get("embedding_model_version", "legacy")),
            embedding_dimension=int(embedding_dimension),
            vector=tuple(float(value) for value in vector),
            source_chunk_sha256=str(data.get("source_chunk_sha256", "")),
            text_hash=str(data.get("text_hash", "")),
            source_path=str(data.get("source_path", "")),
            metadata=dict(data.get("metadata", {})),
        )

    def to_json_dict(self) -> dict[str, Any]:
        """旧 JSON 契约。"""

        return {
            "schema_version": self.schema_version,
            "embedding_id": self.embedding_id,
            "chunk_id": self.chunk_id,
            "paper_id": self.paper_id,
            "embedding": list(self.vector),
            "embedding_model": self.embedding_model,
            "embedding_model_version": self.embedding_model_version,
            "embedding_dim": self.embedding_dimension,
            "text_hash": self.text_hash,
            "source_path": self.source_path,
            "source_chunk_sha256": self.source_chunk_sha256,
            "metadata": self.metadata,
        }

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "ChunkEmbedding":
        """旧 JSON 契约。"""

        return cls.from_dict(data)
