import pytest

from ai4research.indexing_pipeline.embedding_config import EmbeddingServiceConfig
from ai4research.indexing_pipeline.openai_compatible_embedding import (
    OpenAICompatibleEmbeddingProvider,
)


class _Model:
    def __init__(self, model_id: str) -> None:
        self.id = model_id


class _Models:
    def __init__(self, model_ids):
        self._model_ids = model_ids

    def list(self):
        return type(
            "ModelListResponse",
            (),
            {"data": [_Model(model_id) for model_id in self._model_ids]},
        )()


class _EmbeddingData:
    def __init__(self, embedding):
        self.embedding = embedding


class _Embeddings:
    def __init__(self, embedding):
        self._embedding = embedding
        self.last_model = ""
        self.last_input = ""

    def create(self, *, model: str, input: str):
        self.last_model = model
        self.last_input = input
        return type(
            "EmbeddingResponse",
            (),
            {"data": [_EmbeddingData(self._embedding)]},
        )()


class _Client:
    def __init__(self, *, model_ids, embedding):
        self.models = _Models(model_ids)
        self.embeddings = _Embeddings(embedding)


def _config(dimension: int = 3) -> EmbeddingServiceConfig:
    return EmbeddingServiceConfig(
        base_url="http://localhost:9999/v1",
        api_key="EMPTY",
        model_name="test-embedding",
        timeout_seconds=30,
        embedding_dimension=dimension,
    )


def test_openai_compatible_embedding_provider_embeds_text() -> None:
    client = _Client(
        model_ids=["test-embedding"],
        embedding=[0.1, 0.2, 0.3],
    )
    provider = OpenAICompatibleEmbeddingProvider(
        config=_config(),
        client=client,
    )

    vector = provider.embed_text(" agent memory ")

    assert vector == (0.1, 0.2, 0.3)
    assert provider.embedding_model == "test-embedding"
    assert provider.embedding_model_version == "openai-compatible"
    assert provider.embedding_dimension == 3
    assert client.embeddings.last_model == "test-embedding"
    assert client.embeddings.last_input == "agent memory"


def test_openai_compatible_embedding_provider_checks_health() -> None:
    provider = OpenAICompatibleEmbeddingProvider(
        config=_config(),
        client=_Client(
            model_ids=["test-embedding"],
            embedding=[0.1, 0.2, 0.3],
        ),
    )

    provider.check_health()


def test_openai_compatible_embedding_provider_health_reports_missing_model() -> None:
    provider = OpenAICompatibleEmbeddingProvider(
        config=_config(),
        client=_Client(
            model_ids=["other-model"],
            embedding=[0.1, 0.2, 0.3],
        ),
    )

    with pytest.raises(RuntimeError, match="未加载目标模型"):
        provider.check_health()


def test_openai_compatible_embedding_provider_rejects_dimension_mismatch() -> None:
    provider = OpenAICompatibleEmbeddingProvider(
        config=_config(dimension=4),
        client=_Client(
            model_ids=["test-embedding"],
            embedding=[0.1, 0.2, 0.3],
        ),
    )

    with pytest.raises(ValueError, match="embedding dimension mismatch"):
        provider.embed_text("agent memory")


def test_openai_compatible_embedding_provider_rejects_empty_text() -> None:
    provider = OpenAICompatibleEmbeddingProvider(
        config=_config(),
        client=_Client(
            model_ids=["test-embedding"],
            embedding=[0.1, 0.2, 0.3],
        ),
    )

    with pytest.raises(ValueError, match="text must not be empty"):
        provider.embed_text("   ")


class _FakeEmbeddingItem:
    def __init__(self, embedding):
        self.embedding = embedding


class _FakeEmbeddingResponse:
    def __init__(self, embedding):
        self.data = [_FakeEmbeddingItem(embedding)]


class _RecordingEmbeddingsClient:
    def __init__(self):
        self.input_seen = None

    def create(self, *, model, input):
        self.input_seen = input
        return _FakeEmbeddingResponse([0.1, 0.2, 0.3])


class _RecordingClient:
    def __init__(self):
        self.embeddings = _RecordingEmbeddingsClient()


def test_openai_compatible_embedding_truncates_input_before_request():
    client = _RecordingClient()
    provider = OpenAICompatibleEmbeddingProvider(
        config=EmbeddingServiceConfig(
            base_url="http://127.0.0.1:7000/v1",
            api_key="EMPTY",
            model_name="bge-m3",
            timeout_seconds=30,
            embedding_dimension=3,
        ),
        client=client,
        input_max_chars=5,
    )

    vector = provider.embed_text("abcdefghijk")

    assert vector == (0.1, 0.2, 0.3)
    assert client.embeddings.input_seen == "abcde"
