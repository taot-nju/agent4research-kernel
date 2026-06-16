"""
按条件下载论文 PDF。

支持：
1. 下载指定 paper_id；
2. 下载指定 accepted_by，例如 ICLR 2022；
3. 明确选择全部待处理论文；
4. 使用 --limit 控制本次最多处理数量；
5. 自动跳过已经 success 的论文；
6. 继续处理 pending、可重试 failed 和租约过期的 running 任务。

运行示例：

# 下载一篇指定论文
python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --paper-id af32138f7c04e15f3d021a8008bbc64b66f1ba23

# 下载 ICLR 2022 中最多 10 篇
python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --accepted-by "ICLR 2022" \
  --limit 10

# 从所有待处理论文中最多处理 100 篇
python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --all \
  --limit 100

# 下载 Query 召回得到的一批候选论文
python -m ai4research.fulltext_pipeline.scripts_py.download_pdfs \
  --ids-file candidate_paper_ids.txt \
  --limit 100 \
  --workers 8
"""

import argparse
import os
import socket
from typing import Any
from pathlib import Path

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.fulltext_pipeline.pipelines.pdf_download_runner import (
    run_pdf_download_tasks,
)
from ai4research.fulltext_pipeline.pipelines.concurrent_pdf_download_runner import (
    run_concurrent_pdf_download_tasks,
)
from ai4research.fulltext_pipeline.repositories.pdf_task_repository import (
    DEFAULT_LEASE_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
)


DEFAULT_LIMIT = 1
DEFAULT_RETRY_DELAY_SECONDS = 60
DEFAULT_WORKERS = 1

def build_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""

    parser = argparse.ArgumentParser(
        description=(
            "按 paper_id、accepted_by 或全局范围，"
            "下载尚未完成的论文 PDF。"
        )
    )

    selection_group = parser.add_mutually_exclusive_group(
        required=True
    )

    selection_group.add_argument(
        "--paper-id",
        type=str,
        help="只处理指定 MongoDB 论文 _id。",
    )

    selection_group.add_argument(
        "--ids-file",
        type=str,
        help=(
            "从文本文件读取多个论文 _id。"
            "每行一个 paper_id，空行和以 # 开头的注释行会被忽略。"
        ),
    )

    selection_group.add_argument(
        "--accepted-by",
        type=str,
        help='只处理指定会议，例如 "ICLR 2022"。',
    )

    selection_group.add_argument(
        "--all",
        action="store_true",
        help=(
            "允许从所有论文中领取任务。"
            "仍然受到 --limit 限制，不会无限处理。"
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=(
            "本次最多处理的论文数量，"
            f"默认值为 {DEFAULT_LIMIT}。"
        ),
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=(
            "全局下载线程数。"
            "1 表示顺序执行，大于 1 时启用并发下载；"
            f"默认值为 {DEFAULT_WORKERS}。"
            "每个域名仍受独立限速策略约束。"
        ),
    )

    parser.add_argument(
        "--lease-seconds",
        type=int,
        default=DEFAULT_LEASE_SECONDS,
        help=(
            "每条任务的租约时长，单位为秒。"
            f"默认值为 {DEFAULT_LEASE_SECONDS}。"
        ),
    )

    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help=(
            "每篇论文允许被领取的最大次数，"
            f"默认值为 {DEFAULT_MAX_ATTEMPTS}。"
        ),
    )

    parser.add_argument(
        "--retry-delay-seconds",
        type=int,
        default=DEFAULT_RETRY_DELAY_SECONDS,
        help=(
            "下载失败后，再次允许领取前的等待时间，"
            f"默认值为 {DEFAULT_RETRY_DELAY_SECONDS} 秒。"
        ),
    )

    parser.add_argument(
        "--worker-id",
        type=str,
        default="",
        help=(
            "可选的 Worker 标识。"
            "如果不提供，则自动使用 hostname、进程 ID 生成。"
        ),
    )

    return parser


def build_selection_filter(
    args: argparse.Namespace,
) -> dict[str, Any]:
    """根据命令行参数构造 MongoDB 业务筛选条件。"""

    if args.paper_id:
        paper_id = args.paper_id.strip()

        if not paper_id:
            raise ValueError("--paper-id 不能为空")

        return {
            "_id": paper_id,
        }

    if args.ids_file:
        paper_ids = load_paper_ids(args.ids_file)

        return {
            "_id": {
                "$in": paper_ids,
            }
        }

    if args.accepted_by:
        accepted_by = args.accepted_by.strip()

        if not accepted_by:
            raise ValueError("--accepted-by 不能为空")

        return {
            "accepted_by": accepted_by,
        }

    if args.all:
        return {}

    raise ValueError(
        "必须指定 --paper-id、--ids-file、"
        "--accepted-by 或 --all"
    )


def load_paper_ids(ids_file: str) -> list[str]:
    """
    从文本文件读取论文 ID。

    文件格式示例：

        # Agent Memory 候选论文
        paper_id_1
        paper_id_2
        paper_id_3

    会忽略空行、注释行和重复 ID，并保持原始顺序。
    """

    file_path = Path(ids_file).expanduser().resolve()

    if not file_path.exists():
        raise FileNotFoundError(
            f"paper ID 文件不存在：{file_path}"
        )

    if not file_path.is_file():
        raise ValueError(
            f"paper ID 路径不是普通文件：{file_path}"
        )

    paper_ids: list[str] = []
    seen_ids: set[str] = set()

    with file_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line_number, raw_line in enumerate(
            file,
            start=1,
        ):
            paper_id = raw_line.strip()

            if not paper_id:
                continue

            if paper_id.startswith("#"):
                continue

            if "/" in paper_id or "\\" in paper_id:
                raise ValueError(
                    f"第 {line_number} 行包含非法 paper_id："
                    f"{paper_id}"
                )

            if paper_id in seen_ids:
                continue

            seen_ids.add(paper_id)
            paper_ids.append(paper_id)

    if not paper_ids:
        raise ValueError(
            f"文件中没有有效的 paper_id：{file_path}"
        )

    return paper_ids


def build_worker_id(
    configured_worker_id: str,
) -> str:
    """返回显式配置或自动生成的 Worker ID。"""

    normalized_worker_id = configured_worker_id.strip()

    if normalized_worker_id:
        return normalized_worker_id

    hostname = socket.gethostname()
    process_id = os.getpid()

    return f"{hostname}-pid-{process_id}"


def validate_arguments(args: argparse.Namespace) -> None:
    """检查数值参数是否合法。"""

    if args.limit <= 0:
        raise ValueError("--limit 必须大于 0")

    if args.workers <= 0:
        raise ValueError("--workers 必须大于 0")

    if args.lease_seconds <= 0:
        raise ValueError("--lease-seconds 必须大于 0")

    if args.max_attempts <= 0:
        raise ValueError("--max-attempts 必须大于 0")

    if args.retry_delay_seconds < 0:
        raise ValueError(
            "--retry-delay-seconds 不能小于 0"
        )


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    validate_arguments(args)

    selection_filter = build_selection_filter(args)
    worker_id = build_worker_id(args.worker_id)

    MongoDBClient.ping()

    print("✅ MongoDB connected successfully.")
    print("=" * 100)
    print("PDF 下载任务配置")
    print("=" * 100)
    print(f"selection_filter:    {selection_filter}")
    print(f"limit:               {args.limit}")
    print(f"worker_id:           {worker_id}")
    print(f"workers:             {args.workers}")
    print(f"lease_seconds:       {args.lease_seconds}")
    print(f"max_attempts:        {args.max_attempts}")
    print(
        f"retry_delay_seconds: "
        f"{args.retry_delay_seconds}"
    )
    print("=" * 100)

    # summary = run_pdf_download_tasks(
    #     worker_id=worker_id,
    #     selection_filter=selection_filter,
    #     limit=args.limit,
    #     lease_seconds=args.lease_seconds,
    #     max_attempts=args.max_attempts,
    #     retry_delay_seconds=args.retry_delay_seconds,
    # )
    if args.workers == 1:
        print("execution_mode:      sequential")

        summary = run_pdf_download_tasks(
            worker_id=worker_id,
            selection_filter=selection_filter,
            limit=args.limit,
            lease_seconds=args.lease_seconds,
            max_attempts=args.max_attempts,
            retry_delay_seconds=args.retry_delay_seconds,
        )
    else:
        print("execution_mode:      concurrent")

        summary = run_concurrent_pdf_download_tasks(
            worker_id_prefix=worker_id,
            selection_filter=selection_filter,
            limit=args.limit,
            max_workers=args.workers,
            lease_seconds=args.lease_seconds,
            max_attempts=args.max_attempts,
            retry_delay_seconds=args.retry_delay_seconds,
        )

    print("=" * 100)
    print("PDF 下载任务执行完成")
    print("=" * 100)
    print(f"领取任务数:          {summary.claimed}")
    print(f"下载成功:            {summary.success}")
    print(f"下载失败:            {summary.failed}")
    print(f"暂无 PDF URL:        {summary.unavailable}")
    print(f"任务所有权丢失:      {summary.ownership_lost}")
    print(f"其他状态:            {summary.other}")

    if hasattr(summary, "completed"):
        print(f"已完成任务数:        {summary.completed}")

    if hasattr(summary, "worker_exception"):
        print(f"Worker 内部异常:     {summary.worker_exception}")

    print("=" * 100)

    if summary.claimed == 0:
        print(
            "没有符合条件的可领取任务。"
            "可能已经下载成功、达到最大尝试次数，"
            "或仍处于有效租约中。"
        )


if __name__ == "__main__":
    main()
