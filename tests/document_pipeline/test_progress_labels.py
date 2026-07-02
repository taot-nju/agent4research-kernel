from pathlib import Path


def test_document_pipeline_progress_labels_are_stage_specific() -> None:
    root = Path.home() / "ai4research"

    parse_runner = (
        root
        / "document_pipeline"
        / "pipelines"
        / "document_parse_runner.py"
    ).read_text(encoding="utf-8")

    quality_runner = (
        root
        / "document_pipeline"
        / "pipelines"
        / "document_quality_runner.py"
    ).read_text(encoding="utf-8")

    assert "[OCR {summary.claimed}/{limit} claimed_limit]" in parse_runner
    assert "[QUALITY {summary.checked}/{limit} checked_limit]" in quality_runner
    assert "[{summary.claimed}/{limit}]" not in parse_runner
    assert "[{summary.checked}/{limit}]" not in quality_runner
