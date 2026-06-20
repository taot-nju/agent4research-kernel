"""
单页 OCR 后端统一接口。

文档解析器负责拆分和组织 PDF；
OCR 后端只负责识别一张页面图片。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class OCRPageRequest:
    """一次单页 OCR 请求。"""

    paper_id: str
    page_index: int
    image_bytes: bytes
    mime_type: str = "image/png"
    prompt: str = ""
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not self.paper_id.strip():
            raise ValueError("paper_id 不能为空")

        if self.page_index < 0:
            raise ValueError("page_index 不能小于 0")

        if not isinstance(self.image_bytes, bytes):
            raise TypeError("image_bytes 必须是 bytes")

        if not self.image_bytes:
            raise ValueError("image_bytes 不能为空")

        if not self.mime_type.strip():
            raise ValueError("mime_type 不能为空")

    @property
    def page_number(self) -> int:
        """返回从 1 开始的页码。"""

        return self.page_index + 1


@dataclass(frozen=True)
class OCRPageResult:
    """一次单页 OCR 的标准结果。"""

    success: bool
    page_index: int
    text: str = ""
    duration_seconds: float = 0.0
    error: str = ""
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if self.page_index < 0:
            raise ValueError("page_index 不能小于 0")

        if self.duration_seconds < 0:
            raise ValueError(
                "duration_seconds 不能小于 0"
            )

        if self.success and self.error:
            raise ValueError(
                "OCR 成功时 error 应为空"
            )

        if not self.success and not self.error.strip():
            raise ValueError(
                "OCR 失败时必须提供 error"
            )

    @property
    def page_number(self) -> int:
        """返回从 1 开始的页码。"""

        return self.page_index + 1


class PageOCRBackend(ABC):
    """所有单页 OCR 后端必须实现的接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """后端稳定名称。"""

        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        """后端或模型版本。"""

        raise NotImplementedError


    @abstractmethod
    def check_health(self) -> None:
        """
        检查后端是否可用。

        正常时直接返回；不可用时抛出异常。
        """

        raise NotImplementedError


    @abstractmethod
    def recognize(
        self,
        request: OCRPageRequest,
    ) -> OCRPageResult:
        """识别一张页面图片。"""

        raise NotImplementedError