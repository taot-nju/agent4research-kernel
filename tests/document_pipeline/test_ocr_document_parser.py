import json
import time

import fitz

from ai4research.document_pipeline.ocr_backends.base import (
    OCRPageRequest,
    OCRPageResult,
    PageOCRBackend,
)
from ai4research.document_pipeline.parsers.base import (
    ParseRequest,
)
from ai4research.document_pipeline.parsers.ocr_document_parser import (
    OCRDocumentParser,
)


class FakeOCRBackend(PageOCRBackend):
    @property
    def name(self) -> str:
        return "fake-ocr"

    @property
    def version(self) -> str:
        return "test-1"

    def check_health(self) -> None:
        return None

    def recognize(
        self,
        request: OCRPageRequest,
    ) -> OCRPageResult:
        # 强制第一页更晚完成，验证并发结果仍按页码排序。
        if request.page_index == 0:
            time.sleep(0.02)

        return OCRPageResult(
            success=True,
            page_index=request.page_index,
            text=(
                f"recognized page "
                f"{request.page_number}"
            ),
            duration_seconds=0.01,
            metadata={
                "backend": self.name,
            },
        )


class FailingSecondPageBackend(
    FakeOCRBackend
):
    def recognize(
        self,
        request: OCRPageRequest,
    ) -> OCRPageResult:
        if request.page_index == 1:
            return OCRPageResult(
                success=False,
                page_index=request.page_index,
                duration_seconds=0.01,
                error="simulated OCR failure",
            )

        return super().recognize(request)


def create_test_pdf(pdf_path) -> None:
    """创建一个两页测试 PDF。"""

    with fitz.open() as document:
        first_page = document.new_page()
        first_page.insert_text(
            (72, 72),
            "First test page",
        )

        second_page = document.new_page()
        second_page.insert_text(
            (72, 72),
            "Second test page",
        )

        document.save(pdf_path)


def build_request(
    *,
    pdf_path,
    output_directory,
) -> ParseRequest:
    return ParseRequest(
        paper_id="test-paper-id",
        pdf_path=pdf_path,
        source_pdf_sha256="test-sha256",
        output_directory=output_directory,
        title="Test Paper",
        parser_options={
            "render_dpi": 72,
            "max_page_workers": 2,
            "max_tokens": 256,
            "temperature": 0,
        },
    )


def test_parser_preserves_page_order(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "input.pdf"
    output_directory = tmp_path / "output"

    create_test_pdf(pdf_path)

    parser = OCRDocumentParser(
        backend=FakeOCRBackend()
    )

    result = parser.parse(
        build_request(
            pdf_path=pdf_path,
            output_directory=output_directory,
        )
    )

    assert result.success is True
    assert result.error == ""
    assert result.page_count == 2

    markdown_path = (
        result.artifacts.markdown_path
    )
    report_path = (
        result.artifacts.report_path
    )

    assert markdown_path is not None
    assert report_path is not None
    assert markdown_path.exists()
    assert report_path.exists()

    markdown = markdown_path.read_text(
        encoding="utf-8"
    )

    first_position = markdown.index(
        "recognized page 1"
    )
    second_position = markdown.index(
        "recognized page 2"
    )

    assert first_position < second_position
    assert markdown.count("<!-- page:") == 2

    report = json.loads(
        report_path.read_text(
            encoding="utf-8"
        )
    )

    assert report["status"] == "success"
    assert report["page_count"] == 2
    assert len(report["pages"]) == 2
    assert all(
        page["success"]
        for page in report["pages"]
    )


def test_parser_rejects_partial_failure(
    tmp_path,
) -> None:
    pdf_path = tmp_path / "input.pdf"
    output_directory = tmp_path / "output"

    create_test_pdf(pdf_path)

    parser = OCRDocumentParser(
        backend=FailingSecondPageBackend()
    )

    result = parser.parse(
        build_request(
            pdf_path=pdf_path,
            output_directory=output_directory,
        )
    )

    assert result.success is False
    assert "2" in result.error
    assert (
        result.artifacts.markdown_path
        is None
    )
    assert (
        result.artifacts.report_path
        is not None
    )
    assert (
        result.artifacts.report_path.exists()
    )

    report = json.loads(
        result.artifacts.report_path.read_text(
            encoding="utf-8"
        )
    )

    assert report["status"] == "failed"
    assert report["pages"][1]["success"] is False
