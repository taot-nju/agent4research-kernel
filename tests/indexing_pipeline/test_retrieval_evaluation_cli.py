import json
from pathlib import Path

from ai4research.indexing_pipeline.evaluation.schema import (
    PaperRelevanceJudgment,
    RetrievalEvaluationCase,
    RetrievalEvaluationDataset,
)
from ai4research.indexing_pipeline.scripts_py.evaluate_saved_retrieval import (
    main,
)


PAPER_A = "a" * 40
PAPER_B = "b" * 40


def test_cli_evaluates_and_saves_json(
    tmp_path: Path,
    capsys,
) -> None:
    dataset_path = tmp_path / "dataset.json"
    search_result_path = tmp_path / "search-result.json"
    report_path = tmp_path / "metrics.json"

    dataset = RetrievalEvaluationDataset(
        name="cli-test",
        version="1",
        cases=(
            RetrievalEvaluationCase(
                case_id="cli-case",
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
    dataset_path.write_text(
        json.dumps(dataset.to_dict(), ensure_ascii=False),
        encoding="utf-8",
    )

    search_result_path.write_text(
        json.dumps(
            {
                "query": "agent memory trajectory",
                "paper_search_result": {
                    "hits": [
                        {"rank": 1, "paper_id": PAPER_A, "score": 2.0},
                        {"rank": 2, "paper_id": PAPER_B, "score": 1.0},
                    ]
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--dataset",
            str(dataset_path),
            "--search-result",
            str(search_result_path),
            "--k",
            "1",
            "--k",
            "2",
            "--save-json",
            str(report_path),
        ]
    )

    output = capsys.readouterr().out
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "论文检索评估结果" in output
    assert "average_precision:   1.0000" in output
    assert f"JSON report saved: {report_path.resolve()}" in output

    assert report["case_id"] == "cli-case"
    assert report["reciprocal_rank"] == 1.0
    assert report["average_precision"] == 1.0
    assert [item["k"] for item in report["metrics_at_k"]] == [1, 2]
