"""
OpenAI-compatible 单页 OCR 后端。

当前用于本地 vLLM 部署的 GLM-OCR，也可以通过配置切换到
其他兼容 OpenAI Chat Completions 协议的服务。
"""

import base64
import threading
from time import perf_counter
from typing import Any

from openai import OpenAI

from ai4research.document_pipeline.config import (
    OCRServiceConfig,
    load_ocr_service_config,
)
from ai4research.document_pipeline.ocr_backends.base import (
    OCRPageRequest,
    OCRPageResult,
    PageOCRBackend,
)


DEFAULT_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_RETRIES = 2

DEFAULT_OCR_PROMPT = """请对该文档页面进行 OCR 识别，并输出结构化内容：
- 保持原有段落结构
- 表格使用 Markdown 格式
- 数学公式转换为 LaTeX
- 不要遗漏页面中的内容
- 不要添加原文中不存在的解释
"""


class OpenAICompatibleOCRBackend(PageOCRBackend):
    """通过 OpenAI-compatible API 执行单页 OCR。"""

    def __init__(
        self,
        config: OCRServiceConfig | None = None,
    ) -> None:
        self._config = (
            config or load_ocr_service_config()
        )
        self._thread_local = threading.local()

    @property
    def name(self) -> str:
        return "openai-compatible-ocr"

    @property
    def version(self) -> str:
        return self._config.model_name

    @property
    def config(self) -> OCRServiceConfig:
        """返回当前服务配置。"""

        return self._config

    def check_health(self) -> None:
        """确认 OCR 服务在线且目标模型可用。"""

        try:
            response = (
                self._get_client()
                .models.list()
            )
        except Exception as error:
            raise RuntimeError(
                "OCR 服务健康检查失败："
                f"{type(error).__name__}: {error}"
            ) from error

        available_models = {
            str(model.id)
            for model in response.data
        }

        if self._config.model_name not in available_models:
            raise RuntimeError(
                "OCR 服务未加载目标模型："
                f"{self._config.model_name}; "
                "available="
                f"{sorted(available_models)}"
            )


    def _get_client(self) -> OpenAI:
        """
        为当前线程创建并复用独立客户端。

        这样既能复用 HTTP 连接，也避免多个页面线程共享
        同一个客户端实例。
        """

        client = getattr(
            self._thread_local,
            "openai_client",
            None,
        )

        if client is None:
            client = OpenAI(
                base_url=self._config.base_url,
                api_key=self._config.api_key,
                timeout=self._config.timeout_seconds,
                max_retries=DEFAULT_MAX_RETRIES,
            )
            self._thread_local.openai_client = client

        return client

    @staticmethod
    def _read_max_tokens(
        metadata: Any,
    ) -> int:
        """读取并验证单页最大输出 token 数。"""

        raw_value = metadata.get(
            "max_tokens",
            DEFAULT_MAX_TOKENS,
        )

        try:
            value = int(raw_value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "max_tokens 必须是整数"
            ) from error

        if value <= 0:
            raise ValueError(
                "max_tokens 必须大于 0"
            )

        return value

    @staticmethod
    def _read_temperature(
        metadata: Any,
    ) -> float:
        """读取并验证采样温度。"""

        raw_value = metadata.get(
            "temperature",
            DEFAULT_TEMPERATURE,
        )

        try:
            value = float(raw_value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "temperature 必须是数字"
            ) from error

        if value < 0:
            raise ValueError(
                "temperature 不能小于 0"
            )

        return value

    def recognize(
        self,
        request: OCRPageRequest,
    ) -> OCRPageResult:
        """识别一张页面图片并返回标准结果。"""

        started_at = perf_counter()

        try:
            encoded_image = base64.b64encode(
                request.image_bytes
            ).decode("ascii")

            image_data_url = (
                f"data:{request.mime_type};base64,"
                f"{encoded_image}"
            )

            prompt = (
                request.prompt.strip()
                or DEFAULT_OCR_PROMPT
            )

            response = (
                self._get_client()
                .chat.completions.create(
                    model=self._config.model_name,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": prompt,
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": image_data_url,
                                    },
                                },
                            ],
                        }
                    ],
                    max_tokens=self._read_max_tokens(
                        request.metadata
                    ),
                    temperature=self._read_temperature(
                        request.metadata
                    ),
                )
            )

            if not response.choices:
                raise RuntimeError(
                    "OCR 服务没有返回 choices"
                )

            choice = response.choices[0]
            content = choice.message.content

            if content is None:
                raise RuntimeError(
                    "OCR 服务返回的 content 为空"
                )

            metadata: dict[str, Any] = {
                "backend": self.name,
                "model": (
                    response.model
                    or self._config.model_name
                ),
                "response_id": response.id or "",
                "finish_reason": (
                    choice.finish_reason or ""
                ),
            }

            if response.usage is not None:
                metadata.update({
                    "prompt_tokens": (
                        response.usage.prompt_tokens
                    ),
                    "completion_tokens": (
                        response.usage.completion_tokens
                    ),
                    "total_tokens": (
                        response.usage.total_tokens
                    ),
                })

            return OCRPageResult(
                success=True,
                page_index=request.page_index,
                text=str(content),
                duration_seconds=(
                    perf_counter() - started_at
                ),
                metadata=metadata,
            )

        except Exception as error:
            error_message = (
                f"{type(error).__name__}: {error}"
            )[:4000]

            return OCRPageResult(
                success=False,
                page_index=request.page_index,
                duration_seconds=(
                    perf_counter() - started_at
                ),
                error=error_message,
                metadata={
                    "backend": self.name,
                    "model": self._config.model_name,
                },
            )