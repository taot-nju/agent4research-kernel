import math

import pytest

from ai4research.indexing_pipeline.embeddings import (
    DeterministicHashEmbeddingProvider,
    TokenHashEmbeddingProvider,
)


def test_deterministic_hash_embedding_provider_is_stable() -> None:
    provider = DeterministicHashEmbeddingProvider(embedding_dimension=8)

    first = provider.embed_text("agent memory trajectory")
    second = provider.embed_text("agent memory trajectory")

    assert first == second
    assert len(first) == 8
    assert math.sqrt(sum(value * value for value in first)) == pytest.approx(1.0)


def test_deterministic_hash_embedding_provider_differs_for_different_texts() -> None:
    provider = DeterministicHashEmbeddingProvider(embedding_dimension=8)

    first = provider.embed_text("agent memory trajectory")
    second = provider.embed_text("multi agent planning")

    assert first != second


def test_deterministic_hash_embedding_provider_rejects_empty_text() -> None:
    provider = DeterministicHashEmbeddingProvider(embedding_dimension=8)

    with pytest.raises(ValueError, match="text must not be empty"):
        provider.embed_text("   ")


def test_deterministic_hash_embedding_provider_rejects_bad_dimension() -> None:
    with pytest.raises(ValueError, match="embedding_dimension must be positive"):
        DeterministicHashEmbeddingProvider(embedding_dimension=0)


def test_token_hash_embedding_provider_is_stable_and_normalized() -> None:
    provider = TokenHashEmbeddingProvider(embedding_dimension=32)

    first = provider.embed_text("agent memory trajectory")
    second = provider.embed_text("agent memory trajectory")

    assert first == second
    assert len(first) == 32
    assert math.sqrt(sum(value * value for value in first)) == pytest.approx(1.0)


def test_token_hash_embedding_provider_gives_higher_score_to_shared_tokens() -> None:
    provider = TokenHashEmbeddingProvider(embedding_dimension=128)

    query = provider.embed_text("agent memory trajectory clustering")
    close = provider.embed_text("agent trajectory memory clustering for experience organization")
    far = provider.embed_text("image segmentation color histogram convolution")

    close_score = sum(left * right for left, right in zip(query, close))
    far_score = sum(left * right for left, right in zip(query, far))

    assert close_score > far_score


def test_token_hash_embedding_provider_falls_back_for_text_without_tokens() -> None:
    provider = TokenHashEmbeddingProvider(embedding_dimension=32)

    first = provider.embed_text("!!!")
    second = provider.embed_text("!!!")

    assert first == second
    assert len(first) == 32
    assert math.sqrt(sum(value * value for value in first)) == pytest.approx(1.0)
