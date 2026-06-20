import json

from ai4research.document_pipeline.quality_checks.base import (
    DocumentQualityRequest,
)
from ai4research.document_pipeline.quality_checks.basic import (
    BasicDocumentQualityChecker,
)


def write_valid_assets(tmp_path):
    markdown_path = tmp_path / "document.md"
    report_path = tmp_path / "parse_report.json"

    first_text = (
        "Test Paper\n\n"
        + "This is valid document content. " * 20
    )
    second_text = (
        "This is the second page content. " * 20
    )

    markdown = (
        "<!-- page: 1 -->\n\n"
        f"{first_text}\n\n"
        "<!-- page: 2 -->\n\n"
        f"{second_text}\n"
    )

    markdown_path.write_text(
        markdown,
        encoding="utf-8",
    )

    report_path.write_text(
        json.dumps(
            {
                "status": "success",
                "page_count": 2,
                "pages": [
                    {
                        "page_index": 0,
                        "success": True,
                    },
                    {
                        "page_index": 1,
                        "success": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    reported_char_count = (
        len(first_text)
        + len(second_text)
    )

    return (
        markdown_path,
        report_path,
        reported_char_count,
    )


def test_valid_document_passes(
    tmp_path,
) -> None:
    (
        markdown_path,
        report_path,
        reported_char_count,
    ) = write_valid_assets(tmp_path)

    checker = BasicDocumentQualityChecker()

    result = checker.check(
        DocumentQualityRequest(
            paper_id="test-paper",
            title="Test Paper",
            markdown_path=markdown_path,
            report_path=report_path,
            page_count=2,
            char_count=reported_char_count,
        )
    )

    assert result.status == "passed"
    assert result.score >= 0.80
    assert result.warnings == ()
    assert all(
        check.passed
        for check in result.checks
    )


def test_missing_markdown_is_rejected(
    tmp_path,
) -> None:
    checker = BasicDocumentQualityChecker()

    result = checker.check(
        DocumentQualityRequest(
            paper_id="test-paper",
            title="Test Paper",
            markdown_path=(
                tmp_path / "missing.md"
            ),
            report_path=None,
            page_count=2,
            char_count=1000,
        )
    )

    assert result.status == "rejected"
    assert result.score == 0.0
    assert result.warnings
    assert (
        result.checks[0].name
        == "markdown_exists"
    )
    assert result.checks[0].passed is False


def test_page_marker_mismatch_is_rejected(
    tmp_path,
) -> None:
    (
        markdown_path,
        report_path,
        reported_char_count,
    ) = write_valid_assets(tmp_path)

    markdown = markdown_path.read_text(
        encoding="utf-8"
    )
    markdown = markdown.replace(
        "<!-- page: 2 -->",
        "",
    )
    markdown_path.write_text(
        markdown,
        encoding="utf-8",
    )

    checker = BasicDocumentQualityChecker()

    result = checker.check(
        DocumentQualityRequest(
            paper_id="test-paper",
            title="Test Paper",
            markdown_path=markdown_path,
            report_path=report_path,
            page_count=2,
            char_count=reported_char_count,
        )
    )

    assert result.status == "rejected"

    marker_check = next(
        check
        for check in result.checks
        if check.name
        == "page_markers_match"
    )

    assert marker_check.passed is False
    assert marker_check.critical is True
