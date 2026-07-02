"""将 OCR Markdown 解析为带页码和章节上下文的内容块。"""

from __future__ import annotations

import re
from dataclasses import dataclass


_PAGE_MARKER_PATTERN = re.compile(
    r"^\s*<!--\s*page:\s*(\d+)\s*-->\s*$",
    re.IGNORECASE,
)

_ATX_HEADING_PATTERN = re.compile(
    r"^(#{1,6})\s+(.+?)\s*#*\s*$"
)

_NUMBERED_HEADING_PATTERN = re.compile(
    r"^(?P<label>(?:\d+|[A-Z])(?:\.\d+)*)"
    r"[.)]?\s+(?P<title>\S.*)$"
)

_FORBIDDEN_HEADING_SYMBOLS = (
    "←",
    "→",
    "∪",
    "∈",
    ":=",
    "=",
)

_SPECIAL_HEADINGS = {
    "ABSTRACT",
    "REFERENCES",
    "ACKNOWLEDGEMENTS",
    "ACKNOWLEDGMENTS",
    "ETHICS STATEMENT",
    "REPRODUCIBILITY STATEMENT",
    "CONTRIBUTIONS",
    "LIMITATIONS",
}


@dataclass(frozen=True)
class MarkdownBlock:
    """一个不可轻易从中间切断的 Markdown 内容块。"""

    text: str
    kind: str
    page_start: int
    page_end: int
    section_path: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError(
                "MarkdownBlock.text 不能为空"
            )

        if self.page_start <= 0:
            raise ValueError(
                "page_start 必须是正整数"
            )

        if self.page_end < self.page_start:
            raise ValueError(
                "page_end 不能小于 page_start"
            )


@dataclass(frozen=True)
class MarkdownBlockParseResult:
    """Markdown 块解析结果。"""

    blocks: tuple[MarkdownBlock, ...]
    page_numbers: tuple[int, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class _HeadingCandidate:
    """内部使用的标题候选。"""

    text: str
    level: int
    root: str | None


def _uppercase_ratio(text: str) -> float:
    letters = [
        character
        for character in text
        if character.isalpha()
    ]

    if not letters:
        return 0.0

    uppercase_count = sum(
        character.isupper()
        for character in letters
    )

    return uppercase_count / len(letters)


def _detect_heading(
    text: str,
) -> _HeadingCandidate | None:
    """保守识别标题，避免把表格和伪代码当作章节。"""

    stripped = text.strip()

    if not stripped or len(stripped) > 160:
        return None

    if stripped.startswith(
        ("|", "$$", "\\[", "•", "- ", "* ")
    ):
        return None

    atx_match = _ATX_HEADING_PATTERN.match(
        stripped
    )

    if atx_match:
        heading_text = (
            atx_match.group(2).strip()
        )

        numbered_atx_match = (
            _NUMBERED_HEADING_PATTERN.match(
                heading_text
            )
        )

        if numbered_atx_match:
            label = numbered_atx_match.group(
                "label"
            )
            parts = label.split(".")

            return _HeadingCandidate(
                text=heading_text,
                level=len(parts),
                root=parts[0],
            )

        return _HeadingCandidate(
            text=heading_text,
            level=len(atx_match.group(1)),
            root=None,
        )

    if any(
        symbol in stripped
        for symbol in _FORBIDDEN_HEADING_SYMBOLS
    ):
        return None

    numbered_match = (
        _NUMBERED_HEADING_PATTERN.match(
            stripped
        )
    )

    if numbered_match:
        label = numbered_match.group("label")
        title = numbered_match.group(
            "title"
        ).strip()

        if len(title) > 140:
            return None

        parts = label.split(".")

        return _HeadingCandidate(
            text=stripped,
            level=len(parts),
            root=parts[0],
        )

    normalized_upper = stripped.upper()

    if normalized_upper in _SPECIAL_HEADINGS:
        return _HeadingCandidate(
            text=stripped,
            level=1,
            root=None,
        )

    words = stripped.split()

    if (
        2 <= len(words) <= 18
        and not stripped.endswith((".", ",", ";"))
        and _uppercase_ratio(stripped) >= 0.85
    ):
        return _HeadingCandidate(
            text=stripped,
            level=1,
            root=None,
        )

    return None


def _classify_block(
    text: str,
    heading: _HeadingCandidate | None,
) -> str:
    if heading is not None:
        return "heading"

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if lines and all(
        line.startswith("|")
        for line in lines
    ):
        return "table"

    if (
        text.lstrip().startswith(("$$", "\\["))
        or "\\begin{equation" in text
        or "\\begin{align" in text
    ):
        return "formula"

    lowered = text.lstrip().lower()

    if lowered.startswith(
        ("figure ", "figure\xa0", "table ")
    ):
        return "caption"

    return "paragraph"


def _update_heading_stack(
    stack: list[_HeadingCandidate],
    heading: _HeadingCandidate,
) -> None:
    """根据标题层级维护当前章节路径。"""

    if heading.level == 1:
        stack.clear()
        stack.append(heading)
        return

    while (
        stack
        and stack[-1].level >= heading.level
    ):
        stack.pop()

    if (
        stack
        and heading.root is not None
        and stack[0].root is not None
        and stack[0].root != heading.root
    ):
        stack.clear()

    required_parent_level = heading.level - 1

    if not any(
        item.level == required_parent_level
        for item in stack
    ):
        stack.clear()

    stack.append(heading)


def parse_markdown_blocks(
    markdown_text: str,
) -> MarkdownBlockParseResult:
    """解析页标记、段落、表格、公式和弱章节结构。"""

    if not isinstance(markdown_text, str):
        raise TypeError(
            "markdown_text 必须是字符串"
        )

    if not markdown_text.strip():
        raise ValueError(
            "markdown_text 不能为空"
        )

    blocks: list[MarkdownBlock] = []
    page_numbers: list[int] = []
    warnings: list[str] = []
    heading_stack: list[
        _HeadingCandidate
    ] = []

    current_page = 1
    buffer: list[str] = []

    def flush_buffer() -> None:
        if not buffer:
            return

        block_text = "\n".join(
            buffer
        ).strip()
        buffer.clear()

        if not block_text:
            return

        heading = _detect_heading(
            block_text
        )

        if heading is not None:
            _update_heading_stack(
                heading_stack,
                heading,
            )

        block_kind = _classify_block(
            block_text,
            heading,
        )

        blocks.append(
            MarkdownBlock(
                text=block_text,
                kind=block_kind,
                page_start=current_page,
                page_end=current_page,
                section_path=tuple(
                    item.text
                    for item in heading_stack
                ),
            )
        )

    for raw_line in markdown_text.splitlines():
        page_match = _PAGE_MARKER_PATTERN.match(
            raw_line
        )

        if page_match:
            flush_buffer()

            page_number = int(
                page_match.group(1)
            )

            if (
                page_numbers
                and page_number <= page_numbers[-1]
            ):
                warnings.append(
                    "page_markers_not_strictly_increasing"
                )

            current_page = page_number
            page_numbers.append(page_number)
            continue

        if not raw_line.strip():
            flush_buffer()
            continue

        buffer.append(raw_line.rstrip())

    flush_buffer()

    if not page_numbers:
        warnings.append(
            "missing_page_markers_assumed_page_1"
        )

    if not blocks:
        raise ValueError(
            "Markdown 中没有可切分内容"
        )

    return MarkdownBlockParseResult(
        blocks=tuple(blocks),
        page_numbers=tuple(page_numbers),
        warnings=tuple(dict.fromkeys(warnings)),
    )
