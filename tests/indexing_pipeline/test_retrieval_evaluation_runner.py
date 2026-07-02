import json
import math
from pathlib import Path

import pytest

from ai4research.indexing_pipeline.evaluation.runner import (
    evaluate_saved_paper_ranking,
)
from ai4research.indexing_pipeline.evaluation.schema import (
    PaperRelevanceJudgment,
    RetrievalEvaluationCase,
    RetrievalEvaluationDataset,
)


PAPER_A = "a" * 40
PAPER_B = "b" * 40
PAPER_C = "c" * 40


def _write_dataset(path: Path) -> None:
    dataset = RetrievalEvaluationDataset(
        name="runner-test",
        version="1",
        cases=(
            RetrievalEvaluationCase(
                case_id="runner-case",
                query="agent memory trajectory",
                candidate_paper_ids=(PAPER_A, PAPER_B),
                judgments=(
                    PaperRelevanceJudgment(
                        paper_id=PAPER_A,
                        relevance=3,
                    ),
                    PaperRelevanceJudgment(
                        paper_id=PAPER_B,
                        relevance=0,
                    ),
                ),
            ),
        ),
    )
    path.write_text(
        json.dumps(dataset.to_dict(), ensure_ascii=False),
        encoding="utf-8",
    )


def _write_search_result(
    path: Path,
    *,
    query: str = "agent memory trajectory",
    paper_ids: tuple[str, ...] = (PAPER_B, PAPER_A),
) -> None:
    payload = {
        "query": query,
        "paper_search_result": {
            "hits": [
                {
                    "rank": index,
                    "paper_id": paper_id,
                    "score": float(len(paper_ids) - index + 1),
                }
                for index, paper_id in enumerate(paper_ids, start=1)
            ]
        },
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_evaluate_saved_paper_ranking(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.json"
    search_result_path = tmp_path / "search-result.json"
    _write_dataset(dataset_path)
    _write_search_result(search_result_path)

    result = evaluate_saved_paper_ranking(
        dataset_path=dataset_path,
        search_result_path=search_result_path,
        k_values=(1, 2),
    )

    assert result.ranked_paper_ids == (PAPER_B, PAPER_A)
    assert math.isclose(result.reciprocal_rank, 0.5)
    assert math.isclose(result.average_precision, 0.5)
    assert math.isclose(result.metrics_at_k[0].precision, 0.0)
    assert math.isclose(result.metrics_at_k[1].recall, 1.0)


def test_rejects_query_mismatch(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.json"
    search_result_path = tmp_path / "search-result.json"
    _write_dataset(dataset_path)
    _write_search_result(search_result_path, query="different query")

    with pytest.raises(ValueError, match="evaluation_query_mismatch"):
        evaluate_saved_paper_ranking(
            dataset_path=dataset_path,
            search_result_path=search_result_path,
        )


def test_rejects_paper_outside_candidate_set(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.json"
    search_result_path = tmp_path / "search-result.json"
    _write_dataset(dataset_path)
    _write_search_result(
        search_result_path,
        paper_ids=(PAPER_A, PAPER_C),
    )

    with pytest.raises(
        ValueError,
        match="ranked_papers_outside_candidate_set",
    ):
        evaluate_saved_paper_ranking(
            dataset_path=dataset_path,
            search_result_path=search_result_path,
        )
