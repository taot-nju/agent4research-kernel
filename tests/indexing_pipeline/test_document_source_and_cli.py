"""文档来源适配器与 chunk CLI 测试。"""

from pathlib import Path

import pytest

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.indexing_pipeline.repositories.document_source import (
    load_indexable_document_source,
)
from ai4research.indexing_pipeline.scripts_py.chunk_documents import (
    build_argument_parser,
)


class _FakeCollection:
    def __init__(self, paper):
        self._paper = paper

    def find_one(self, query, projection):
        if (
            self._paper is not None
            and self._paper["_id"]
            == query["_id"]
        ):
            return self._paper

        return None


def _build_paper(
    *,
    paper_id: str,
    quality_status: str = "passed",
    pdf_sha256: str = "b" * 64,
    source_pdf_sha256: str = "b" * 64,
) -> dict:
    return {
        "_id": paper_id,
        "title": "Example Paper",
        "pdf_asset": {
            "status": "success",
            "sha256": pdf_sha256,
        },
        "document_asset": {
            "status": "success",
            "quality_status": quality_status,
            "markdown_relative_path": (
                f"documents/{paper_id[:2]}/"
                f"{paper_id[2:4]}/{paper_id}/"
                "document.md"
            ),
            "source_pdf_sha256": (
                source_pdf_sha256
            ),
            "parser_name": (
                "ocr-document-parser"
            ),
            "parser_version": "1:glm-ocr",
        },
    }


def _install_fake_collection(
    monkeypatch,
    paper,
):
    fake_collection = _FakeCollection(paper)

    monkeypatch.setattr(
        MongoDBClient,
        "get_collection",
        classmethod(
            lambda cls: fake_collection
        ),
    )


def test_load_indexable_document_source(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AI4RESEARCH_DATA_ROOT",
        str(tmp_path),
    )

    paper_id = "a" * 40
    paper = _build_paper(
        paper_id=paper_id
    )

    relative_path = Path(
        paper["document_asset"][
            "markdown_relative_path"
        ]
    )
    markdown_path = tmp_path / relative_path
    markdown_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    markdown_path.write_text(
        "<!-- page: 1 -->\n\nText.\n",
        encoding="utf-8",
    )

    _install_fake_collection(
        monkeypatch,
        paper,
    )

    source = (
        load_indexable_document_source(
            paper_id=paper_id
        )
    )

    assert source.paper_id == paper_id
    assert source.title == "Example Paper"
    assert source.markdown_path == (
        markdown_path
    )
    assert source.quality_status == "passed"


def test_rejected_document_is_not_indexable(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AI4RESEARCH_DATA_ROOT",
        str(tmp_path),
    )

    paper_id = "a" * 40

    _install_fake_collection(
        monkeypatch,
        _build_paper(
            paper_id=paper_id,
            quality_status="rejected",
        ),
    )

    with pytest.raises(
        ValueError,
        match="质量状态不允许索引",
    ):
        load_indexable_document_source(
            paper_id=paper_id
        )


def test_changed_pdf_marks_document_unusable(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "AI4RESEARCH_DATA_ROOT",
        str(tmp_path),
    )

    paper_id = "a" * 40

    _install_fake_collection(
        monkeypatch,
        _build_paper(
            paper_id=paper_id,
            pdf_sha256="c" * 64,
            source_pdf_sha256="b" * 64,
        ),
    )

    with pytest.raises(
        ValueError,
        match="来源 PDF 已变化",
    ):
        load_indexable_document_source(
            paper_id=paper_id
        )


def test_chunk_cli_defaults():
    parser = build_argument_parser()

    args = parser.parse_args(
        [
            "--paper-id",
            "a" * 40,
        ]
    )

    assert args.target_chars == 2400
    assert args.max_chars == 3200
    assert args.overlap_chars == 300
    assert (
        args.min_chars_before_heading_break
        == 800
    )
    assert not args.passed_only
