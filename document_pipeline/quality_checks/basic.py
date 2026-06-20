"""
基础文档质量检查器。

当前检查：
1. Markdown 是否存在且非空；
2. 页数是否合法；
3. Markdown 页标记数是否与 PDF 页数一致；
4. 实际字符数是否与解析器报告基本一致；
5. 平均每页字符数是否过低；
6. 首页附近是否能匹配论文标题；
7. 解析报告是否完整且全部页面成功。
"""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from ai4research.data_pipeline.utils.text_utils import (
    normalize_title,
)
from ai4research.document_pipeline.quality_checks.base import (
    DocumentQualityChecker,
    DocumentQualityRequest,
    DocumentQualityResult,
    QualityCheckResult,
)


CHECKER_VERSION = "1"

PAGE_MARKER_PATTERN = re.compile(
    r"<!--\s*page:\s*\d+\s*-->"
)


class BasicDocumentQualityChecker(
    DocumentQualityChecker
):
    """第一版通用文档质量检查器。"""

    def __init__(
        self,
        *,
        min_average_chars_per_page: int = 100,
        expected_chars_per_page: int = 500,
        min_char_count_ratio: float = 0.95,
        min_title_similarity: float = 0.60,
    ) -> None:
        if min_average_chars_per_page < 0:
            raise ValueError(
                "min_average_chars_per_page "
                "不能小于 0"
            )

        if expected_chars_per_page <= 0:
            raise ValueError(
                "expected_chars_per_page "
                "必须大于 0"
            )

        if not 0.0 <= min_char_count_ratio <= 1.0:
            raise ValueError(
                "min_char_count_ratio "
                "必须在 0 到 1 之间"
            )

        if not 0.0 <= min_title_similarity <= 1.0:
            raise ValueError(
                "min_title_similarity "
                "必须在 0 到 1 之间"
            )

        self._min_average_chars_per_page = (
            min_average_chars_per_page
        )
        self._expected_chars_per_page = (
            expected_chars_per_page
        )
        self._min_char_count_ratio = (
            min_char_count_ratio
        )
        self._min_title_similarity = (
            min_title_similarity
        )

    @property
    def name(self) -> str:
        return "basic-document-quality"

    @property
    def version(self) -> str:
        return CHECKER_VERSION

    @staticmethod
    def _compute_char_count_ratio(
        reported_chars: int,
        actual_chars: int,
    ) -> float:
        """计算两个字符数的一致程度。"""

        larger = max(
            reported_chars,
            actual_chars,
        )

        if larger == 0:
            return 1.0

        return (
            min(
                reported_chars,
                actual_chars,
            )
            / larger
        )

    def _check_title(
        self,
        *,
        title: str,
        markdown: str,
    ) -> QualityCheckResult:
        """检查论文标题是否出现在文档开头。"""

        normalized_title = normalize_title(
            title
        )

        if not normalized_title:
            return QualityCheckResult(
                name="title_match",
                passed=True,
                score=1.0,
                weight=1.0,
                message=(
                    "数据库标题为空，跳过标题匹配"
                ),
                details={
                    "skipped": True,
                },
            )

        beginning = markdown[:5000]
        normalized_beginning = normalize_title(
            beginning
        )

        if normalized_title in normalized_beginning:
            similarity = 1.0
        else:
            candidate_lines = [
                normalize_title(line)
                for line in beginning.splitlines()
                if normalize_title(line)
            ]

            similarities = [
                SequenceMatcher(
                    None,
                    normalized_title,
                    candidate,
                ).ratio()
                for candidate in candidate_lines
            ]

            similarity = max(
                similarities,
                default=0.0,
            )

        passed = (
            similarity
            >= self._min_title_similarity
        )

        return QualityCheckResult(
            name="title_match",
            passed=passed,
            score=similarity,
            weight=1.5,
            critical=False,
            message=(
                ""
                if passed
                else "文档开头未可靠匹配论文标题"
            ),
            details={
                "similarity": similarity,
                "minimum": (
                    self._min_title_similarity
                ),
            },
        )

    @staticmethod
    def _check_report(
        *,
        report_path: Path | None,
        expected_page_count: int,
    ) -> QualityCheckResult:
        """检查解析报告及页面状态。"""

        if report_path is None:
            return QualityCheckResult(
                name="parse_report",
                passed=True,
                score=1.0,
                weight=1.0,
                message=(
                    "未提供解析报告，跳过检查"
                ),
                details={
                    "skipped": True,
                },
            )

        if not report_path.exists():
            return QualityCheckResult(
                name="parse_report",
                passed=False,
                score=0.0,
                weight=1.0,
                critical=True,
                message="解析报告文件不存在",
                details={
                    "path": str(report_path),
                },
            )

        try:
            report = json.loads(
                report_path.read_text(
                    encoding="utf-8"
                )
            )
        except Exception as error:
            return QualityCheckResult(
                name="parse_report",
                passed=False,
                score=0.0,
                weight=1.0,
                critical=True,
                message=(
                    "解析报告无法读取："
                    f"{type(error).__name__}: {error}"
                ),
                details={
                    "path": str(report_path),
                },
            )

        pages = report.get("pages", [])

        successful_pages = sum(
            bool(page.get("success"))
            for page in pages
            if isinstance(page, dict)
        )

        passed = (
            report.get("status") == "success"
            and report.get("page_count")
            == expected_page_count
            and len(pages)
            == expected_page_count
            and successful_pages
            == expected_page_count
        )

        score = (
            successful_pages
            / expected_page_count
            if expected_page_count > 0
            else 0.0
        )

        return QualityCheckResult(
            name="parse_report",
            passed=passed,
            score=min(1.0, score),
            weight=2.0,
            critical=True,
            message=(
                ""
                if passed
                else "解析报告页数或成功状态不一致"
            ),
            details={
                "report_status": report.get(
                    "status"
                ),
                "reported_page_count": (
                    report.get("page_count")
                ),
                "page_records": len(pages),
                "successful_pages": (
                    successful_pages
                ),
                "expected_page_count": (
                    expected_page_count
                ),
            },
        )

    def check(
        self,
        request: DocumentQualityRequest,
    ) -> DocumentQualityResult:
        """执行基础质量检查。"""

        markdown_path = request.markdown_path

        markdown_exists = (
            markdown_path.exists()
            and markdown_path.is_file()
        )

        checks = [
            QualityCheckResult(
                name="markdown_exists",
                passed=markdown_exists,
                score=(
                    1.0
                    if markdown_exists
                    else 0.0
                ),
                weight=2.0,
                critical=True,
                message=(
                    ""
                    if markdown_exists
                    else "Markdown 文件不存在"
                ),
                details={
                    "path": str(markdown_path),
                },
            )
        ]

        if not markdown_exists:
            return DocumentQualityResult(
                status="rejected",
                score=0.0,
                checks=tuple(checks),
                warnings=(
                    "Markdown 文件不存在",
                ),
            )

        try:
            markdown = markdown_path.read_text(
                encoding="utf-8"
            )
        except Exception as error:
            read_error = (
                "Markdown 无法读取："
                f"{type(error).__name__}: {error}"
            )

            checks.append(
                QualityCheckResult(
                    name="markdown_readable",
                    passed=False,
                    score=0.0,
                    weight=2.0,
                    critical=True,
                    message=read_error,
                )
            )

            return DocumentQualityResult(
                status="rejected",
                score=0.0,
                checks=tuple(checks),
                warnings=(read_error,),
            )

        marker_count = len(
            PAGE_MARKER_PATTERN.findall(
                markdown
            )
        )

        content_without_markers = (
            PAGE_MARKER_PATTERN.sub(
                "",
                markdown,
            ).strip()
        )
        actual_char_count = len(
            content_without_markers
        )

        page_count_valid = (
            request.page_count > 0
        )

        checks.append(
            QualityCheckResult(
                name="page_count_valid",
                passed=page_count_valid,
                score=(
                    1.0
                    if page_count_valid
                    else 0.0
                ),
                weight=2.0,
                critical=True,
                message=(
                    ""
                    if page_count_valid
                    else "文档页数必须大于 0"
                ),
                details={
                    "page_count": (
                        request.page_count
                    ),
                },
            )
        )

        markers_match = (
            page_count_valid
            and marker_count
            == request.page_count
        )

        checks.append(
            QualityCheckResult(
                name="page_markers_match",
                passed=markers_match,
                score=(
                    min(
                        marker_count
                        / request.page_count,
                        1.0,
                    )
                    if page_count_valid
                    else 0.0
                ),
                weight=2.0,
                critical=True,
                message=(
                    ""
                    if markers_match
                    else "Markdown 页标记数与页数不一致"
                ),
                details={
                    "marker_count": marker_count,
                    "page_count": (
                        request.page_count
                    ),
                },
            )
        )

        markdown_non_empty = (
            actual_char_count > 0
        )

        checks.append(
            QualityCheckResult(
                name="markdown_non_empty",
                passed=markdown_non_empty,
                score=(
                    1.0
                    if markdown_non_empty
                    else 0.0
                ),
                weight=2.0,
                critical=True,
                message=(
                    ""
                    if markdown_non_empty
                    else "Markdown 正文为空"
                ),
                details={
                    "actual_char_count": (
                        actual_char_count
                    ),
                },
            )
        )

        char_count_ratio = (
            self._compute_char_count_ratio(
                request.char_count,
                actual_char_count,
            )
        )
        char_count_consistent = (
            char_count_ratio
            >= self._min_char_count_ratio
        )

        checks.append(
            QualityCheckResult(
                name="char_count_consistency",
                passed=char_count_consistent,
                score=char_count_ratio,
                weight=1.0,
                critical=False,
                message=(
                    ""
                    if char_count_consistent
                    else "实际字符数与解析器记录差异较大"
                ),
                details={
                    "reported_char_count": (
                        request.char_count
                    ),
                    "actual_char_count": (
                        actual_char_count
                    ),
                    "ratio": char_count_ratio,
                    "minimum": (
                        self._min_char_count_ratio
                    ),
                },
            )
        )

        average_chars = (
            actual_char_count
            / request.page_count
            if page_count_valid
            else 0.0
        )
        average_chars_passed = (
            average_chars
            >= self._min_average_chars_per_page
        )

        checks.append(
            QualityCheckResult(
                name="average_chars_per_page",
                passed=average_chars_passed,
                score=min(
                    average_chars
                    / self._expected_chars_per_page,
                    1.0,
                ),
                weight=1.0,
                critical=False,
                message=(
                    ""
                    if average_chars_passed
                    else "平均每页字符数过低"
                ),
                details={
                    "average_chars_per_page": (
                        average_chars
                    ),
                    "minimum": (
                        self
                        ._min_average_chars_per_page
                    ),
                },
            )
        )

        checks.append(
            self._check_title(
                title=request.title,
                markdown=markdown,
            )
        )

        checks.append(
            self._check_report(
                report_path=request.report_path,
                expected_page_count=(
                    request.page_count
                ),
            )
        )

        total_weight = sum(
            check.weight
            for check in checks
        )
        weighted_score = sum(
            check.score * check.weight
            for check in checks
        ) / total_weight

        critical_failed = any(
            check.critical and not check.passed
            for check in checks
        )
        noncritical_failed = any(
            not check.critical
            and not check.passed
            for check in checks
        )

        if critical_failed:
            status = "rejected"
        elif (
            noncritical_failed
            or weighted_score < 0.80
        ):
            status = "warning"
        else:
            status = "passed"

        warnings = tuple(
            check.message
            for check in checks
            if not check.passed
            and check.message
        )

        return DocumentQualityResult(
            status=status,
            score=weighted_score,
            checks=tuple(checks),
            warnings=warnings,
        )