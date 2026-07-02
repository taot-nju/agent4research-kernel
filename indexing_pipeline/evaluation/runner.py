"""读取真实评估集和已保存检索结果，生成论文排序评估。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .metrics import PaperRankingEvaluation, evaluate_paper_ranking
from .schema import RetrievalEvaluationCase, RetrievalEvaluationDataset


def _read_json_object(path: str | Path) -> dict[str, Any]:
    resolved_path = Path(path).expanduser().resolve()

    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"json_file_missing: {resolved_path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid_json: {resolved_path}: line={exc.lineno} column={exc.colno}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(f"json_root_must_be_object: {resolved_path}")

    return payload


def load_evaluation_dataset(
    path: str | Path,
) -> RetrievalEvaluationDataset:
    """从 JSON 文件读取并校验检索评估数据集。"""

    return RetrievalEvaluationDataset.from_dict(_read_json_object(path))


def select_evaluation_case(
    *,
    dataset: RetrievalEvaluationDataset,
    case_id: str | None = None,
) -> RetrievalEvaluationCase:
    """按 case_id 选择评估用例；单用例数据集可省略 case_id。"""

    if case_id is None:
        if len(dataset.cases) != 1:
            raise ValueError(
                "case_id_required_for_multi_case_dataset: "
                f"case_count={len(dataset.cases)}"
            )
        return dataset.cases[0]

    matches = tuple(case for case in dataset.cases if case.case_id == case_id)

    if not matches:
        raise ValueError(f"evaluation_case_not_found: {case_id}")
    if len(matches) > 1:
        raise ValueError(f"duplicate_evaluation_case_id: {case_id}")

    return matches[0]


def extract_ranked_paper_ids(
    search_result: Mapping[str, Any],
) -> tuple[str, ...]:
    """从候选全文检索 JSON 中提取论文级排序。"""

    paper_search_result = search_result.get("paper_search_result")
    if not isinstance(paper_search_result, Mapping):
        raise ValueError("paper_search_result_missing_or_invalid")

    hits = paper_search_result.get("hits")
    if not isinstance(hits, list):
        raise ValueError("paper_search_result_hits_missing_or_invalid")

    ranked_paper_ids: list[str] = []

    for index, hit in enumerate(hits):
        if not isinstance(hit, Mapping):
            raise ValueError(f"paper_hit_must_be_object: index={index}")

        paper_id = hit.get("paper_id")
        if not isinstance(paper_id, str) or not paper_id.strip():
            raise ValueError(f"paper_hit_id_missing_or_invalid: index={index}")

        ranked_paper_ids.append(paper_id.strip())

    if len(set(ranked_paper_ids)) != len(ranked_paper_ids):
        raise ValueError("ranked_paper_ids_must_be_unique")

    return tuple(ranked_paper_ids)


def evaluate_saved_paper_ranking(
    *,
    dataset_path: str | Path,
    search_result_path: str | Path,
    case_id: str | None = None,
    k_values: tuple[int, ...] = (1, 3, 5, 10),
    minimum_relevance: int = 1,
) -> PaperRankingEvaluation:
    """评估一份已保存的候选全文论文排序结果。"""

    dataset = load_evaluation_dataset(dataset_path)
    case = select_evaluation_case(dataset=dataset, case_id=case_id)
    search_result = _read_json_object(search_result_path)

    search_query = search_result.get("query")
    if search_query != case.query:
        raise ValueError(
            "evaluation_query_mismatch: "
            f"expected={case.query!r} actual={search_query!r}"
        )

    ranked_paper_ids = extract_ranked_paper_ids(search_result)
    unexpected_ids = tuple(
        paper_id
        for paper_id in ranked_paper_ids
        if paper_id not in case.candidate_paper_ids
    )
    if unexpected_ids:
        raise ValueError(
            f"ranked_papers_outside_candidate_set: {unexpected_ids!r}"
        )

    return evaluate_paper_ranking(
        case=case,
        ranked_paper_ids=ranked_paper_ids,
        k_values=k_values,
        minimum_relevance=minimum_relevance,
    )
