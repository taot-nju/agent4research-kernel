import math

from ai4research.indexing_pipeline.evaluation.metrics import evaluate_paper_ranking
from ai4research.indexing_pipeline.evaluation.schema import (
    PaperRelevanceJudgment,
    RetrievalEvaluationCase,
    RetrievalEvaluationDataset,
)


PAPER_A = "a" * 40
PAPER_B = "b" * 40
PAPER_C = "c" * 40
PAPER_D = "d" * 40


def _build_case() -> RetrievalEvaluationCase:
    return RetrievalEvaluationCase(
        case_id="known-ranking-test",
        query="agent memory trajectory",
        description="A deterministic paper-ranking evaluation case.",
        tags=("agent", "memory", "trajectory"),
        candidate_paper_ids=(PAPER_A, PAPER_B, PAPER_C, PAPER_D),
        judgments=(
            PaperRelevanceJudgment(
                paper_id=PAPER_A,
                relevance=3,
                rationale="Highly relevant.",
                evidence_page_ranges=((2, 3),),
            ),
            PaperRelevanceJudgment(
                paper_id=PAPER_B,
                relevance=2,
                rationale="Relevant.",
            ),
            PaperRelevanceJudgment(
                paper_id=PAPER_C,
                relevance=1,
                rationale="Marginally relevant.",
            ),
            PaperRelevanceJudgment(
                paper_id=PAPER_D,
                relevance=0,
                rationale="Irrelevant.",
            ),
        ),
    )


def test_evaluation_dataset_round_trip() -> None:
    dataset = RetrievalEvaluationDataset(
        name="retrieval-evaluation-test",
        version="1",
        description="Deterministic test dataset.",
        cases=(_build_case(),),
    )

    restored = RetrievalEvaluationDataset.from_dict(dataset.to_dict())

    assert restored == dataset


def test_evaluate_known_nonideal_ranking() -> None:
    result = evaluate_paper_ranking(
        case=_build_case(),
        ranked_paper_ids=(PAPER_B, PAPER_D, PAPER_A, PAPER_C),
        k_values=(1, 3, 4),
    )
    metrics = {item.k: item for item in result.metrics_at_k}

    assert result.relevant_count == 3
    assert math.isclose(result.reciprocal_rank, 1.0)
    assert math.isclose(result.average_precision, 29 / 36)

    assert math.isclose(metrics[1].precision, 1.0)
    assert math.isclose(metrics[1].recall, 1 / 3)
    assert math.isclose(metrics[1].ndcg, 3 / 7)

    assert math.isclose(metrics[3].precision, 2 / 3)
    assert math.isclose(metrics[3].recall, 2 / 3)

    assert math.isclose(metrics[4].precision, 3 / 4)
    assert math.isclose(metrics[4].recall, 1.0)
    assert 0.0 < metrics[4].ndcg < 1.0


def test_ideal_ranking_has_perfect_metrics() -> None:
    result = evaluate_paper_ranking(
        case=_build_case(),
        ranked_paper_ids=(PAPER_A, PAPER_B, PAPER_C, PAPER_D),
        k_values=(1, 3, 4),
    )

    assert math.isclose(result.reciprocal_rank, 1.0)
    assert math.isclose(result.average_precision, 1.0)
    assert all(math.isclose(item.ndcg, 1.0) for item in result.metrics_at_k)
