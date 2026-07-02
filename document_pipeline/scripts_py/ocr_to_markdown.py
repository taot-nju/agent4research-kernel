"""OCR 手工测试入口：PDF / 图片 -> Markdown。

这是 operator-facing CLI，用于单独测试 GLM-OCR / OpenAI-compatible OCR 能力。

支持两种输入模式：

1. PDF：
   --input-pdf xxx.pdf --output-md yyy.md

2. 单张图片：
   --input-image xxx.png --output-md yyy.md

图片支持 .png / .jpg / .jpeg / .webp。
PDF 模式复用 OCRDocumentParser；图片模式直接调用 OpenAICompatibleOCRBackend.recognize。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from ai4research.document_pipeline.config import (
    load_ocr_service_config,
)
from ai4research.document_pipeline.ocr_backends.base import (
    OCRPageRequest,
)
from ai4research.document_pipeline.ocr_backends.openai_compatible import (
    OpenAICompatibleOCRBackend,
)
from ai4research.document_pipeline.parsers.base import (
    ParseRequest,
)
from ai4research.document_pipeline.parsers.ocr_document_parser import (
    DEFAULT_MAX_PAGE_WORKERS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_RENDER_DPI,
    DEFAULT_TEMPERATURE,
    OCRDocumentParser,
)


SUPPORTED_IMAGE_SUFFIXES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用 GLM-OCR / OpenAI-compatible OCR 将 PDF 或单张图片识别为 Markdown。"
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input-pdf",
        help="输入 PDF 路径",
    )
    input_group.add_argument(
        "--input-image",
        help="输入图片路径，支持 png/jpg/jpeg/webp",
    )

    parser.add_argument(
        "--output-md",
        required=True,
        help="输出 Markdown 路径",
    )
    parser.add_argument(
        "--output-report",
        help="可选：输出 OCR report JSON 路径",
    )
    parser.add_argument(
        "--paper-id",
        default="manual-ocr",
        help="手工 OCR 的 paper_id / task id，默认 manual-ocr",
    )
    parser.add_argument(
        "--title",
        default="",
        help="可选：文档标题，仅用于 parser metadata",
    )
    parser.add_argument(
        "--prompt",
        default="",
        help="可选：自定义 OCR prompt；为空时使用默认 OCR prompt",
    )
    parser.add_argument(
        "--render-dpi",
        type=int,
        default=DEFAULT_RENDER_DPI,
        help=f"PDF 渲染 DPI，默认 {DEFAULT_RENDER_DPI}",
    )
    parser.add_argument(
        "--page-workers",
        type=int,
        default=DEFAULT_MAX_PAGE_WORKERS,
        help=f"PDF 页并发 OCR workers，默认 {DEFAULT_MAX_PAGE_WORKERS}",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"单页 OCR 最大输出 token，默认 {DEFAULT_MAX_TOKENS}",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help=f"OCR temperature，默认 {DEFAULT_TEMPERATURE}",
    )
    parser.add_argument(
        "--check-health",
        action="store_true",
        help="执行 OCR 前先检查 OCR 服务和模型是否可用",
    )
    return parser.parse_args()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _copy_report_if_requested(
    *,
    source_report_path: Path | None,
    output_report_path: Path | None,
) -> None:
    if output_report_path is None or source_report_path is None:
        return

    output_report_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_report_path, output_report_path)


def _build_backend(*, check_health: bool) -> OpenAICompatibleOCRBackend:
    config = load_ocr_service_config()
    backend = OpenAICompatibleOCRBackend(config=config)

    if check_health:
        print("Checking OCR service...")
        backend.check_health()
        print("OCR service is ready.")

    return backend


def _run_pdf_ocr(
    *,
    input_pdf: Path,
    output_md: Path,
    output_report: Path | None,
    paper_id: str,
    title: str,
    prompt: str,
    render_dpi: int,
    page_workers: int,
    max_tokens: int,
    temperature: float,
    check_health: bool,
) -> dict[str, Any]:
    backend = _build_backend(check_health=check_health)
    parser = OCRDocumentParser(backend=backend)
    pdf_sha256 = _sha256_file(input_pdf)

    with TemporaryDirectory(prefix="ai4research_manual_ocr_") as tmp:
        output_directory = Path(tmp)
        result = parser.parse(
            ParseRequest(
                paper_id=paper_id,
                pdf_path=input_pdf,
                source_pdf_sha256=pdf_sha256,
                output_directory=output_directory,
                title=title,
                parser_options={
                    "render_dpi": render_dpi,
                    "max_page_workers": page_workers,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "prompt": prompt,
                },
            )
        )

        if not result.success or result.artifacts.markdown_path is None:
            _copy_report_if_requested(
                source_report_path=result.artifacts.report_path,
                output_report_path=output_report,
            )
            raise RuntimeError(
                f"OCR PDF failed: {result.error or 'markdown_not_generated'}"
            )

        output_md.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(result.artifacts.markdown_path, output_md)

        _copy_report_if_requested(
            source_report_path=result.artifacts.report_path,
            output_report_path=output_report,
        )

        return {
            "success": True,
            "mode": "pdf",
            "input_path": str(input_pdf),
            "output_md": str(output_md),
            "output_report": str(output_report) if output_report else "",
            "paper_id": paper_id,
            "source_sha256": pdf_sha256,
            "parser_name": result.parser_name,
            "parser_version": result.parser_version,
            "backend_name": backend.name,
            "backend_version": backend.version,
            "page_count": result.page_count,
            "char_count": result.char_count,
            "duration_seconds": result.duration_seconds,
            "warnings": list(result.warnings),
        }


def _mime_type_for_image(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_IMAGE_SUFFIXES:
        return SUPPORTED_IMAGE_SUFFIXES[suffix]

    guessed, _ = mimetypes.guess_type(str(path))
    if guessed and guessed.startswith("image/"):
        return guessed

    raise ValueError(
        f"unsupported image suffix: {path.suffix}; supported={sorted(SUPPORTED_IMAGE_SUFFIXES)}"
    )


def _run_image_ocr(
    *,
    input_image: Path,
    output_md: Path,
    output_report: Path | None,
    paper_id: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    check_health: bool,
) -> dict[str, Any]:
    backend = _build_backend(check_health=check_health)
    image_sha256 = _sha256_file(input_image)
    image_bytes = input_image.read_bytes()
    mime_type = _mime_type_for_image(input_image)

    result = backend.recognize(
        OCRPageRequest(
            paper_id=paper_id,
            page_index=0,
            image_bytes=image_bytes,
            mime_type=mime_type,
            prompt=prompt,
            metadata={
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
    )

    report = {
        "paper_id": paper_id,
        "status": "success" if result.success else "failed",
        "mode": "image",
        "backend_name": backend.name,
        "backend_version": backend.version,
        "input_path": str(input_image),
        "input_sha256": image_sha256,
        "mime_type": mime_type,
        "page_count": 1,
        "char_count": len(result.text),
        "duration_seconds": result.duration_seconds,
        "error": result.error,
        "metadata": dict(result.metadata),
    }

    if output_report:
        _write_json(output_report, report)

    if not result.success:
        raise RuntimeError(f"OCR image failed: {result.error}")

    markdown = f"<!-- page: 1 -->\n\n{result.text.strip()}\n"
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(markdown, encoding="utf-8")

    return {
        "success": True,
        "mode": "image",
        "input_path": str(input_image),
        "output_md": str(output_md),
        "output_report": str(output_report) if output_report else "",
        "paper_id": paper_id,
        "source_sha256": image_sha256,
        "parser_name": "manual-image-ocr",
        "parser_version": "1",
        "backend_name": backend.name,
        "backend_version": backend.version,
        "page_count": 1,
        "char_count": len(result.text),
        "duration_seconds": result.duration_seconds,
        "warnings": [],
    }


def print_summary(summary: dict[str, Any]) -> None:
    print("=" * 100)
    print("OCR to Markdown result")
    print("=" * 100)
    print(f"success:          {summary['success']}")
    print(f"mode:             {summary['mode']}")
    print(f"paper_id:         {summary['paper_id']}")
    print(f"input_path:       {summary['input_path']}")
    print(f"output_md:        {summary['output_md']}")
    print(f"output_report:    {summary['output_report']}")
    print(f"backend:          {summary['backend_name']}:{summary['backend_version']}")
    print(f"parser:           {summary['parser_name']}:{summary['parser_version']}")
    print(f"page_count:       {summary['page_count']}")
    print(f"char_count:       {summary['char_count']}")
    print(f"duration_seconds: {summary['duration_seconds']:.3f}")
    print(f"warnings:         {summary['warnings']}")
    print("=" * 100)


def main() -> None:
    args = parse_args()

    output_md = Path(args.output_md).expanduser().resolve()
    output_report = (
        Path(args.output_report).expanduser().resolve()
        if args.output_report
        else None
    )

    if args.input_pdf:
        input_pdf = Path(args.input_pdf).expanduser().resolve()
        summary = _run_pdf_ocr(
            input_pdf=input_pdf,
            output_md=output_md,
            output_report=output_report,
            paper_id=args.paper_id,
            title=args.title,
            prompt=args.prompt,
            render_dpi=args.render_dpi,
            page_workers=args.page_workers,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            check_health=args.check_health,
        )
    else:
        input_image = Path(args.input_image).expanduser().resolve()
        summary = _run_image_ocr(
            input_image=input_image,
            output_md=output_md,
            output_report=output_report,
            paper_id=args.paper_id,
            prompt=args.prompt,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            check_health=args.check_health,
        )

    print_summary(summary)


if __name__ == "__main__":
    main()
