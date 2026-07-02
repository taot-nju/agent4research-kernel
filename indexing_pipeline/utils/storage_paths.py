"""标准 chunk 资产路径生成工具。"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai4research.fulltext_pipeline.config import (
    get_data_root,
)
from ai4research.fulltext_pipeline.utils.storage_paths import (
    validate_paper_id,
)


CHUNKS_DIRECTORY_NAME = "chunks"
CHUNKS_FILENAME = "chunks.jsonl"
CHUNK_MANIFEST_FILENAME = "manifest.json"

_SAFE_COMPONENT_PATTERN = re.compile(
    r"[^A-Za-z0-9._-]+"
)


@dataclass(frozen=True)
class ChunkAssetPaths:
    """一组特定切分配置对应的标准资产路径。"""

    relative_directory: Path
    absolute_directory: Path

    chunks_jsonl_path: Path
    manifest_path: Path


def _normalize_splitter_options(
    options: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(options, Mapping):
        raise TypeError(
            "splitter_options 必须是 Mapping"
        )

    try:
        encoded = json.dumps(
            dict(options),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "splitter_options 必须可序列化为 JSON"
        ) from error

    decoded = json.loads(encoded)

    if not isinstance(decoded, dict):
        raise TypeError(
            "splitter_options 必须是 JSON object"
        )

    return decoded


def _safe_path_component(
    field_name: str,
    value: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"{field_name} 必须是字符串"
        )

    normalized = value.strip()

    if not normalized:
        raise ValueError(
            f"{field_name} 不能为空"
        )

    safe_value = _SAFE_COMPONENT_PATTERN.sub(
        "-",
        normalized,
    ).strip(".-_")

    if not safe_value:
        raise ValueError(
            f"{field_name} 不能生成安全路径组件"
        )

    return safe_value


def fingerprint_splitter_config(
    *,
    splitter_name: str,
    splitter_version: str,
    splitter_options: Mapping[str, Any],
) -> str:
    """生成稳定的切分配置指纹。"""

    payload = {
        "splitter_name": splitter_name.strip(),
        "splitter_version": (
            splitter_version.strip()
        ),
        "splitter_options": (
            _normalize_splitter_options(
                splitter_options
            )
        ),
    }

    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

    return hashlib.sha256(
        canonical_payload.encode("utf-8")
    ).hexdigest()[:16]


def get_chunk_relative_directory(
    *,
    paper_id: str,
    splitter_name: str,
    splitter_version: str,
    splitter_options: Mapping[str, Any],
) -> Path:
    """返回 chunk 资产相对于数据根目录的路径。"""

    normalized_paper_id = validate_paper_id(
        paper_id
    )
    safe_splitter_name = _safe_path_component(
        "splitter_name",
        splitter_name,
    )
    safe_splitter_version = (
        _safe_path_component(
            "splitter_version",
            splitter_version,
        )
    )
    config_fingerprint = (
        fingerprint_splitter_config(
            splitter_name=splitter_name,
            splitter_version=splitter_version,
            splitter_options=splitter_options,
        )
    )

    return (
        Path(CHUNKS_DIRECTORY_NAME)
        / normalized_paper_id[:2]
        / normalized_paper_id[2:4]
        / normalized_paper_id
        / safe_splitter_name
        / (
            f"{safe_splitter_version}-"
            f"{config_fingerprint}"
        )
    )


def build_chunk_asset_paths(
    *,
    paper_id: str,
    splitter_name: str,
    splitter_version: str,
    splitter_options: Mapping[str, Any],
) -> ChunkAssetPaths:
    """生成 chunk JSONL 与 manifest 的绝对和相对路径。"""

    relative_directory = (
        get_chunk_relative_directory(
            paper_id=paper_id,
            splitter_name=splitter_name,
            splitter_version=splitter_version,
            splitter_options=splitter_options,
        )
    )
    absolute_directory = (
        get_data_root()
        / relative_directory
    )

    return ChunkAssetPaths(
        relative_directory=relative_directory,
        absolute_directory=absolute_directory,
        chunks_jsonl_path=(
            absolute_directory
            / CHUNKS_FILENAME
        ),
        manifest_path=(
            absolute_directory
            / CHUNK_MANIFEST_FILENAME
        ),
    )


def ensure_chunk_asset_directory(
    paths: ChunkAssetPaths,
) -> None:
    """创建 chunk 资产目录，但不创建空资产文件。"""

    paths.absolute_directory.mkdir(
        parents=True,
        exist_ok=True,
    )


def to_data_root_relative_path(
    path: str | Path,
) -> Path:
    """将数据根目录下的路径转换为相对路径。"""

    absolute_path = Path(
        path
    ).expanduser().resolve()
    data_root = (
        get_data_root()
        .expanduser()
        .resolve()
    )

    try:
        return absolute_path.relative_to(
            data_root
        )
    except ValueError as error:
        raise ValueError(
            f"路径不属于资产根目录：{absolute_path}"
        ) from error
