import json
from pathlib import Path


def test_retrieval_experiment_registry_paths_and_recommendation() -> None:
    repo_root = Path.home() / "ai4research"
    registry_path = (
        repo_root
        / "evaluation_datasets/retrieval/retrieval_suite_v1_experiment_registry.json"
    )

    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    assert registry["name"] == "ai4research-retrieval-suite-v1-experiment-registry"
    assert registry["suite"]["case_count"] == 8

    baseline_names = {
        baseline["name"]
        for baseline in registry["baselines"]
    }

    assert "bm25" in baseline_names
    assert "bge_m3_vector_truncated_3200" in baseline_names
    assert "bm25_bge_m3_hybrid_w070_030" in baseline_names
    assert "bm25_bge_m3_subchunk_hybrid_w070_030" in baseline_names

    assert (
        registry["current_recommendation"]["default_retrieval_strategy"]
        == "bm25_bge_m3_subchunk_hybrid_w070_030"
    )

    referenced_paths = [
        registry["suite"]["manifest_path"],
        registry["weight_scan"]["report_path"],
        registry["weight_scan"]["summary_path"],
    ]

    for baseline in registry["baselines"]:
        referenced_paths.append(baseline["summary_path"])
        if "report_path" in baseline:
            referenced_paths.append(baseline["report_path"])

    for relative_path in referenced_paths:
        assert (repo_root / relative_path).is_file(), relative_path

    next_task_names = {
        task["name"]
        for task in registry["next_tasks"]
    }
    assert "subchunk_embedding" in next_task_names

def test_rerank_experiment_is_full_suite_validated_but_not_default() -> None:
    repo_root = Path.home() / "ai4research"
    registry_path = (
        repo_root
        / "evaluation_datasets/retrieval/"
        / "retrieval_suite_v1_experiment_registry.json"
    )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    rerank_baseline = next(
        baseline
        for baseline in registry["baselines"]
        if baseline["name"]
        == "bge_m3_rerank_from_recommended_hybrid"
    )

    assert rerank_baseline["type"] == "reranker"
    assert rerank_baseline["status"] == (
        "experimental_not_recommended"
    )
    assert rerank_baseline["input_baseline"] == (
        "bm25_bge_m3_subchunk_hybrid_w070_030"
    )
    assert rerank_baseline["macro"]["macro_ap"] == 0.7713

    reranker_task = next(
        task
        for task in registry["next_tasks"]
        if task["name"] == "reranker"
    )
    assert reranker_task["status"] == (
        "full_suite_validated_experimental_not_recommended"
    )

    assert (
        registry["current_recommendation"]
        ["default_retrieval_strategy"]
        != rerank_baseline["name"]
    )

