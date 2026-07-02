"""对 query 与候选文本执行 OpenAI-compatible rerank 的手工入口。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = (
    os.getenv("AI4RESEARCH_RERANK_BASE_URL")
    or os.getenv("AI4RESEARCH_EMBEDDING_BASE_URL")
    or "http://127.0.0.1:7000/v1"
)
DEFAULT_API_KEY = (
    os.getenv("AI4RESEARCH_RERANK_API_KEY")
    or os.getenv("AI4RESEARCH_EMBEDDING_API_KEY")
    or "EMPTY"
)
DEFAULT_MODEL = (
    os.getenv("AI4RESEARCH_RERANK_MODEL")
    or os.getenv("AI4RESEARCH_EMBEDDING_MODEL")
    or "bge-m3"
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "调用 OpenAI-compatible /v1/rerank，"
            "对一条 query 与多条候选文本进行相关性重排。"
        )
    )
    parser.add_argument(
        "--query",
        required=True,
        help="检索 query",
    )
    parser.add_argument(
        "--document",
        action="append",
        required=True,
        help="候选文本；可重复传入多次",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=(
            "OpenAI-compatible 服务 base URL；默认读取 "
            "AI4RESEARCH_RERANK_BASE_URL，随后回退 embedding 配置"
        ),
    )
    parser.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY,
        help=(
            "服务 API key；默认读取 AI4RESEARCH_RERANK_API_KEY，"
            "随后回退 embedding 配置"
        ),
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=(
            "rerank 模型；默认读取 AI4RESEARCH_RERANK_MODEL，"
            "随后回退 embedding 模型配置"
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="HTTP 请求超时秒数，默认 60",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=180,
        help="每条候选文本的终端预览字符数，默认 180",
    )
    parser.add_argument(
        "--save-json",
        help="可选：保存 rerank 结果 JSON 路径",
    )
    return parser


def _preview(text: str, limit: int) -> str:
    normalized = " ".join(text.split())

    if len(normalized) <= limit:
        return normalized

    return normalized[:limit] + "..."


def _post_rerank(
    *,
    base_url: str,
    api_key: str,
    model: str,
    query: str,
    documents: list[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    endpoint = base_url.rstrip("/") + "/rerank"
    payload = json.dumps(
        {
            "model": model,
            "query": query,
            "documents": documents,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
    }

    if api_key.strip():
        headers["Authorization"] = (
            f"Bearer {api_key.strip()}"
        )

    request = Request(
        endpoint,
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            body = response.read().decode("utf-8")
    except HTTPError as error:
        detail = error.read().decode(
            "utf-8",
            errors="replace",
        )
        raise RuntimeError(
            f"rerank request failed: HTTP {error.code}: "
            f"{detail}"
        ) from error
    except URLError as error:
        raise RuntimeError(
            f"rerank request failed: {error.reason}"
        ) from error

    data = json.loads(body)

    if not isinstance(data, dict):
        raise ValueError(
            "rerank response 必须是 JSON object"
        )

    return data


def _normalized_results(
    response: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_results = response.get("results")

    if not isinstance(raw_results, list):
        raise ValueError(
            "rerank response 缺少 results list"
        )

    results: list[dict[str, Any]] = []

    for item in raw_results:
        if not isinstance(item, dict):
            raise ValueError(
                "rerank result 必须是 JSON object"
            )

        document = item.get("document", {})

        if not isinstance(document, dict):
            document = {}

        results.append(
            {
                "original_index": int(item["index"]),
                "relevance_score": float(
                    item["relevance_score"]
                ),
                "text": str(document.get("text", "")),
            }
        )

    return sorted(
        results,
        key=lambda item: (
            -item["relevance_score"],
            item["original_index"],
        ),
    )


def _save_json(
    *,
    path: str,
    payload: dict[str, Any],
) -> Path:
    resolved = Path(path).expanduser().resolve()
    resolved.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    resolved.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return resolved


def main(
    argv: Sequence[str] | None = None,
) -> int:
    args = build_argument_parser().parse_args(argv)

    query = args.query.strip()
    documents = [
        document.strip()
        for document in args.document
    ]

    if not query:
        raise ValueError("query 不能为空")

    if any(not document for document in documents):
        raise ValueError(
            "document 不能包含空文本"
        )

    if args.timeout_seconds <= 0:
        raise ValueError(
            "timeout_seconds 必须大于 0"
        )

    if args.preview_chars < 0:
        raise ValueError(
            "preview_chars 不能小于 0"
        )

    response = _post_rerank(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model.strip(),
        query=query,
        documents=documents,
        timeout_seconds=args.timeout_seconds,
    )
    results = _normalized_results(response)

    report = {
        "query": query,
        "model": args.model.strip(),
        "base_url": args.base_url.rstrip("/"),
        "document_count": len(documents),
        "response_id": response.get("id", ""),
        "usage": response.get("usage", {}),
        "results": results,
    }

    print("=" * 100)
    print("Rerank text result")
    print("=" * 100)
    print(f"model:          {report['model']}")
    print(f"document_count: {report['document_count']}")
    print(f"query:          {query}")
    print("-" * 100)

    for rank, item in enumerate(
        results,
        start=1,
    ):
        print(
            f"rank={rank} "
            f"score={item['relevance_score']:.6f} "
            f"original_index={item['original_index']}"
        )
        print(
            "text: "
            + _preview(
                item["text"],
                args.preview_chars,
            )
        )

    if args.save_json:
        saved_path = _save_json(
            path=args.save_json,
            payload=report,
        )
        print("-" * 100)
        print(f"JSON report saved: {saved_path}")

    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
