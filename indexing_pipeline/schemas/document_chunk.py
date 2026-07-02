"""可检索论文片段的数据结构与稳定 ID。"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


DOCUMENT_CHUNK_SCHEMA_VERSION = 1

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def compute_text_sha256(text: str) -> str:
    """计算文本内容的 SHA256。"""

    if not isinstance(text, str):
        raise TypeError("text 必须是字符串")

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def _normalize_options(
    options: Mapping[str, Any],
) -> dict[str, Any]:
    """复制并验证切分器配置可以稳定序列化。"""

    if not isinstance(options, Mapping):
        raise TypeError(
            "splitter_options 必须是 Mapping"
        )

    copied = dict(options)

    if any(
        not isinstance(key, str)
        for key in copied
    ):
        raise TypeError(
            "splitter_options 的键必须是字符串"
        )

    try:
        encoded = json.dumps(
            copied,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "splitter_options 必须可序列化为 JSON"
        ) from error

    return json.loads(encoded)


def build_chunk_id(
    *,
    paper_id: str,
    chunk_index: int,
    content_sha256: str,
    page_start: int,
    page_end: int,
    section_path: Sequence[str],
    source_markdown_sha256: str,
    source_pdf_sha256: str,
    source_parser_name: str,
    source_parser_version: str,
    splitter_name: str,
    splitter_version: str,
    splitter_options: Mapping[str, Any],
) -> str:
    """根据来源、切分配置与内容生成稳定 chunk ID。"""

    payload = {
        "schema_version": (
            DOCUMENT_CHUNK_SCHEMA_VERSION
        ),
        "paper_id": paper_id,
        "chunk_index": chunk_index,
        "content_sha256": content_sha256,
        "page_start": page_start,
        "page_end": page_end,
        "section_path": list(section_path),
        "source_markdown_sha256": (
            source_markdown_sha256
        ),
        "source_pdf_sha256": source_pdf_sha256,
        "source_parser_name": source_parser_name,
        "source_parser_version": (
            source_parser_version
        ),
        "splitter_name": splitter_name,
        "splitter_version": splitter_version,
        "splitter_options": _normalize_options(
            splitter_options
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
    ).hexdigest()


@dataclass(frozen=True)
class DocumentChunk:
    """一段可重复生成、可检索、可引用的论文正文。"""

    chunk_id: str
    paper_id: str
    chunk_index: int

    text: str
    char_count: int
    content_sha256: str

    page_start: int
    page_end: int
    section_path: tuple[str, ...]

    source_markdown_relative_path: str
    source_markdown_sha256: str
    source_pdf_sha256: str
    source_parser_name: str
    source_parser_version: str

    splitter_name: str
    splitter_version: str
    splitter_options: dict[str, Any]

    schema_version: int = (
        DOCUMENT_CHUNK_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != DOCUMENT_CHUNK_SCHEMA_VERSION
        ):
            raise ValueError(
                "不支持的 chunk schema_version"
            )

        if not self.paper_id.strip():
            raise ValueError("paper_id 不能为空")

        if (
            not isinstance(self.chunk_index, int)
            or isinstance(self.chunk_index, bool)
            or self.chunk_index < 0
        ):
            raise ValueError(
                "chunk_index 必须是非负整数"
            )

        if not self.text.strip():
            raise ValueError("text 不能为空")

        if self.char_count != len(self.text):
            raise ValueError(
                "char_count 与 text 长度不一致"
            )

        if self.page_start <= 0:
            raise ValueError(
                "page_start 必须是正整数"
            )

        if self.page_end < self.page_start:
            raise ValueError(
                "page_end 不能小于 page_start"
            )

        if not self.source_markdown_relative_path.strip():
            raise ValueError(
                "source_markdown_relative_path 不能为空"
            )

        hashes = {
            "chunk_id": self.chunk_id,
            "content_sha256": self.content_sha256,
            "source_markdown_sha256": (
                self.source_markdown_sha256
            ),
            "source_pdf_sha256": (
                self.source_pdf_sha256
            ),
        }

        for field_name, value in hashes.items():
            if not _SHA256_PATTERN.fullmatch(value):
                raise ValueError(
                    f"{field_name} 必须是 64 位 SHA256"
                )

        if (
            compute_text_sha256(self.text)
            != self.content_sha256
        ):
            raise ValueError(
                "content_sha256 与 text 不一致"
            )

        for field_name, value in (
            (
                "source_parser_name",
                self.source_parser_name,
            ),
            (
                "source_parser_version",
                self.source_parser_version,
            ),
            ("splitter_name", self.splitter_name),
            (
                "splitter_version",
                self.splitter_version,
            ),
        ):
            if not value.strip():
                raise ValueError(
                    f"{field_name} 不能为空"
                )

        expected_chunk_id = build_chunk_id(
            paper_id=self.paper_id,
            chunk_index=self.chunk_index,
            content_sha256=self.content_sha256,
            page_start=self.page_start,
            page_end=self.page_end,
            section_path=self.section_path,
            source_markdown_sha256=(
                self.source_markdown_sha256
            ),
            source_pdf_sha256=self.source_pdf_sha256,
            source_parser_name=self.source_parser_name,
            source_parser_version=(
                self.source_parser_version
            ),
            splitter_name=self.splitter_name,
            splitter_version=self.splitter_version,
            splitter_options=self.splitter_options,
        )

        if self.chunk_id != expected_chunk_id:
            raise ValueError(
                "chunk_id 与内容、来源或配置不一致"
            )

    @classmethod
    def create(
        cls,
        *,
        paper_id: str,
        chunk_index: int,
        text: str,
        page_start: int,
        page_end: int,
        section_path: Sequence[str],
        source_markdown_relative_path: str,
        source_markdown_sha256: str,
        source_pdf_sha256: str,
        source_parser_name: str,
        source_parser_version: str,
        splitter_name: str,
        splitter_version: str,
        splitter_options: Mapping[str, Any],
    ) -> DocumentChunk:
        """规范化输入并创建 DocumentChunk。"""

        normalized_text = text.strip()
        normalized_sections = tuple(
            section.strip()
            for section in section_path
            if section.strip()
        )
        normalized_options = _normalize_options(
            splitter_options
        )

        content_sha256 = compute_text_sha256(
            normalized_text
        )

        chunk_id = build_chunk_id(
            paper_id=paper_id.strip(),
            chunk_index=chunk_index,
            content_sha256=content_sha256,
            page_start=page_start,
            page_end=page_end,
            section_path=normalized_sections,
            source_markdown_sha256=(
                source_markdown_sha256.strip().lower()
            ),
            source_pdf_sha256=(
                source_pdf_sha256.strip().lower()
            ),
            source_parser_name=(
                source_parser_name.strip()
            ),
            source_parser_version=(
                source_parser_version.strip()
            ),
            splitter_name=splitter_name.strip(),
            splitter_version=(
                splitter_version.strip()
            ),
            splitter_options=normalized_options,
        )

        return cls(
            chunk_id=chunk_id,
            paper_id=paper_id.strip(),
            chunk_index=chunk_index,
            text=normalized_text,
            char_count=len(normalized_text),
            content_sha256=content_sha256,
            page_start=page_start,
            page_end=page_end,
            section_path=normalized_sections,
            source_markdown_relative_path=(
                source_markdown_relative_path
                .strip()
                .replace("\\", "/")
            ),
            source_markdown_sha256=(
                source_markdown_sha256.strip().lower()
            ),
            source_pdf_sha256=(
                source_pdf_sha256.strip().lower()
            ),
            source_parser_name=(
                source_parser_name.strip()
            ),
            source_parser_version=(
                source_parser_version.strip()
            ),
            splitter_name=splitter_name.strip(),
            splitter_version=(
                splitter_version.strip()
            ),
            splitter_options=normalized_options,
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为存储层可使用的普通字典。"""

        return {
            "schema_version": self.schema_version,
            "chunk_id": self.chunk_id,
            "paper_id": self.paper_id,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "char_count": self.char_count,
            "content_sha256": self.content_sha256,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "section_path": list(
                self.section_path
            ),
            "source_markdown_relative_path": (
                self.source_markdown_relative_path
            ),
            "source_markdown_sha256": (
                self.source_markdown_sha256
            ),
            "source_pdf_sha256": (
                self.source_pdf_sha256
            ),
            "source_parser_name": (
                self.source_parser_name
            ),
            "source_parser_version": (
                self.source_parser_version
            ),
            "splitter_name": self.splitter_name,
            "splitter_version": (
                self.splitter_version
            ),
            "splitter_options": _normalize_options(
                self.splitter_options
            ),
        }
