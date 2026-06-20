"""
给定 Research Topic，自动获得相关论文 Markdown 路径。

支持：
1. 预览候选论文；
2. 自动下载缺失 PDF；
3. 自动刷新文档任务；
4. 自动 OCR；
5. 自动质量检查；
6. 输出可用 Markdown 绝对路径。
"""

import argparse
import json
import os
import socket
from pathlib import Path

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.document_pipeline.config import (
    load_ocr_service_config,
)
from ai4research.document_pipeline.ocr_backends.openai_compatible import (
    OpenAICompatibleOCRBackend,
)
from ai4research.document_pipeline.parsers.ocr_document_parser import (
    DEFAULT_MAX_PAGE_WORKERS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_RENDER_DPI,
    DEFAULT_TEMPERATURE,
    OCRDocumentParser,
)
from ai4research.document_pipeline.quality_checks.basic import (
    BasicDocumentQualityChecker,
)
from ai4research.research_pipeline.pipelines.topic_to_documents import (
    run_topic_to_documents,
    select_processable_topic_candidates,
)
from ai4research.research_pipeline.retrieval.mongo_lexical import (
    MongoLexicalTopicRetriever,
)


DEFAULT_TOP_K = 3
DEFAULT_CANDIDATE_POOL_SIZE = 1000
DEFAULT_CANDIDATE_SCAN_LIMIT = 30

def build_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description=(
            "根据 Research Topic 从 MongoDB 召回论文，"
            "自动完成 PDF、OCR、质检并输出 Markdown 路径。"
        )
    )

    parser.add_argument(
        "--topic",
        type=str,
        required=True,
        help=(
            'Research Topic，例如 "agent memory"。'
        ),
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=(
            "最终处理的相关论文数量；"
            f"默认 {DEFAULT_TOP_K}。"
        ),
    )

    parser.add_argument(
        "--candidate-pool-size",
        type=int,
        default=(
            DEFAULT_CANDIDATE_POOL_SIZE
        ),
        help=(
            "MongoDB 初始候选池上限；"
            f"默认 "
            f"{DEFAULT_CANDIDATE_POOL_SIZE}。"
        ),
    )

    parser.add_argument(
        "--candidate-scan-limit",
        type=int,
        default=DEFAULT_CANDIDATE_SCAN_LIMIT,
        help=(
            "为自动补位而检查的高相关候选数量；"
            f"默认 {DEFAULT_CANDIDATE_SCAN_LIMIT}。"
        ),
    )

    parser.add_argument(
        "--preview",
        action="store_true",
        help=(
            "只预览召回结果，不下载、"
            "不 OCR、不修改数据库。"
        ),
    )

    parser.add_argument(
        "--download-workers",
        type=int,
        default=1,
        help=(
            "PDF 下载线程数；默认 1。"
        ),
    )

    parser.add_argument(
        "--page-workers",
        type=int,
        default=DEFAULT_MAX_PAGE_WORKERS,
        help=(
            "单篇论文页面 OCR 线程数；"
            f"默认 {DEFAULT_MAX_PAGE_WORKERS}。"
        ),
    )

    parser.add_argument(
        "--render-dpi",
        type=int,
        default=DEFAULT_RENDER_DPI,
        help=(
            "PDF 页面渲染 DPI；"
            f"默认 {DEFAULT_RENDER_DPI}。"
        ),
    )

    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=(
            "单页 OCR 最大输出 token；"
            f"默认 {DEFAULT_MAX_TOKENS}。"
        ),
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help=(
            "OCR 采样温度；"
            f"默认 {DEFAULT_TEMPERATURE}。"
        ),
    )

    parser.add_argument(
        "--pdf-lease-seconds",
        type=int,
        default=600,
        help="PDF 下载任务租约秒数；默认 600。",
    )

    parser.add_argument(
        "--document-lease-seconds",
        type=int,
        default=3600,
        help=(
            "文档解析任务租约秒数；默认 3600。"
        ),
    )

    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="任务最大尝试次数；默认 3。",
    )

    parser.add_argument(
        "--retry-delay-seconds",
        type=int,
        default=60,
        help="失败重试等待秒数；默认 60。",
    )

    parser.add_argument(
        "--recheck-quality",
        action="store_true",
        help=(
            "重新检查已有文档质量结果。"
        ),
    )

    parser.add_argument(
        "--worker-id",
        type=str,
        default="",
        help=(
            "可选 Worker 前缀；"
            "默认根据 hostname 和进程 ID 生成。"
        ),
    )

    parser.add_argument(
        "--save-json",
        type=str,
        default="",
        help=(
            "可选，把完整工作流结果保存为 JSON。"
        ),
    )

    return parser


def validate_arguments(
    args: argparse.Namespace,
) -> None:
    """检查命令行参数。"""

    positive_arguments = {
        "--top-k": args.top_k,
        "--candidate-pool-size": (
            args.candidate_pool_size
        ),
        "--candidate-scan-limit": (
            args.candidate_scan_limit
        ),
        "--download-workers": (
            args.download_workers
        ),
        "--page-workers": (
            args.page_workers
        ),
        "--render-dpi": args.render_dpi,
        "--max-tokens": args.max_tokens,
        "--pdf-lease-seconds": (
            args.pdf_lease_seconds
        ),
        "--document-lease-seconds": (
            args.document_lease_seconds
        ),
        "--max-attempts": (
            args.max_attempts
        ),
        "--retry-delay-seconds": (
            args.retry_delay_seconds
        ),
    }

    for name, value in positive_arguments.items():
        if value <= 0:
            raise ValueError(
                f"{name} 必须大于 0"
            )

    if args.temperature < 0:
        raise ValueError(
            "--temperature 不能小于 0"
        )

    if not args.topic.strip():
        raise ValueError(
            "--topic 不能为空"
        )


def build_worker_id(
    configured_worker_id: str,
) -> str:
    """生成工作流 Worker 前缀。"""

    normalized_worker_id = (
        configured_worker_id.strip()
    )

    if normalized_worker_id:
        return normalized_worker_id

    return (
        f"{socket.gethostname()}"
        f"-pid-{os.getpid()}"
        "-topic-workflow"
    )


def print_candidates(
    candidates,
) -> None:
    """打印召回候选列表。"""

    print("=" * 100)
    print("Research Topic 召回结果")
    print("=" * 100)

    if not candidates:
        print("没有找到相关论文。")
        return

    for rank, candidate in enumerate(
        candidates,
        start=1,
    ):
        print("-" * 100)
        print(f"rank:          {rank}")
        print(
            f"paper_id:      "
            f"{candidate.paper_id}"
        )
        print(
            f"score:         "
            f"{candidate.score:.4f}"
        )
        print(
            f"title:         "
            f"{candidate.title}"
        )
        print(
            f"accepted_by:   "
            f"{candidate.accepted_by}"
        )
        print(
            f"matched_fields:"
            f" {candidate.matched_fields}"
        )


def save_result_json(
    *,
    output_path: str,
    result: dict,
) -> Path:
    """原子保存工作流 JSON 结果。"""

    path = Path(
        output_path
    ).expanduser().resolve()

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    temp_path.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    temp_path.replace(path)

    return path


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    validate_arguments(args)

    MongoDBClient.ping()
    print("✅ MongoDB connected successfully.")

    retriever = MongoLexicalTopicRetriever(
        candidate_pool_size=(
            args.candidate_pool_size
        )
    )

    if args.preview:
        # candidates = retriever.search(
        #     topic=args.topic,
        #     limit=args.top_k,
        # )

        candidates = select_processable_topic_candidates(
            topic=args.topic,
            top_k=args.top_k,
            candidate_scan_limit=(
                args.candidate_scan_limit
            ),
            retriever=retriever,
        )

        print_candidates(candidates)
        print("=" * 100)
        print(
            "✅ Preview completed; "
            "没有下载、OCR 或修改数据库。"
        )
        return

    service_config = (
        load_ocr_service_config()
    )
    ocr_backend = (
        OpenAICompatibleOCRBackend(
            config=service_config
        )
    )

    print("🔎 Checking OCR service...")
    ocr_backend.check_health()
    print("✅ OCR service is ready.")

    document_parser = OCRDocumentParser(
        backend=ocr_backend
    )
    quality_checker = (
        BasicDocumentQualityChecker()
    )
    worker_id = build_worker_id(
        args.worker_id
    )

    print("=" * 100)
    print("Research Topic 工作流配置")
    print("=" * 100)
    print(f"topic:                   {args.topic}")
    print(f"top_k:                   {args.top_k}")
    print(
        f"candidate_pool_size:     "
        f"{args.candidate_pool_size}"
    )
    print(
        f"candidate_scan_limit:    "
        f"{args.candidate_scan_limit}"
    )
    print(
        f"download_workers:        "
        f"{args.download_workers}"
    )
    print(
        f"page_workers:            "
        f"{args.page_workers}"
    )
    print(
        f"render_dpi:              "
        f"{args.render_dpi}"
    )
    print(
        f"max_tokens:              "
        f"{args.max_tokens}"
    )
    print(
        f"worker_id:               "
        f"{worker_id}"
    )
    print("=" * 100)

    result = run_topic_to_documents(
        topic=args.topic,
        top_k=args.top_k,
        candidate_scan_limit=(
            args.candidate_scan_limit
        ),
        retriever=retriever,
        document_parser=document_parser,
        quality_checker=quality_checker,
        worker_id_prefix=worker_id,
        parser_options={
            "render_dpi": args.render_dpi,
            "max_page_workers": (
                args.page_workers
            ),
            "max_tokens": args.max_tokens,
            "temperature": args.temperature,
        },
        download_workers=(
            args.download_workers
        ),
        pdf_lease_seconds=(
            args.pdf_lease_seconds
        ),
        document_lease_seconds=(
            args.document_lease_seconds
        ),
        max_attempts=args.max_attempts,
        retry_delay_seconds=(
            args.retry_delay_seconds
        ),
        recheck_quality=(
            args.recheck_quality
        ),
    )

    print_candidates(
        result.candidates
    )

    print("=" * 100)
    print("阶段统计")
    print("=" * 100)
    print(
        "恢复 PDF 任务:       "
        f"{result.refreshed_pdf_tasks}"
    )
    print(
        "文档可用性变化:      "
        f"{result.document_availability_changes}"
    )
    print(
        f"PDF:                 "
        f"{result.pdf_summary}"
    )
    print(
        f"Document:            "
        f"{result.document_summary}"
    )
    print(
        f"Quality:             "
        f"{result.quality_summary}"
    )

    print("=" * 100)
    print("最终论文状态")
    print("=" * 100)

    for outcome in result.outcomes:
        print("-" * 100)
        print(f"rank:             {outcome.rank}")
        print(f"paper_id:         {outcome.paper_id}")
        print(f"title:            {outcome.title}")
        print(f"pdf_status:       {outcome.pdf_status}")
        print(
            f"document_status:  "
            f"{outcome.document_status}"
        )
        print(
            f"quality_status:   "
            f"{outcome.quality_status}"
        )
        print(f"ready:            {outcome.ready}")
        print(f"error:            {outcome.error}")

    ready_paths = [
        outcome.markdown_absolute_path
        for outcome in result.outcomes
        if outcome.ready
        and outcome.markdown_absolute_path
    ]

    print("=" * 100)
    print("READY_MARKDOWN_PATHS")
    print("=" * 100)

    if ready_paths:
        for path in ready_paths:
            print(path)
    else:
        print("<none>")

    if args.save_json:
        saved_path = save_result_json(
            output_path=args.save_json,
            result=result.to_dict(),
        )

        print("=" * 100)
        print(
            f"JSON result saved: {saved_path}"
        )


if __name__ == "__main__":
    main()
