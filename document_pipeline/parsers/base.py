"""
文档解析器统一接口。

本模块只定义所有解析器共同遵守的输入、输出和能力描述，
不包含 GLM-OCR、GROBID 等具体实现。

上层 Document Pipeline 只依赖这里定义的 DocumentParser，
不需要了解不同解析器内部如何调用模型、拆分页面或处理响应。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ParserCapabilities:
    """
    描述解析器能够产生或识别哪些内容。

    上层 Pipeline 应根据能力声明判断某种资产是否可用，
    不应直接通过 parser_name 判断解析器类型。
    """

    markdown: bool = False
    plain_text: bool = False
    layout: bool = False
    formulas: bool = False
    tables: bool = False
    page_coordinates: bool = False


@dataclass(frozen=True)
class ParseRequest:
    """
    一次文档解析任务的标准输入。

    parser_options 用于传递解析器特有配置。例如 GLM-OCR
    可能需要页面批量大小、提示词或超时时间，但这些配置不会
    暴露给其他解析器。
    """

    paper_id: str
    pdf_path: Path
    source_pdf_sha256: str
    output_directory: Path

    # 可选的论文元数据，可用于标题匹配和质量检查。
    title: str = ""

    # 解析器自己的可选参数。
    parser_options: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        normalized_paper_id = self.paper_id.strip()
        normalized_sha256 = self.source_pdf_sha256.strip()

        if not normalized_paper_id:
            raise ValueError("paper_id 不能为空")

        if "/" in normalized_paper_id or "\\" in normalized_paper_id:
            raise ValueError(
                "paper_id 中不能包含路径分隔符"
            )

        if not isinstance(self.pdf_path, Path):
            raise TypeError("pdf_path 必须是 pathlib.Path")

        if not isinstance(self.output_directory, Path):
            raise TypeError(
                "output_directory 必须是 pathlib.Path"
            )

        if not normalized_sha256:
            raise ValueError(
                "source_pdf_sha256 不能为空"
            )


@dataclass(frozen=True)
class ParseArtifacts:
    """
    解析器实际生成的资产路径。

    这些路径是当前机器上的绝对路径或工作目录路径，
    不直接写入 MongoDB。后续由 Document Pipeline 转换成
    相对于 AI4RESEARCH_DATA_ROOT 的相对路径。

    某个解析器不支持的资产保持为 None。
    """

    markdown_path: Path | None = None
    plain_text_path: Path | None = None
    layout_path: Path | None = None
    report_path: Path | None = None

    # 保存解析器未经统一转换的原始响应。
    # 它既可以是文件，也可以是一个目录。
    raw_output_path: Path | None = None


@dataclass(frozen=True)
class ParseResult:
    """
    一次解析调用的标准结果。

    success 只表示解析程序是否成功执行并产生结果，
    不代表文档质量一定合格。

    文档质量判断将在独立的 quality_checks 模块中完成。
    """

    success: bool

    parser_name: str
    parser_version: str
    capabilities: ParserCapabilities

    source_pdf_sha256: str
    artifacts: ParseArtifacts

    page_count: int = 0
    char_count: int = 0
    duration_seconds: float = 0.0

    warnings: tuple[str, ...] = ()
    error: str = ""

    # 用于保存解析器返回的其他统计信息。
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not self.parser_name.strip():
            raise ValueError("parser_name 不能为空")

        if not self.parser_version.strip():
            raise ValueError("parser_version 不能为空")

        if not self.source_pdf_sha256.strip():
            raise ValueError(
                "source_pdf_sha256 不能为空"
            )

        if self.page_count < 0:
            raise ValueError("page_count 不能小于 0")

        if self.char_count < 0:
            raise ValueError("char_count 不能小于 0")

        if self.duration_seconds < 0:
            raise ValueError(
                "duration_seconds 不能小于 0"
            )

        if self.success and self.error:
            raise ValueError(
                "解析成功时 error 应为空"
            )

        if not self.success and not self.error.strip():
            raise ValueError(
                "解析失败时必须提供 error"
            )


class DocumentParser(ABC):
    """
    所有文档解析器必须实现的统一抽象接口。

    上层 Pipeline 只调用：

        parser.parse(request)

    不关心解析器内部使用的是 GLM-OCR、GROBID，
    还是未来新增的其他模型。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """解析器的稳定名称，例如 glm-ocr。"""

        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        """
        解析器或模型版本。

        版本变化可能导致解析结果变化，因此必须记录。
        """

        raise NotImplementedError

    @property
    @abstractmethod
    def capabilities(self) -> ParserCapabilities:
        """返回解析器的能力声明。"""

        raise NotImplementedError

    @abstractmethod
    def parse(
        self,
        request: ParseRequest,
    ) -> ParseResult:
        """
        解析一篇 PDF，并返回统一的 ParseResult。

        具体解析器负责：
        1. 检查自身配置；
        2. 调用模型或服务；
        3. 将原始结果转换成标准资产；
        4. 捕获可预期的解析异常；
        5. 返回成功或失败结果。

        具体解析器不负责：
        1. MongoDB 任务领取和状态更新；
        2. 全局并发调度；
        3. 最终质量裁决；
        4. Chunk 切分和向量数据库写入。
        """

        raise NotImplementedError