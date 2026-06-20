"""
按条件解析论文 PDF，生成标准文档资产。

当前执行模式：
- 论文之间顺序处理；
- 单篇论文内部按页并发 OCR。

未来可以在不修改 Parser 和单任务 Pipeline 的情况下，
增加多论文并发运行器。
"""

import argparse
import os
import socket
from typing import Any

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
from ai4research.document_pipeline.pipelines.document_parse_runner import (
    DEFAULT_DOCUMENT_LEASE_SECONDS,
    DEFAULT_DOCUMENT_MAX_ATTEMPTS,
    DEFAULT_DOCUMENT_RETRY_DELAY_SECONDS,
    run_document_parse_tasks,
)


DEFAULT_LIMIT = 1


def build_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description=(
            "使用可配置 OCR 后端解析 PDF，"
            "生成标准 Markdown 和解析报告。"
        )
    )

    selection_group = (
        parser.add_mutually_exclusive_group(
            required=True
        )
    )

    selection_group.add_argument(
        "--paper-id",
        type=str,
        help="只处理指定 MongoDB 论文 _id。",
    )

    selection_group.add_argument(
        "--accepted-by",
        type=str,
        help=(
            '只处理指定会议，例如 "NeurIPS 2025"。'
        ),
    )

    selection_group.add_argument(
        "--all",
        action="store_true",
        help=(
            "允许从全部可领取任务中处理；"
            "仍受到 --limit 限制。"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=(
            "本次最多解析多少篇论文；"
            f"默认 {DEFAULT_LIMIT}。"
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
        "--page-workers",
        type=int,
        default=DEFAULT_MAX_PAGE_WORKERS,
        help=(
            "单篇论文内部的页面 OCR 线程数；"
            f"默认 {DEFAULT_MAX_PAGE_WORKERS}。"
        ),
    )

    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=(
            "单页 OCR 最大输出 token 数；"
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
        "--lease-seconds",
        type=int,
        default=DEFAULT_DOCUMENT_LEASE_SECONDS,
        help=(
            "单篇文档解析任务租约秒数；"
            f"默认 {DEFAULT_DOCUMENT_LEASE_SECONDS}。"
        ),
    )

    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_DOCUMENT_MAX_ATTEMPTS,
        help=(
            "单篇论文允许的最大领取次数；"
            f"默认 {DEFAULT_DOCUMENT_MAX_ATTEMPTS}。"
        ),
    )

    parser.add_argument(
        "--retry-delay-seconds",
        type=int,
        default=(
            DEFAULT_DOCUMENT_RETRY_DELAY_SECONDS
        ),
        help=(
            "失败后允许重试前的等待秒数；"
            f"默认 "
            f"{DEFAULT_DOCUMENT_RETRY_DELAY_SECONDS}。"
        ),
    )

    parser.add_argument(
        "--worker-id",
        type=str,
        default="",
        help=(
            "可选 Worker 标识；"
            "默认根据 hostname 和进程 ID 生成。"
        ),
    )

    return parser


def build_selection_filter(
    args: argparse.Namespace,
) -> dict[str, Any]:
    """根据命令行参数构造业务筛选条件。"""

    if args.paper_id:
        paper_id = args.paper_id.strip()

        if not paper_id:
            raise ValueError(
                "--paper-id 不能为空"
            )

        return {
            "_id": paper_id,
        }

    if args.accepted_by:
        accepted_by = (
            args.accepted_by.strip()
        )

        if not accepted_by:
            raise ValueError(
                "--accepted-by 不能为空"
            )

        return {
            "accepted_by": accepted_by,
        }

    if args.all:
        return {}

    raise ValueError(
        "必须指定 --paper-id、"
        "--accepted-by 或 --all"
    )


def build_worker_id(
    configured_worker_id: str,
) -> str:
    """返回显式配置或自动生成的 Worker ID。"""

    normalized_worker_id = (
        configured_worker_id.strip()
    )

    if normalized_worker_id:
        return normalized_worker_id

    return (
        f"{socket.gethostname()}"
        f"-pid-{os.getpid()}"
    )


def validate_arguments(
    args: argparse.Namespace,
) -> None:
    """检查命令行数值参数。"""

    positive_arguments = {
        "--limit": args.limit,
        "--render-dpi": args.render_dpi,
        "--page-workers": args.page_workers,
        "--max-tokens": args.max_tokens,
        "--lease-seconds": args.lease_seconds,
        "--max-attempts": args.max_attempts,
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


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    validate_arguments(args)

    selection_filter = build_selection_filter(
        args
    )
    worker_id = build_worker_id(
        args.worker_id
    )

    service_config = (
        load_ocr_service_config()
    )

    # ocr_backend = (
    #     OpenAICompatibleOCRBackend(
    #         config=service_config
    #     )
    # )
    # document_parser = OCRDocumentParser(
    #     backend=ocr_backend
    # )

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


    MongoDBClient.ping()

    print("✅ MongoDB connected successfully.")
    print("=" * 100)
    print("文档解析任务配置")
    print("=" * 100)
    print(
        f"selection_filter:    "
        f"{selection_filter}"
    )
    print(f"limit:               {args.limit}")
    print(f"worker_id:           {worker_id}")
    print(
        f"ocr_base_url:        "
        f"{service_config.base_url}"
    )
    print(
        f"ocr_model:           "
        f"{service_config.model_name}"
    )
    print(
        f"render_dpi:          "
        f"{args.render_dpi}"
    )
    print(
        f"page_workers:        "
        f"{args.page_workers}"
    )
    print(
        f"max_tokens:          "
        f"{args.max_tokens}"
    )
    print(
        f"temperature:         "
        f"{args.temperature}"
    )
    print(
        f"lease_seconds:       "
        f"{args.lease_seconds}"
    )
    print(
        f"max_attempts:        "
        f"{args.max_attempts}"
    )
    print(
        f"retry_delay_seconds: "
        f"{args.retry_delay_seconds}"
    )
    print("=" * 100)

    summary = run_document_parse_tasks(
        worker_id=worker_id,
        selection_filter=selection_filter,
        limit=args.limit,
        parser=document_parser,
        parser_options={
            "render_dpi": args.render_dpi,
            "max_page_workers": (
                args.page_workers
            ),
            "max_tokens": args.max_tokens,
            "temperature": args.temperature,
        },
        lease_seconds=args.lease_seconds,
        max_attempts=args.max_attempts,
        retry_delay_seconds=(
            args.retry_delay_seconds
        ),
    )

    print("=" * 100)
    print("文档解析任务执行完成")
    print("=" * 100)
    print(f"领取任务数:      {summary.claimed}")
    print(f"解析成功:        {summary.success}")
    print(f"解析失败:        {summary.failed}")
    print(
        f"任务所有权丢失:  "
        f"{summary.ownership_lost}"
    )
    print(f"其他状态:        {summary.other}")
    print("=" * 100)

    if summary.claimed == 0:
        print(
            "没有符合条件的可领取文档任务。"
        )


if __name__ == "__main__":
    main()
