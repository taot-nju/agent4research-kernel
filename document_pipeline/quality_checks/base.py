"""
文档质量检查统一接口。

解析成功只表示程序正常生成资产；
质量检查负责判断资产是否适合进入后续检索和分析流程。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


QUALITY_STATUSES = {
    "passed",
    "warning",
    "rejected",
}


@dataclass(frozen=True)
class DocumentQualityRequest:
    """一次文档质量检查的标准输入。"""

    paper_id: str
    title: str
    markdown_path: Path
    report_path: Path | None
    page_count: int
    char_count: int

    def __post_init__(self) -> None:
        if not self.paper_id.strip():
            raise ValueError(
                "paper_id 不能为空"
            )

        if not isinstance(
            self.markdown_path,
            Path,
        ):
            raise TypeError(
                "markdown_path 必须是 pathlib.Path"
            )

        if (
            self.report_path is not None
            and not isinstance(
                self.report_path,
                Path,
            )
        ):
            raise TypeError(
                "report_path 必须是 pathlib.Path 或 None"
            )

        if self.page_count < 0:
            raise ValueError(
                "page_count 不能小于 0"
            )

        if self.char_count < 0:
            raise ValueError(
                "char_count 不能小于 0"
            )


@dataclass(frozen=True)
class QualityCheckResult:
    """一项独立质量规则的检查结果。"""

    name: str
    passed: bool
    score: float
    weight: float = 1.0
    critical: bool = False
    message: str = ""
    details: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError(
                "质量检查名称不能为空"
            )

        if not 0.0 <= self.score <= 1.0:
            raise ValueError(
                "质量检查 score 必须在 0 到 1 之间"
            )

        if self.weight <= 0:
            raise ValueError(
                "质量检查 weight 必须大于 0"
            )


@dataclass(frozen=True)
class DocumentQualityResult:
    """一篇文档的综合质量结果。"""

    status: str
    score: float
    checks: tuple[QualityCheckResult, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in QUALITY_STATUSES:
            raise ValueError(
                f"不支持的质量状态：{self.status}"
            )

        if not 0.0 <= self.score <= 1.0:
            raise ValueError(
                "综合质量 score 必须在 0 到 1 之间"
            )


class DocumentQualityChecker(ABC):
    """所有文档质量检查器必须实现的接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """质量检查器稳定名称。"""

        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        """质量规则版本。"""

        raise NotImplementedError

    @abstractmethod
    def check(
        self,
        request: DocumentQualityRequest,
    ) -> DocumentQualityResult:
        """执行质量检查。"""

        raise NotImplementedError
