"""单文本 embedding 手工测试入口。

这是 operator-facing CLI，用于单独测试 embedding provider。

当前支持：

- token-hash：本地 demo provider，适合验证 vector pipeline；
- deterministic-hash：整段文本哈希 provider，适合稳定性测试。

后续真实 embedding API 会接入同一个入口，例如 openai-compatible provider。
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from ai4research.indexing_pipeline.embeddings import (
    DeterministicHashEmbeddingProvider,
    TokenHashEmbeddingProvider,
)
from ai4research.indexing_pipeline.embedding_config import (
    load_embedding_service_config,
)
from ai4research.indexing_pipeline.openai_compatible_embedding import (
    OpenAICompatibleEmbeddingProvider,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="对单段文本生成 embedding，用于手工测试 embedding provider。"
    )
    parser.add_argument(
        "--text",
        required=True,
        help="要生成 embedding 的文本",
    )
    parser.add_argument(
        "--provider",
        choices=("token-hash", "deterministic-hash", "openai-compatible"),
        default="token-hash",
        help="embedding provider，默认 token-hash",
    )
    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=256,
        help="embedding 维度，默认 256",
    )
    parser.add_argument(
        "--preview-values",
        type=int,
        default=8,
        help="终端中预览前多少个向量值，默认 8",
    )
    parser.add_argument(
        "--print-vector",
        action="store_true",
        help="是否在终端打印完整向量",
    )
    parser.add_argument(
        "--save-json",
        help="可选：保存 embedding JSON 到指定路径",
    )
    return parser.parse_args()


def build_provider(*, provider_name: str, embedding_dim: int):
    if provider_name == "token-hash":
        return TokenHashEmbeddingProvider(
            embedding_dimension=embedding_dim,
        )

    if provider_name == "deterministic-hash":
        return DeterministicHashEmbeddingProvider(
            embedding_dimension=embedding_dim,
        )

    if provider_name == "openai-compatible":
        config = load_embedding_service_config()
        if embedding_dim != config.embedding_dimension:
            raise ValueError(
                "embedding_dim must match AI4RESEARCH_EMBEDDING_DIMENSION "
                f"for openai-compatible provider: expected={config.embedding_dimension}, got={embedding_dim}"
            )
        return OpenAICompatibleEmbeddingProvider(config=config)

    raise ValueError(f"unsupported provider: {provider_name}")


def vector_norm(vector: tuple[float, ...]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def build_result(*, args: argparse.Namespace) -> dict[str, Any]:
    provider = build_provider(
        provider_name=args.provider,
        embedding_dim=args.embedding_dim,
    )
    vector = provider.embed_text(args.text)

    return {
        "success": True,
        "provider": args.provider,
        "embedding_model": provider.embedding_model,
        "embedding_model_version": provider.embedding_model_version,
        "embedding_dimension": provider.embedding_dimension,
        "text": args.text,
        "vector_norm": vector_norm(vector),
        "vector": list(vector),
    }


def print_result(result: dict[str, Any], *, preview_values: int, print_vector: bool) -> None:
    vector = result["vector"]
    preview = vector[:preview_values]

    print("=" * 100)
    print("Embedding text result")
    print("=" * 100)
    print(f"provider:                {result['provider']}")
    print(f"embedding_model:         {result['embedding_model']}")
    print(f"embedding_model_version: {result['embedding_model_version']}")
    print(f"embedding_dimension:     {result['embedding_dimension']}")
    print(f"vector_norm:             {result['vector_norm']:.6f}")
    print(f"text:                    {result['text']}")
    print(f"vector_preview:          {preview}")

    if print_vector:
        print("-" * 100)
        print("vector:")
        print(json.dumps(vector, ensure_ascii=False))

    print("=" * 100)


def main() -> None:
    args = parse_args()
    result = build_result(args=args)
    print_result(
        result,
        preview_values=args.preview_values,
        print_vector=args.print_vector,
    )

    if args.save_json:
        save_path = Path(args.save_json).expanduser().resolve()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"JSON report saved: {save_path}")


if __name__ == "__main__":
    main()
