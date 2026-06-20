"""
通用 OCR 文档解析器。

职责：
1. 读取 PDF 页数；
2. 按页渲染为 PNG；
3. 通过 PageOCRBackend 并发识别；
4. 按原始页序组合 Markdown；
5. 生成标准解析报告。

本模块不连接 MongoDB，也不负责领取任务。
"""

import json
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

import fitz

from ai4research.document_pipeline.ocr_backends.base import (
    OCRPageRequest,
    OCRPageResult,
    PageOCRBackend,
)
from ai4research.document_pipeline.parsers.base import (
    DocumentParser,
    ParseArtifacts,
    ParseRequest,
    ParseResult,
    ParserCapabilities,
)
from ai4research.document_pipeline.utils.storage_paths import (
    MARKDOWN_FILENAME,
    PARSE_REPORT_FILENAME,
)


PARSER_VERSION = "1"

DEFAULT_RENDER_DPI = 200
DEFAULT_MAX_PAGE_WORKERS = 4
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 0.0


def _read_positive_int(
    options: Mapping[str, Any],
    key: str,
    default: int,
) -> int:
    """读取正整数解析选项。"""

    raw_value = options.get(key, default)

    try:
        value = int(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{key} 必须是整数"
        ) from error

    if value <= 0:
        raise ValueError(
            f"{key} 必须大于 0"
        )

    return value


def _read_non_negative_float(
    options: Mapping[str, Any],
    key: str,
    default: float,
) -> float:
    """读取非负浮点数解析选项。"""

    raw_value = options.get(key, default)

    try:
        value = float(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{key} 必须是数字"
        ) from error

    if value < 0:
        raise ValueError(
            f"{key} 不能小于 0"
        )

    return value


def _write_text_atomic(
    path: Path,
    content: str,
) -> None:
    """通过临时文件原子写入文本。"""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    temp_path.write_text(
        content,
        encoding="utf-8",
    )

    temp_path.replace(path)


def _write_json_atomic(
    path: Path,
    data: Mapping[str, Any],
) -> None:
    """通过临时文件原子写入 JSON。"""

    content = (
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )

    _write_text_atomic(path, content)


class OCRDocumentParser(DocumentParser):
    """使用可替换单页 OCR 后端解析完整 PDF。"""

    def __init__(
        self,
        backend: PageOCRBackend,
    ) -> None:
        self._backend = backend

    @property
    def name(self) -> str:
        return "ocr-document-parser"

    @property
    def version(self) -> str:
        return (
            f"{PARSER_VERSION}:"
            f"{self._backend.name}:"
            f"{self._backend.version}"
        )

    @property
    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            markdown=True,
            plain_text=False,
            layout=False,
            formulas=True,
            tables=True,
            page_coordinates=False,
        )

    def _process_page(
        self,
        *,
        request: ParseRequest,
        page_index: int,
        render_dpi: int,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> OCRPageResult:
        """
        渲染并识别一页 PDF。

        每个线程独立打开 PDF，避免多个线程共享同一个
        PyMuPDF Document 或 Page 对象。
        """

        started_at = perf_counter()

        try:
            with fitz.open(request.pdf_path) as document:
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(
                    dpi=render_dpi
                )
                image_bytes = pixmap.tobytes("png")

            backend_result = self._backend.recognize(
                OCRPageRequest(
                    paper_id=request.paper_id,
                    page_index=page_index,
                    image_bytes=image_bytes,
                    mime_type="image/png",
                    prompt=prompt,
                    metadata={
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                )
            )

            metadata = dict(
                backend_result.metadata
            )
            metadata["backend_duration_seconds"] = (
                backend_result.duration_seconds
            )
            metadata["render_dpi"] = render_dpi

            return OCRPageResult(
                success=backend_result.success,
                page_index=page_index,
                text=backend_result.text,
                duration_seconds=(
                    perf_counter() - started_at
                ),
                error=backend_result.error,
                metadata=metadata,
            )

        except Exception as error:
            return OCRPageResult(
                success=False,
                page_index=page_index,
                duration_seconds=(
                    perf_counter() - started_at
                ),
                error=(
                    f"{type(error).__name__}: {error}"
                )[:4000],
                metadata={
                    "backend": self._backend.name,
                    "model": self._backend.version,
                    "render_dpi": render_dpi,
                },
            )

    @staticmethod
    def _build_markdown(
        page_results: list[OCRPageResult],
    ) -> str:
        """按页码顺序组合 Markdown。"""

        sections = []

        for result in page_results:
            page_marker = (
                f"<!-- page: {result.page_number} -->"
            )
            page_text = result.text.strip()

            sections.append(
                f"{page_marker}\n\n{page_text}"
            )

        return "\n\n".join(sections) + "\n"

    def parse(
        self,
        request: ParseRequest,
    ) -> ParseResult:
        """解析完整 PDF 并生成标准文档资产。"""

        started_at = perf_counter()

        empty_artifacts = ParseArtifacts()

        try:
            pdf_path = request.pdf_path

            if not pdf_path.exists():
                raise FileNotFoundError(
                    f"PDF 不存在：{pdf_path}"
                )

            if not pdf_path.is_file():
                raise ValueError(
                    f"PDF 路径不是普通文件：{pdf_path}"
                )

            options = dict(
                request.parser_options
            )

            render_dpi = _read_positive_int(
                options,
                "render_dpi",
                DEFAULT_RENDER_DPI,
            )
            max_page_workers = _read_positive_int(
                options,
                "max_page_workers",
                DEFAULT_MAX_PAGE_WORKERS,
            )
            max_tokens = _read_positive_int(
                options,
                "max_tokens",
                DEFAULT_MAX_TOKENS,
            )
            temperature = _read_non_negative_float(
                options,
                "temperature",
                DEFAULT_TEMPERATURE,
            )
            prompt = str(
                options.get("prompt", "")
            ).strip()

            with fitz.open(pdf_path) as document:
                page_count = document.page_count

            if page_count <= 0:
                raise ValueError(
                    "PDF 不包含可解析页面"
                )

            request.output_directory.mkdir(
                parents=True,
                exist_ok=True,
            )

            worker_count = min(
                max_page_workers,
                page_count,
            )

            ordered_results: list[
                OCRPageResult | None
            ] = [None] * page_count

            with ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix="document-ocr",
            ) as executor:
                future_to_page = {
                    executor.submit(
                        self._process_page,
                        request=request,
                        page_index=page_index,
                        render_dpi=render_dpi,
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    ): page_index
                    for page_index in range(page_count)
                }

                for future in as_completed(
                    future_to_page
                ):
                    page_index = future_to_page[
                        future
                    ]
                    ordered_results[
                        page_index
                    ] = future.result()

            page_results = [
                result
                for result in ordered_results
                if result is not None
            ]

            if len(page_results) != page_count:
                raise RuntimeError(
                    "部分页面没有返回 OCR 结果"
                )

            failed_results = [
                result
                for result in page_results
                if not result.success
            ]

            duration_seconds = (
                perf_counter() - started_at
            )
            char_count = sum(
                len(result.text)
                for result in page_results
            )

            report_path = (
                request.output_directory
                / PARSE_REPORT_FILENAME
            )

            report = {
                "paper_id": request.paper_id,
                "status": (
                    "failed"
                    if failed_results
                    else "success"
                ),
                "parser_name": self.name,
                "parser_version": self.version,
                "backend_name": self._backend.name,
                "backend_version": (
                    self._backend.version
                ),
                "source_pdf_sha256": (
                    request.source_pdf_sha256
                ),
                "page_count": page_count,
                "char_count": char_count,
                "duration_seconds": duration_seconds,
                "parser_options": {
                    "render_dpi": render_dpi,
                    "max_page_workers": (
                        max_page_workers
                    ),
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                "pages": [
                    {
                        "page_index": result.page_index,
                        "page_number": (
                            result.page_number
                        ),
                        "success": result.success,
                        "char_count": len(
                            result.text
                        ),
                        "duration_seconds": (
                            result.duration_seconds
                        ),
                        "error": result.error,
                        "metadata": dict(
                            result.metadata
                        ),
                    }
                    for result in page_results
                ],
            }

            _write_json_atomic(
                report_path,
                report,
            )

            if failed_results:
                failed_pages = [
                    str(result.page_number)
                    for result in failed_results
                ]

                error_message = (
                    "OCR 页面解析失败："
                    + ", ".join(failed_pages)
                )

                return ParseResult(
                    success=False,
                    parser_name=self.name,
                    parser_version=self.version,
                    capabilities=self.capabilities,
                    source_pdf_sha256=(
                        request.source_pdf_sha256
                    ),
                    artifacts=ParseArtifacts(
                        report_path=report_path,
                    ),
                    page_count=page_count,
                    char_count=char_count,
                    duration_seconds=(
                        duration_seconds
                    ),
                    warnings=(
                        f"failed_pages="
                        f"{','.join(failed_pages)}",
                    ),
                    error=error_message,
                    metadata={
                        "failed_page_count": len(
                            failed_results
                        ),
                    },
                )

            markdown_content = (
                self._build_markdown(
                    page_results
                )
            )

            markdown_path = (
                request.output_directory
                / MARKDOWN_FILENAME
            )

            _write_text_atomic(
                markdown_path,
                markdown_content,
            )

            return ParseResult(
                success=True,
                parser_name=self.name,
                parser_version=self.version,
                capabilities=self.capabilities,
                source_pdf_sha256=(
                    request.source_pdf_sha256
                ),
                artifacts=ParseArtifacts(
                    markdown_path=markdown_path,
                    report_path=report_path,
                ),
                page_count=page_count,
                char_count=char_count,
                duration_seconds=duration_seconds,
                metadata={
                    "backend_name": (
                        self._backend.name
                    ),
                    "backend_version": (
                        self._backend.version
                    ),
                },
            )

        except Exception as error:
            return ParseResult(
                success=False,
                parser_name=self.name,
                parser_version=self.version,
                capabilities=self.capabilities,
                source_pdf_sha256=(
                    request.source_pdf_sha256
                ),
                artifacts=empty_artifacts,
                duration_seconds=(
                    perf_counter() - started_at
                ),
                error=(
                    f"{type(error).__name__}: {error}"
                )[:4000],
                metadata={
                    "backend_name": (
                        self._backend.name
                    ),
                    "backend_version": (
                        self._backend.version
                    ),
                },
            )