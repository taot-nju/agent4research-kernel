"""检索评测集的数据结构与校验规则。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


RELEVANCE_GRADES = {
    0,
    1,
    2,
    3,
}

RELEVANCE_GRADE_MEANINGS = {
    0: "irrelevant",
    1: "marginally_relevant",
    2: "relevant",
    3: "highly_relevant",
}

_CASE_ID_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9._-]*$"
)


@dataclass(frozen=True)
class PaperRelevanceJudgment:
    """一篇候选论文对某个查询的人工相关性判断。"""

    paper_id: str
    relevance: int

    rationale: str = ""
    evidence_page_ranges: tuple[
        tuple[int, int],
        ...,
    ] = ()
    relevant_chunk_ids: tuple[
        str,
        ...,
    ] = ()

    def __post_init__(self) -> None:
        if not self.paper_id.strip():
            raise ValueError(
                "paper_id 不能为空"
            )

        if self.relevance not in (
            RELEVANCE_GRADES
        ):
            raise ValueError(
                "relevance 必须是 0、1、2 或 3"
            )

        for page_start, page_end in (
            self.evidence_page_ranges
        ):
            if page_start <= 0:
                raise ValueError(
                    "证据起始页必须是正整数"
                )

            if page_end < page_start:
                raise ValueError(
                    "证据结束页不能小于起始页"
                )

        if len(
            set(self.relevant_chunk_ids)
        ) != len(self.relevant_chunk_ids):
            raise ValueError(
                "relevant_chunk_ids 不能重复"
            )

    @property
    def relevance_label(self) -> str:
        return RELEVANCE_GRADE_MEANINGS[
            self.relevance
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "relevance": self.relevance,
            "relevance_label": (
                self.relevance_label
            ),
            "rationale": self.rationale,
            "evidence_page_ranges": [
                [
                    page_start,
                    page_end,
                ]
                for page_start, page_end
                in self.evidence_page_ranges
            ],
            "relevant_chunk_ids": list(
                self.relevant_chunk_ids
            ),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> PaperRelevanceJudgment:
        return cls(
            paper_id=str(
                data.get("paper_id", "")
            ).strip(),
            relevance=int(
                data.get("relevance", -1)
            ),
            rationale=str(
                data.get("rationale", "")
            ).strip(),
            evidence_page_ranges=tuple(
                (
                    int(page_range[0]),
                    int(page_range[1]),
                )
                for page_range in data.get(
                    "evidence_page_ranges",
                    [],
                )
            ),
            relevant_chunk_ids=tuple(
                str(chunk_id).strip()
                for chunk_id in data.get(
                    "relevant_chunk_ids",
                    [],
                )
                if str(chunk_id).strip()
            ),
        )


@dataclass(frozen=True)
class RetrievalEvaluationCase:
    """一个查询及其候选论文和人工判断。"""

    case_id: str
    query: str
    candidate_paper_ids: tuple[
        str,
        ...,
    ]
    judgments: tuple[
        PaperRelevanceJudgment,
        ...,
    ]

    description: str = ""
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized_case_id = (
            self.case_id.strip()
        )

        if not _CASE_ID_PATTERN.fullmatch(
            normalized_case_id
        ):
            raise ValueError(
                "case_id 只能包含小写字母、"
                "数字、点、下划线和连字符"
            )

        if not self.query.strip():
            raise ValueError(
                "query 不能为空"
            )

        if not self.candidate_paper_ids:
            raise ValueError(
                "candidate_paper_ids 不能为空"
            )

        if len(
            set(self.candidate_paper_ids)
        ) != len(
            self.candidate_paper_ids
        ):
            raise ValueError(
                "candidate_paper_ids 不能重复"
            )

        judgment_paper_ids = [
            judgment.paper_id
            for judgment in self.judgments
        ]

        if len(
            set(judgment_paper_ids)
        ) != len(judgment_paper_ids):
            raise ValueError(
                "同一论文不能重复标注"
            )

        unknown_judgments = (
            set(judgment_paper_ids)
            - set(self.candidate_paper_ids)
        )

        if unknown_judgments:
            raise ValueError(
                "judgment 必须属于候选论文集合"
            )

        if len(set(self.tags)) != len(
            self.tags
        ):
            raise ValueError(
                "tags 不能重复"
            )

    @property
    def judgment_by_paper_id(
        self,
    ) -> dict[
        str,
        PaperRelevanceJudgment,
    ]:
        return {
            judgment.paper_id: judgment
            for judgment in self.judgments
        }

    def relevant_paper_ids(
        self,
        *,
        minimum_relevance: int = 1,
    ) -> tuple[str, ...]:
        if minimum_relevance not in {
            1,
            2,
            3,
        }:
            raise ValueError(
                "minimum_relevance 必须是 1、2 或 3"
            )

        return tuple(
            judgment.paper_id
            for judgment in self.judgments
            if judgment.relevance
            >= minimum_relevance
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "query": self.query,
            "description": self.description,
            "tags": list(self.tags),
            "candidate_paper_ids": list(
                self.candidate_paper_ids
            ),
            "judgments": [
                judgment.to_dict()
                for judgment
                in self.judgments
            ],
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> RetrievalEvaluationCase:
        return cls(
            case_id=str(
                data.get("case_id", "")
            ).strip(),
            query=str(
                data.get("query", "")
            ).strip(),
            description=str(
                data.get("description", "")
            ).strip(),
            tags=tuple(
                str(tag).strip()
                for tag in data.get(
                    "tags",
                    [],
                )
                if str(tag).strip()
            ),
            candidate_paper_ids=tuple(
                str(paper_id).strip()
                for paper_id in data.get(
                    "candidate_paper_ids",
                    [],
                )
                if str(paper_id).strip()
            ),
            judgments=tuple(
                PaperRelevanceJudgment.from_dict(
                    judgment
                )
                for judgment in data.get(
                    "judgments",
                    [],
                )
            ),
        )


@dataclass(frozen=True)
class RetrievalEvaluationDataset:
    """一组可版本化的检索评测样例。"""

    name: str
    version: str
    cases: tuple[
        RetrievalEvaluationCase,
        ...]

    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError(
                "dataset name 不能为空"
            )

        if not self.version.strip():
            raise ValueError(
                "dataset version 不能为空"
            )

        if not self.cases:
            raise ValueError(
                "dataset cases 不能为空"
            )

        case_ids = [
            case.case_id
            for case in self.cases
        ]

        if len(set(case_ids)) != len(
            case_ids
        ):
            raise ValueError(
                "dataset case_id 不能重复"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "cases": [
                case.to_dict()
                for case in self.cases
            ],
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> RetrievalEvaluationDataset:
        return cls(
            name=str(
                data.get("name", "")
            ).strip(),
            version=str(
                data.get("version", "")
            ).strip(),
            description=str(
                data.get("description", "")
            ).strip(),
            cases=tuple(
                RetrievalEvaluationCase.from_dict(
                    case
                )
                for case in data.get(
                    "cases",
                    [],
                )
            ),
        )
