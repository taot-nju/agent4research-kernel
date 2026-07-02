import pytest

from ai4research.indexing_pipeline.embedding_config import (
    DEFAULT_EMBEDDING_API_KEY,
    DEFAULT_EMBEDDING_BASE_URL,
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_TIMEOUT_SECONDS,
    EMBEDDING_API_KEY_ENV,
    EMBEDDING_BASE_URL_ENV,
    EMBEDDING_DIMENSION_ENV,
    EMBEDDING_MODEL_ENV,
    EMBEDDING_TIMEOUT_ENV,
    EmbeddingServiceConfig,
    load_embedding_service_config,
)


def test_load_embedding_service_config_defaults(monkeypatch) -> None:
    for name in (
        EMBEDDING_BASE_URL_ENV,
        EMBEDDING_API_KEY_ENV,
        EMBEDDING_MODEL_ENV,
        EMBEDDING_TIMEOUT_ENV,
        EMBEDDING_DIMENSION_ENV,
    ):
        monkeypatch.delenv(name, raising=False)

    config = load_embedding_service_config()

    assert config.base_url == DEFAULT_EMBEDDING_BASE_URL
    assert config.api_key == DEFAULT_EMBEDDING_API_KEY
    assert config.model_name == DEFAULT_EMBEDDING_MODEL
    assert config.timeout_seconds == DEFAULT_EMBEDDING_TIMEOUT_SECONDS
    assert config.embedding_dimension == DEFAULT_EMBEDDING_DIMENSION


def test_load_embedding_service_config_from_environment(monkeypatch) -> None:
    monkeypatch.setenv(EMBEDDING_BASE_URL_ENV, "http://localhost:9999/v1/")
    monkeypatch.setenv(EMBEDDING_API_KEY_ENV, "test-key")
    monkeypatch.setenv(EMBEDDING_MODEL_ENV, "test-embedding")
    monkeypatch.setenv(EMBEDDING_TIMEOUT_ENV, "321")
    monkeypatch.setenv(EMBEDDING_DIMENSION_ENV, "384")

    config = load_embedding_service_config()

    assert config.base_url == "http://localhost:9999/v1"
    assert config.api_key == "test-key"
    assert config.model_name == "test-embedding"
    assert config.timeout_seconds == 321
    assert config.embedding_dimension == 384


def test_embedding_service_config_validates_values() -> None:
    with pytest.raises(ValueError, match="base_url"):
        EmbeddingServiceConfig(
            base_url="",
            api_key="key",
            model_name="model",
            timeout_seconds=1,
            embedding_dimension=1,
        )

    with pytest.raises(ValueError, match="embedding_dimension"):
        EmbeddingServiceConfig(
            base_url="http://localhost:9999/v1",
            api_key="key",
            model_name="model",
            timeout_seconds=1,
            embedding_dimension=0,
        )
