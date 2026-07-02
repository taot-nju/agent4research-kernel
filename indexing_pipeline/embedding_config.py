"""Embedding 服务配置。

当前用于 OpenAI-compatible embedding 服务。
服务地址、模型、维度和凭据均可通过环境变量替换，上层 pipeline 不应硬编码。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


EMBEDDING_BASE_URL_ENV = "AI4RESEARCH_EMBEDDING_BASE_URL"
EMBEDDING_API_KEY_ENV = "AI4RESEARCH_EMBEDDING_API_KEY"
EMBEDDING_MODEL_ENV = "AI4RESEARCH_EMBEDDING_MODEL"
EMBEDDING_TIMEOUT_ENV = "AI4RESEARCH_EMBEDDING_TIMEOUT_SECONDS"
EMBEDDING_DIMENSION_ENV = "AI4RESEARCH_EMBEDDING_DIMENSION"

DEFAULT_EMBEDDING_BASE_URL = "http://127.0.0.1:9001/v1"
DEFAULT_EMBEDDING_API_KEY = "EMPTY"
DEFAULT_EMBEDDING_MODEL = "embedding-model"
DEFAULT_EMBEDDING_TIMEOUT_SECONDS = 120
DEFAULT_EMBEDDING_DIMENSION = 1024


@dataclass(frozen=True)
class EmbeddingServiceConfig:
    """OpenAI-compatible embedding 服务连接配置。"""

    base_url: str
    api_key: str
    model_name: str
    timeout_seconds: int
    embedding_dimension: int

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("embedding base_url 不能为空")

        if not self.api_key.strip():
            raise ValueError("embedding api_key 不能为空")

        if not self.model_name.strip():
            raise ValueError("embedding model_name 不能为空")

        if self.timeout_seconds <= 0:
            raise ValueError("embedding timeout_seconds 必须大于 0")

        if self.embedding_dimension <= 0:
            raise ValueError("embedding_dimension 必须大于 0")


def _read_positive_int(
    environment_name: str,
    default: int,
) -> int:
    raw_value = os.getenv(environment_name)

    if raw_value is None or not raw_value.strip():
        return default

    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(
            f"{environment_name} 必须是整数"
        ) from error

    if value <= 0:
        raise ValueError(
            f"{environment_name} 必须大于 0"
        )

    return value


def load_embedding_service_config() -> EmbeddingServiceConfig:
    """从环境变量读取 embedding 服务配置。"""

    return EmbeddingServiceConfig(
        base_url=os.getenv(
            EMBEDDING_BASE_URL_ENV,
            DEFAULT_EMBEDDING_BASE_URL,
        ).strip().rstrip("/"),
        api_key=os.getenv(
            EMBEDDING_API_KEY_ENV,
            DEFAULT_EMBEDDING_API_KEY,
        ).strip(),
        model_name=os.getenv(
            EMBEDDING_MODEL_ENV,
            DEFAULT_EMBEDDING_MODEL,
        ).strip(),
        timeout_seconds=_read_positive_int(
            EMBEDDING_TIMEOUT_ENV,
            DEFAULT_EMBEDDING_TIMEOUT_SECONDS,
        ),
        embedding_dimension=_read_positive_int(
            EMBEDDING_DIMENSION_ENV,
            DEFAULT_EMBEDDING_DIMENSION,
        ),
    )
