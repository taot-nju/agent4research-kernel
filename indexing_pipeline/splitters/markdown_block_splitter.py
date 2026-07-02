"""页码感知、块感知的 Markdown 切分器。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ai4research.indexing_pipeline.schemas.document_chunk import (
    DocumentChunk,
)
from ai4research.indexing_pipeline.splitters.base import (
    DocumentSplitter,
    SplitRequest,
    SplitResult,
)
from ai4research.indexing_pipeline.splitters.markdown_blocks import (
    MarkdownBlock,
    parse_markdown_blocks,
)


SPLITTER_NAME = "markdown-block-splitter"
SPLITTER_VERSION = "1"


@dataclass(frozen=True)
class MarkdownBlockSplitterConfig:
    """字符级 MVP 切分配置。"""

    target_chars: int = 2400
    max_chars: int = 3200
    overlap_chars: int = 300
    min_chars_before_heading_break: int = 800

    def __post_init__(self) -> None:
        if self.target_chars <= 0:
            raise ValueError(
                "target_chars 必须大于 0"
            )

        if self.max_chars < self.target_chars:
            raise ValueError(
                "max_chars 不能小于 target_chars"
            )

        if (
            self.overlap_chars < 0
            or self.overlap_chars
            >= self.target_chars
        ):
            raise ValueError(
                "overlap_chars 必须大于等于 0"
                "且小于 target_chars"
            )

        if (
            self.min_chars_before_heading_break
            < 0
        ):
            raise ValueError(
                "min_chars_before_heading_break "
                "不能小于 0"
            )

    def to_options(self) -> dict[str, int]:
        return {
            "target_chars": self.target_chars,
            "max_chars": self.max_chars,
            "overlap_chars": self.overlap_chars,
            "min_chars_before_heading_break": (
                self.min_chars_before_heading_break
            ),
        }


def _blocks_char_count(
    blocks: list[MarkdownBlock],
) -> int:
    if not blocks:
        return 0

    return sum(
        len(block.text)
        for block in blocks
    ) + 2 * (len(blocks) - 1)


def _find_split_position(
    text: str,
    max_chars: int,
) -> int:
    """在最大长度以内寻找较自然的文本边界。"""

    minimum_position = max(
        1,
        max_chars // 2,
    )
    window = text[: max_chars + 1]
    candidates: list[int] = []

    newline_position = window.rfind(
        "\n",
        minimum_position,
    )

    if newline_position >= minimum_position:
        candidates.append(newline_position)

    for delimiter in (". ", "? ", "! ", "; "):
        position = window.rfind(
            delimiter,
            minimum_position,
        )

        if position >= minimum_position:
            candidates.append(position + 1)

    space_position = window.rfind(
        " ",
        minimum_position,
    )

    if space_position >= minimum_position:
        candidates.append(space_position)

    if candidates:
        return max(candidates)

    return max_chars


def _split_oversized_block(
    block: MarkdownBlock,
    max_chars: int,
) -> list[MarkdownBlock]:
    """切分超长普通文本，但保持表格、公式和标题完整。"""

    if len(block.text) <= max_chars:
        return [block]

    if block.kind in {
        "heading",
        "table",
        "formula",
    }:
        return [block]

    remaining = block.text.strip()
    segments: list[MarkdownBlock] = []

    while len(remaining) > max_chars:
        split_position = _find_split_position(
            remaining,
            max_chars,
        )

        segment_text = remaining[
            :split_position
        ].strip()
        remaining = remaining[
            split_position:
        ].strip()

        if not segment_text:
            segment_text = remaining[
                :max_chars
            ]
            remaining = remaining[
                max_chars:
            ].strip()

        segments.append(
            MarkdownBlock(
                text=segment_text,
                kind=block.kind,
                page_start=block.page_start,
                page_end=block.page_end,
                section_path=block.section_path,
            )
        )

    if remaining:
        segments.append(
            MarkdownBlock(
                text=remaining,
                kind=block.kind,
                page_start=block.page_start,
                page_end=block.page_end,
                section_path=block.section_path,
            )
        )

    return segments


def _prepare_blocks(
    blocks: tuple[MarkdownBlock, ...],
    max_chars: int,
) -> list[MarkdownBlock]:
    prepared: list[MarkdownBlock] = []

    for block in blocks:
        prepared.extend(
            _split_oversized_block(
                block,
                max_chars,
            )
        )

    return prepared


def _build_primary_groups(
    blocks: list[MarkdownBlock],
    config: MarkdownBlockSplitterConfig,
) -> list[list[MarkdownBlock]]:
    """构建不含 overlap 的主 chunk 分组。"""

    groups: list[list[MarkdownBlock]] = []
    current: list[MarkdownBlock] = []

    for block in blocks:
        current_size = _blocks_char_count(
            current
        )

        if (
            block.kind == "heading"
            and current
            and current_size
            >= config.min_chars_before_heading_break
        ):
            groups.append(current)
            current = []
            current_size = 0

        separator_size = 2 if current else 0
        projected_size = (
            current_size
            + separator_size
            + len(block.text)
        )

        if (
            current
            and projected_size > config.max_chars
        ):
            groups.append(current)
            current = []

        current.append(block)

        if (
            _blocks_char_count(current)
            >= config.target_chars
            and block.kind != "heading"
        ):
            groups.append(current)
            current = []

    if current:
        groups.append(current)

    return groups


def _build_overlap_blocks(
    previous_group: list[MarkdownBlock],
    overlap_chars: int,
) -> list[MarkdownBlock]:
    """从上一主分组尾部构建近似字符 overlap。"""

    if overlap_chars <= 0:
        return []

    selected_reversed: list[
        MarkdownBlock
    ] = []
    remaining_chars = overlap_chars

    for block in reversed(previous_group):
        separator_size = (
            2 if selected_reversed else 0
        )
        available_chars = (
            remaining_chars - separator_size
        )

        if available_chars <= 0:
            break

        if len(block.text) <= available_chars:
            selected_reversed.append(block)
            remaining_chars -= (
                len(block.text) + separator_size
            )
            continue

        if block.kind in {
            "heading",
            "table",
            "formula",
        }:
            break

        suffix = block.text[
            -available_chars:
        ].strip()

        first_space = suffix.find(" ")

        if 0 < first_space < 80:
            suffix = suffix[
                first_space + 1:
            ].lstrip()

        if suffix:
            selected_reversed.append(
                MarkdownBlock(
                    text=suffix,
                    kind="overlap",
                    page_start=block.page_start,
                    page_end=block.page_end,
                    section_path=(
                        block.section_path
                    ),
                )
            )

        break

    return list(reversed(selected_reversed))


class MarkdownBlockSplitter(DocumentSplitter):
    """基于 OCR 页标记和 Markdown 块的字符级切分器。"""

    def __init__(
        self,
        config: (
            MarkdownBlockSplitterConfig | None
        ) = None,
    ) -> None:
        self._config = (
            config
            or MarkdownBlockSplitterConfig()
        )

    @property
    def name(self) -> str:
        return SPLITTER_NAME

    @property
    def version(self) -> str:
        return SPLITTER_VERSION

    @property
    def options(self) -> Mapping[str, Any]:
        return self._config.to_options()

    def split(
        self,
        request: SplitRequest,
    ) -> SplitResult:
        warnings: list[str] = []

        try:
            parsed = parse_markdown_blocks(
                request.markdown_text
            )
            warnings.extend(parsed.warnings)

            prepared_blocks = _prepare_blocks(
                parsed.blocks,
                self._config.target_chars,
            )

            primary_groups = (
                _build_primary_groups(
                    prepared_blocks,
                    self._config,
                )
            )

            chunks: list[DocumentChunk] = []

            for chunk_index, group in enumerate(
                primary_groups
            ):
                effective_blocks = list(group)

                if chunk_index > 0:
                    group_size = (
                        _blocks_char_count(group)
                    )
                    available_overlap = max(
                        0,
                        self._config.max_chars
                        - group_size
                        - 2,
                    )
                    requested_overlap = min(
                        self._config.overlap_chars,
                        available_overlap,
                    )

                    overlap_blocks = (
                        _build_overlap_blocks(
                            primary_groups[
                                chunk_index - 1
                            ],
                            requested_overlap,
                        )
                    )

                    effective_blocks = (
                        overlap_blocks
                        + effective_blocks
                    )

                chunk_text = "\n\n".join(
                    block.text
                    for block in effective_blocks
                ).strip()

                page_start = min(
                    block.page_start
                    for block in effective_blocks
                )
                page_end = max(
                    block.page_end
                    for block in effective_blocks
                )

                section_path = (
                    group[-1].section_path
                )

                chunks.append(
                    DocumentChunk.create(
                        paper_id=request.paper_id,
                        chunk_index=chunk_index,
                        text=chunk_text,
                        page_start=page_start,
                        page_end=page_end,
                        section_path=section_path,
                        source_markdown_relative_path=(
                            request
                            .source_markdown_relative_path
                        ),
                        source_markdown_sha256=(
                            request
                            .source_markdown_sha256
                        ),
                        source_pdf_sha256=(
                            request.source_pdf_sha256
                        ),
                        source_parser_name=(
                            request.source_parser_name
                        ),
                        source_parser_version=(
                            request
                            .source_parser_version
                        ),
                        splitter_name=self.name,
                        splitter_version=self.version,
                        splitter_options=(
                            self.options
                        ),
                    )
                )

            oversized_atomic_count = sum(
                1
                for block in prepared_blocks
                if (
                    block.kind
                    in {"table", "formula"}
                    and len(block.text)
                    > self._config.max_chars
                )
            )

            if oversized_atomic_count:
                warnings.append(
                    "oversized_atomic_blocks_preserved="
                    f"{oversized_atomic_count}"
                )

            return SplitResult(
                success=True,
                paper_id=request.paper_id,
                splitter_name=self.name,
                splitter_version=self.version,
                splitter_options=self.options,
                chunks=tuple(chunks),
                warnings=tuple(
                    dict.fromkeys(warnings)
                ),
                metadata={
                    "page_marker_count": len(
                        parsed.page_numbers
                    ),
                    "block_count": len(
                        prepared_blocks
                    ),
                    "chunk_count": len(chunks),
                    "oversized_atomic_count": (
                        oversized_atomic_count
                    ),
                },
            )

        except Exception as error:
            return SplitResult(
                success=False,
                paper_id=request.paper_id,
                splitter_name=self.name,
                splitter_version=self.version,
                splitter_options=self.options,
                error=(
                    f"{type(error).__name__}: "
                    f"{error}"
                )[:4000],
            )
