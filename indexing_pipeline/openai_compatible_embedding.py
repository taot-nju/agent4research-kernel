"""OpenAI-compatible embedding provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from ai4research.indexing_pipeline.embedding_config import (
    EmbeddingServiceConfig,
    load_embedding_service_config,
)


@dataclass(frozen=True)
class OpenAICompatibleEmbeddingProvider:
    """通过 OpenAI-compatible embeddings API 生成文本向量。"""

    config: EmbeddingServiceConfig | None = None
    client: Any | None = None
    input_max_chars: int | None = None

    @property
    def effective_config(self) -> EmbeddingServiceConfig:
        return self.config or load_embedding_service_config()

    @property
    def embedding_model(self) -> str:
        return self.effective_config.model_name

    @property
    def embedding_model_version(self) -> str:
        return "openai-compatible"

    @property
    def embedding_dimension(self) -> int:
        return self.effective_config.embedding_dimension

    def _get_client(self) -> Any:
        if self.client is not None:
            return self.client

        config = self.effective_config
        return OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=config.timeout_seconds,
        )

    def check_health(self) -> None:
        """检查 embedding 服务和目标模型是否可用。"""

        config = self.effective_config
        response = self._get_client().models.list()

        available_models = {
            str(model.id)
            for model in response.data
        }

        if config.model_name not in available_models:
            raise RuntimeError(
                "embedding 服务未加载目标模型："
                f"{config.model_name}; available={sorted(available_models)}"
            )

    def _normalize_text(self, text: str) -> str:
        normalized = text.strip()

        if self.input_max_chars is not None:
            if self.input_max_chars <= 0:
                raise ValueError("input_max_chars must be greater than 0")
            normalized = normalized[: self.input_max_chars].strip()

        if not normalized:
            raise ValueError("text must not be empty")

        return normalized

    def embed_text(self, text: str) -> tuple[float, ...]:
        normalized = self._normalize_text(text=text)

        config = self.effective_config
        response = self._get_client().embeddings.create(
            model=config.model_name,
            input=normalized,
        )

        if not response.data:
            raise RuntimeError("embedding 服务没有返回 data")

        vector = tuple(float(value) for value in response.data[0].embedding)

        if len(vector) != config.embedding_dimension:
            raise ValueError(
                "embedding dimension mismatch: "
                f"expected={config.embedding_dimension}, actual={len(vector)}"
            )

        return vector
