"""Audit embedding JSONL cache/run outputs.

最小手工入口：递归扫描 embeddings.jsonl，统计 embedding 数量、
模型/维度分布、subchunk 使用情况和重复 embedding_id。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

from ai4research.indexing_pipeline.repositories.jsonl_embedding import (
    JsonlChunkEmbeddingRepository,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "递归扫描 embedding root 下的 embeddings.jsonl，"
            "输出 embedding/subchunk/cache 健康统计。"
        )
    )
    parser.add_argument(
        "--embedding-root",
        required=True,
        help="embedding cache/run 根目录；会递归查找 embeddings.jsonl",
    )
    parser.add_argument(
        "--save-json",
        help="可选：保存 audit JSON 报告路径",
    )
    parser.add_argument(
        "--show-examples",
        type=int,
        default=5,
        help="终端展示 subchunk 示例数量，默认 5；0 表示不展示",
    )
    return parser


def _counter_to_dict(counter: Counter[Any]) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in sorted(
            counter.items(),
            key=lambda item: str(item[0]),
        )
    }


def audit_embedding_root(
    *,
    embedding_root: Path,
    show_examples: int = 5,
) -> dict[str, Any]:
    root = embedding_root.expanduser().resolve()

    if not root.exists():
        raise FileNotFoundError(f"embedding_root not found: {root}")

    paths = sorted(root.rglob("embeddings.jsonl"))
    repository = JsonlChunkEmbeddingRepository()

    embedding_ids: Counter[str] = Counter()
    paper_ids: set[str] = set()
    model_counter: Counter[str] = Counter()
    dimension_counter: Counter[int] = Counter()
    file_embedding_counts: dict[str, int] = {}
    read_errors: dict[str, str] = {}

    total_embeddings = 0
    subchunk_embeddings = 0
    source_chunks_with_subchunks: set[str] = set()
    papers_with_subchunks: set[str] = set()
    max_subchunk_count = 0
    max_char_end = 0
    subchunk_examples: list[dict[str, Any]] = []

    for path in paths:
        relative_path = str(path.relative_to(root))

        try:
            result = repository.read_embeddings(path=path)
        except Exception as error:
            read_errors[relative_path] = f"{type(error).__name__}: {error}"
            continue

        file_embedding_counts[relative_path] = result.embedding_count

        for embedding in result.embeddings:
            total_embeddings += 1
            paper_ids.add(embedding.paper_id)
            model_counter[
                f"{embedding.embedding_model}@{embedding.embedding_model_version}"
            ] += 1
            dimension_counter[embedding.embedding_dimension] += 1

            if embedding.embedding_id:
                embedding_ids[embedding.embedding_id] += 1

            metadata = embedding.metadata
            is_subchunk = bool(metadata.get("is_subchunk"))
            source_chunk_id = str(
                metadata.get("source_chunk_id", embedding.chunk_id)
            )

            if is_subchunk:
                subchunk_embeddings += 1
                source_chunks_with_subchunks.add(source_chunk_id)
                papers_with_subchunks.add(embedding.paper_id)

                try:
                    max_subchunk_count = max(
                        max_subchunk_count,
                        int(metadata.get("subchunk_count", 0)),
                    )
                except (TypeError, ValueError):
                    pass

                try:
                    max_char_end = max(
                        max_char_end,
                        int(metadata.get("char_end", 0)),
                    )
                except (TypeError, ValueError):
                    pass

                if len(subchunk_examples) < show_examples:
                    subchunk_examples.append({
                        "embedding_file": relative_path,
                        "paper_id": embedding.paper_id,
                        "embedding_chunk_id": embedding.chunk_id,
                        "source_chunk_id": source_chunk_id,
                        "subchunk_index": metadata.get("subchunk_index"),
                        "subchunk_count": metadata.get("subchunk_count"),
                        "char_start": metadata.get("char_start"),
                        "char_end": metadata.get("char_end"),
                    })

    duplicate_embedding_ids = {
        embedding_id: count
        for embedding_id, count in embedding_ids.items()
        if count > 1
    }

    return {
        "embedding_root": str(root),
        "embedding_files": len(paths),
        "readable_embedding_files": len(file_embedding_counts),
        "read_error_count": len(read_errors),
        "read_errors": read_errors,
        "total_embeddings": total_embeddings,
        "paper_count": len(paper_ids),
        "model_distribution": _counter_to_dict(model_counter),
        "dimension_distribution": _counter_to_dict(dimension_counter),
        "subchunk_embeddings": subchunk_embeddings,
        "source_chunks_with_subchunks": len(source_chunks_with_subchunks),
        "papers_with_subchunks": len(papers_with_subchunks),
        "max_subchunk_count": max_subchunk_count,
        "max_char_end": max_char_end,
        "duplicate_embedding_id_count": len(duplicate_embedding_ids),
        "duplicate_embedding_ids": duplicate_embedding_ids,
        "file_embedding_counts": file_embedding_counts,
        "subchunk_examples": subchunk_examples,
    }


def print_report(report: dict[str, Any]) -> None:
    print("=" * 100)
    print("Embedding run audit")
    print("=" * 100)
    print(f"embedding_root:                {report['embedding_root']}")
    print(f"embedding_files:               {report['embedding_files']}")
    print(f"readable_embedding_files:      {report['readable_embedding_files']}")
    print(f"read_error_count:              {report['read_error_count']}")
    print(f"total_embeddings:              {report['total_embeddings']}")
    print(f"paper_count:                   {report['paper_count']}")
    print(f"model_distribution:            {report['model_distribution']}")
    print(f"dimension_distribution:        {report['dimension_distribution']}")
    print(f"subchunk_embeddings:           {report['subchunk_embeddings']}")
    print(f"source_chunks_with_subchunks:  {report['source_chunks_with_subchunks']}")
    print(f"papers_with_subchunks:         {report['papers_with_subchunks']}")
    print(f"max_subchunk_count:            {report['max_subchunk_count']}")
    print(f"max_char_end:                  {report['max_char_end']}")
    print(f"duplicate_embedding_id_count:  {report['duplicate_embedding_id_count']}")

    examples = report["subchunk_examples"]
    if examples:
        print("-" * 100)
        print("subchunk_examples:")
        for index, example in enumerate(examples, start=1):
            print(f"[{index}] {example}")

    if report["read_errors"]:
        print("-" * 100)
        print("read_errors:")
        for path, error in report["read_errors"].items():
            print(f"{path}: {error}")

    print("=" * 100)


def _save_json(path: str | Path, payload: dict[str, Any]) -> Path:
    resolved_path = Path(path).expanduser().resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return resolved_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    report = audit_embedding_root(
        embedding_root=Path(args.embedding_root),
        show_examples=args.show_examples,
    )
    print_report(report)

    if args.save_json:
        saved_path = _save_json(args.save_json, report)
        print(f"JSON report saved: {saved_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
