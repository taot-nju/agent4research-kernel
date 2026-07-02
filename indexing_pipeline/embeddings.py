"""Embedding provider interfaces and deterministic demo embedders.

这里有两个本地 demo provider：

1. DeterministicHashEmbeddingProvider
   - 对整段文本做哈希；
   - 只保证稳定；
   - 不具备词汇或语义相似性。

2. TokenHashEmbeddingProvider
   - 对 token 做 hashing trick；
   - 相同 token 会落到相同维度；
   - 不是真正语义 embedding，但适合本地闭环 demo 和测试。
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Protocol


class TextEmbeddingProvider(Protocol):
    embedding_model: str
    embedding_model_version: str
    embedding_dimension: int

    def embed_text(self, text: str) -> tuple[float, ...]:
        ...


@dataclass(frozen=True)
class DeterministicHashEmbeddingProvider:
    """基于整段文本哈希的确定性 demo embedding provider。"""

    embedding_dimension: int = 32
    embedding_model: str = "deterministic-hash-embedding"
    embedding_model_version: str = "1"

    def __post_init__(self) -> None:
        if self.embedding_dimension <= 0:
            raise ValueError("embedding_dimension must be positive")

    def embed_text(self, text: str) -> tuple[float, ...]:
        normalized = text.strip()
        if not normalized:
            raise ValueError("text must not be empty")

        values: list[float] = []
        counter = 0

        while len(values) < self.embedding_dimension:
            payload = f"{counter}\n{normalized}".encode("utf-8")
            digest = hashlib.sha256(payload).digest()

            for byte in digest:
                value = (byte / 127.5) - 1.0
                values.append(value)
                if len(values) >= self.embedding_dimension:
                    break

            counter += 1

        return _l2_normalize(values)


@dataclass(frozen=True)
class TokenHashEmbeddingProvider:
    """基于 token hashing trick 的本地 demo embedding provider。"""

    embedding_dimension: int = 128
    embedding_model: str = "token-hash-embedding"
    embedding_model_version: str = "1"

    def __post_init__(self) -> None:
        if self.embedding_dimension <= 0:
            raise ValueError("embedding_dimension must be positive")

    def embed_text(self, text: str) -> tuple[float, ...]:
        normalized = text.strip()
        if not normalized:
            raise ValueError("text must not be empty")

        tokens = _tokenize(normalized)
        if not tokens:
            return DeterministicHashEmbeddingProvider(
                embedding_dimension=self.embedding_dimension,
            ).embed_text(normalized)

        values = [0.0 for _ in range(self.embedding_dimension)]

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:8], "big") % self.embedding_dimension
            sign = 1.0 if digest[8] % 2 == 0 else -1.0
            values[bucket] += sign

        return _l2_normalize(values)


def _tokenize(text: str) -> tuple[str, ...]:
    return tuple(
        match.group(0).lower()
        for match in re.finditer(r"[A-Za-z0-9_]+", text)
    )


def _l2_normalize(values: list[float]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0.0:
        return tuple(values)
    return tuple(value / norm for value in values)
