from typing import Any

import pytest

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.research_pipeline.pipelines.topic_to_documents import (
    select_processable_topic_candidates,
)
from ai4research.research_pipeline.retrieval.base import (
    TopicCandidate,
    TopicRetriever,
)


class FakeRetriever(TopicRetriever):
    def __init__(
        self,
        candidates: list[TopicCandidate],
    ) -> None:
        self._candidates = candidates
        self.requested_limit = 0

    @property
    def name(self) -> str:
        return "fake-retriever"

    @property
    def version(self) -> str:
        return "1"

    def search(
        self,
        *,
        topic: str,
        limit: int,
    ) -> list[TopicCandidate]:
        self.requested_limit = limit
        return self._candidates[:limit]


class FakeCollection:
    def __init__(
        self,
        documents: list[dict[str, Any]],
    ) -> None:
        self._documents = documents

    def find(
        self,
        query: dict[str, Any],
    ) -> list[dict[str, Any]]:
        requested_ids = set(
            query["_id"]["$in"]
        )
        return [
            document
            for document in self._documents
            if document["_id"] in requested_ids
        ]


def make_candidate(
    paper_id: str,
    score: float,
) -> TopicCandidate:
    return TopicCandidate(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        accepted_by="Test Venue",
        score=score,
        matched_fields=("title",),
    )


def test_skips_unavailable_and_backfills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = [
        make_candidate("no-pdf-1", 50.0),
        make_candidate("downloaded", 40.0),
        make_candidate("arxiv-url", 30.0),
        make_candidate("no-pdf-2", 20.0),
        make_candidate("openreview-url", 10.0),
    ]
    retriever = FakeRetriever(candidates)

    collection = FakeCollection(
        [
            {
                "_id": "no-pdf-1",
                "pdf_asset": {
                    "status": "unavailable",
                },
            },
            {
                "_id": "downloaded",
                "pdf_asset": {
                    "status": "success",
                },
            },
            {
                "_id": "arxiv-url",
                "pdf_asset": {
                    "status": "pending",
                },
                "arxiv_obj": {
                    "arxiv_pdf_url": (
                        "https://arxiv.org/pdf/test"
                    ),
                },
            },
            {
                "_id": "no-pdf-2",
                "pdf_asset": {
                    "status": "unavailable",
                },
            },
            {
                "_id": "openreview-url",
                "pdf_asset": {
                    "status": "failed",
                },
                "openreview_obj": {
                    "pdf_url": (
                        "https://openreview.net/pdf/test"
                    ),
                },
            },
        ]
    )

    monkeypatch.setattr(
        MongoDBClient,
        "get_collection",
        staticmethod(lambda: collection),
    )

    selected = select_processable_topic_candidates(
        topic="agent memory",
        top_k=3,
        candidate_scan_limit=5,
        retriever=retriever,
    )

    assert retriever.requested_limit == 5
    assert [
        candidate.paper_id
        for candidate in selected
    ] == [
        "downloaded",
        "arxiv-url",
        "openreview-url",
    ]


def test_scan_limit_is_never_below_top_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = [
        make_candidate("paper-1", 30.0),
        make_candidate("paper-2", 20.0),
        make_candidate("paper-3", 10.0),
    ]
    retriever = FakeRetriever(candidates)
    collection = FakeCollection(
        [
            {
                "_id": candidate.paper_id,
                "pdf_asset": {
                    "status": "success",
                },
            }
            for candidate in candidates
        ]
    )

    monkeypatch.setattr(
        MongoDBClient,
        "get_collection",
        staticmethod(lambda: collection),
    )

    selected = select_processable_topic_candidates(
        topic="agent memory",
        top_k=3,
        candidate_scan_limit=1,
        retriever=retriever,
    )

    assert retriever.requested_limit == 3
    assert len(selected) == 3
