import subprocess
import sys


def test_ocr_to_markdown_cli_help() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai4research.document_pipeline.scripts_py.ocr_to_markdown",
            "--help",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "ocr_to_markdown.py" in completed.stdout
    assert "--input-pdf" in completed.stdout
    assert "--input-image" in completed.stdout
    assert "--output-md" in completed.stdout
    assert "--output-report" in completed.stdout
    assert "--check-health" in completed.stdout


def test_ocr_to_markdown_image_mode_writes_markdown_and_report(
    tmp_path,
    monkeypatch,
) -> None:
    from ai4research.document_pipeline.ocr_backends.base import OCRPageResult
    from ai4research.document_pipeline.scripts_py import ocr_to_markdown

    class FakeBackend:
        name = "fake-ocr"
        version = "test"

        def check_health(self) -> None:
            return None

        def recognize(self, request):
            return OCRPageResult(
                success=True,
                page_index=request.page_index,
                text="Hello OCR",
                duration_seconds=0.123,
                metadata={"model": "fake-model"},
            )

    monkeypatch.setattr(
        ocr_to_markdown,
        "_build_backend",
        lambda *, check_health: FakeBackend(),
    )

    image_path = tmp_path / "page.png"
    output_md = tmp_path / "output.md"
    output_report = tmp_path / "report.json"
    image_path.write_bytes(b"fake-image-bytes")

    summary = ocr_to_markdown._run_image_ocr(
        input_image=image_path,
        output_md=output_md,
        output_report=output_report,
        paper_id="manual-test",
        prompt="",
        max_tokens=128,
        temperature=0.0,
        check_health=False,
    )

    assert summary["success"] is True
    assert summary["mode"] == "image"
    assert output_md.read_text(encoding="utf-8") == "<!-- page: 1 -->\n\nHello OCR\n"
    report_text = output_report.read_text(encoding="utf-8")
    assert '"status": "success"' in report_text
    assert '"backend_name": "fake-ocr"' in report_text


def test_ocr_to_markdown_pdf_mode_copies_markdown_and_report(
    tmp_path,
    monkeypatch,
) -> None:
    from ai4research.document_pipeline.parsers.base import (
        ParseArtifacts,
        ParseResult,
        ParserCapabilities,
    )
    from ai4research.document_pipeline.scripts_py import ocr_to_markdown

    class FakeParser:
        def __init__(self, *, backend):
            self.backend = backend

        def parse(self, request):
            generated_md = request.output_directory / "document.md"
            generated_report = request.output_directory / "parse_report.json"
            generated_md.write_text("PDF OCR markdown\n", encoding="utf-8")
            generated_report.write_text('{"status": "success"}\n', encoding="utf-8")

            return ParseResult(
                success=True,
                parser_name="fake-parser",
                parser_version="test",
                capabilities=ParserCapabilities(markdown=True),
                source_pdf_sha256=request.source_pdf_sha256,
                artifacts=ParseArtifacts(
                    markdown_path=generated_md,
                    report_path=generated_report,
                ),
                page_count=2,
                char_count=17,
                duration_seconds=0.456,
            )

    class FakeBackend:
        name = "fake-ocr"
        version = "test"

    monkeypatch.setattr(
        ocr_to_markdown,
        "_build_backend",
        lambda *, check_health: FakeBackend(),
    )
    monkeypatch.setattr(
        ocr_to_markdown,
        "OCRDocumentParser",
        FakeParser,
    )

    input_pdf = tmp_path / "input.pdf"
    output_md = tmp_path / "output.md"
    output_report = tmp_path / "report.json"
    input_pdf.write_bytes(b"%PDF fake")

    summary = ocr_to_markdown._run_pdf_ocr(
        input_pdf=input_pdf,
        output_md=output_md,
        output_report=output_report,
        paper_id="manual-test",
        title="",
        prompt="",
        render_dpi=200,
        page_workers=1,
        max_tokens=128,
        temperature=0.0,
        check_health=False,
    )

    assert summary["success"] is True
    assert summary["mode"] == "pdf"
    assert summary["page_count"] == 2
    assert output_md.read_text(encoding="utf-8") == "PDF OCR markdown\n"
    assert output_report.read_text(encoding="utf-8") == '{"status": "success"}\n'
