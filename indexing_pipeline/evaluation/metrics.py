"""论文级检索评测指标。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ai4research.indexing_pipeline.evaluation.schema import (
    RetrievalEvaluationCase,
)


@dataclass(frozen=True)
class RankingAtKMetrics:
    """指定 K 下的论文排名指标。"""

    k: int
    precision: float
    recall: float
    ndcg: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "k": self.k,
            "precision": self.precision,
            "recall": self.recall,
            "ndcg": self.ndcg,
        }


@dataclass(frozen=True)
class PaperRankingEvaluation:
    """一个评测样例的论文级排名结果。"""

    case_id: str
    query: str

    candidate_count: int
    judged_count: int
    relevant_count: int
    retrieved_count: int

    minimum_relevance: int
    reciprocal_rank: float
    average_precision: float

    metrics_at_k: tuple[
        RankingAtKMetrics,
        ...,
    ]

    ranked_paper_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "query": self.query,
            "candidate_count": (
                self.candidate_count
            ),
            "judged_count": self.judged_count,
            "relevant_count": (
                self.relevant_count
            ),
            "retrieved_count": (
                self.retrieved_count
            ),
            "minimum_relevance": (
                self.minimum_relevance
            ),
            "reciprocal_rank": (
                self.reciprocal_rank
            ),
            "average_precision": (
                self.average_precision
            ),
            "metrics_at_k": {
                str(metrics.k): (
                    metrics.to_dict()
                )
                for metrics
                in self.metrics_at_k
            },
            "ranked_paper_ids": list(
                self.ranked_paper_ids
            ),
        }


def _discounted_cumulative_gain(
    relevance_grades: list[int],
) -> float:
    return sum(
        (
            (2 ** relevance_grade) - 1
        )
        / math.log2(rank + 1)
        for rank, relevance_grade
        in enumerate(
            relevance_grades,
            start=1,
        )
    )


def evaluate_paper_ranking(
    *,
    case: RetrievalEvaluationCase,
    ranked_paper_ids: tuple[str, ...],
    k_values: tuple[int, ...] = (
        1,
        3,
        5,
        10,
    ),
    minimum_relevance: int = 1,
) -> PaperRankingEvaluation:
    """计算一个查询的论文级排名指标。"""

    if minimum_relevance not in {
        1,
        2,
        3,
    }:
        raise ValueError(
            "minimum_relevance 必须是 1、2 或 3"
        )

    if not k_values:
        raise ValueError(
            "k_values 不能为空"
        )

    if any(k <= 0 for k in k_values):
        raise ValueError(
            "所有 K 必须大于 0"
        )

    if len(set(k_values)) != len(
        k_values
    ):
        raise ValueError(
            "k_values 不能重复"
        )

    if len(
        set(ranked_paper_ids)
    ) != len(ranked_paper_ids):
        raise ValueError(
            "ranked_paper_ids 不能重复"
        )

    unknown_paper_ids = (
        set(ranked_paper_ids)
        - set(case.candidate_paper_ids)
    )

    if unknown_paper_ids:
        raise ValueError(
            "排名结果包含候选集合外的论文"
        )

    judgment_by_paper_id = (
        case.judgment_by_paper_id
    )

    relevance_by_paper_id = {
        paper_id: (
            judgment_by_paper_id[
                paper_id
            ].relevance
            if paper_id
            in judgment_by_paper_id
            else 0
        )
        for paper_id
        in case.candidate_paper_ids
    }

    relevant_paper_ids = {
        paper_id
        for paper_id, relevance
        in relevance_by_paper_id.items()
        if relevance >= minimum_relevance
    }
    relevant_count = len(
        relevant_paper_ids
    )

    reciprocal_rank = 0.0

    for rank, paper_id in enumerate(
        ranked_paper_ids,
        start=1,
    ):
        if paper_id in relevant_paper_ids:
            reciprocal_rank = 1.0 / rank
            break

    precision_sum = 0.0
    relevant_seen = 0

    for rank, paper_id in enumerate(
        ranked_paper_ids,
        start=1,
    ):
        if paper_id not in relevant_paper_ids:
            continue

        relevant_seen += 1
        precision_sum += (
            relevant_seen / rank
        )

    average_precision = (
        precision_sum / relevant_count
        if relevant_count
        else 0.0
    )

    ideal_relevance_grades = sorted(
        relevance_by_paper_id.values(),
        reverse=True,
    )

    metrics_at_k = []

    for k in sorted(k_values):
        top_k_paper_ids = (
            ranked_paper_ids[:k]
        )
        relevant_in_top_k = sum(
            paper_id in relevant_paper_ids
            for paper_id
            in top_k_paper_ids
        )

        precision = (
            relevant_in_top_k / k
        )
        recall = (
            relevant_in_top_k
            / relevant_count
            if relevant_count
            else 0.0
        )

        actual_grades = [
            relevance_by_paper_id[
                paper_id
            ]
            for paper_id
            in top_k_paper_ids
        ]

        if len(actual_grades) < k:
            actual_grades.extend(
                [0] * (
                    k - len(actual_grades)
                )
            )

        ideal_grades = (
            ideal_relevance_grades[:k]
        )

        if len(ideal_grades) < k:
            ideal_grades.extend(
                [0] * (
                    k - len(ideal_grades)
                )
            )

        actual_dcg = (
            _discounted_cumulative_gain(
                actual_grades
            )
        )
        ideal_dcg = (
            _discounted_cumulative_gain(
                ideal_grades
            )
        )
        ndcg = (
            actual_dcg / ideal_dcg
            if ideal_dcg > 0
            else 0.0
        )

        metrics_at_k.append(
            RankingAtKMetrics(
                k=k,
                precision=precision,
                recall=recall,
                ndcg=ndcg,
            )
        )

    return PaperRankingEvaluation(
        case_id=case.case_id,
        query=case.query,
        candidate_count=len(
            case.candidate_paper_ids
        ),
        judged_count=len(
            case.judgments
        ),
        relevant_count=relevant_count,
        retrieved_count=len(
            ranked_paper_ids
        ),
        minimum_relevance=(
            minimum_relevance
        ),
        reciprocal_rank=reciprocal_rank,
        average_precision=(
            average_precision
        ),
        metrics_at_k=tuple(
            metrics_at_k
        ),
        ranked_paper_ids=(
            ranked_paper_ids
        ),
    )
