"""
文档解析服务配置。

当前默认连接本机部署的 OpenAI-compatible OCR 服务。
服务地址、模型和凭据均可通过环境变量替换，业务代码不应硬编码。
"""

import os
from dataclasses import dataclass


OCR_BASE_URL_ENV = "AI4RESEARCH_OCR_BASE_URL"
OCR_API_KEY_ENV = "AI4RESEARCH_OCR_API_KEY"
OCR_MODEL_ENV = "AI4RESEARCH_OCR_MODEL"
OCR_TIMEOUT_ENV = "AI4RESEARCH_OCR_TIMEOUT_SECONDS"

DEFAULT_OCR_BASE_URL = "http://127.0.0.1:9000/v1"
DEFAULT_OCR_API_KEY = "EMPTY"
DEFAULT_OCR_MODEL = "glm-ocr"
DEFAULT_OCR_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class OCRServiceConfig:
    """OpenAI-compatible OCR 服务连接配置。"""

    base_url: str
    api_key: str
    model_name: str
    timeout_seconds: int

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("OCR base_url 不能为空")

        if not self.api_key.strip():
            raise ValueError("OCR api_key 不能为空")

        if not self.model_name.strip():
            raise ValueError("OCR model_name 不能为空")

        if self.timeout_seconds <= 0:
            raise ValueError(
                "OCR timeout_seconds 必须大于 0"
            )


def _read_positive_int(
    environment_name: str,
    default: int,
) -> int:
    """读取正整数环境变量。"""

    raw_value = os.getenv(environment_name)

    if raw_value is None or not raw_value.strip():
        return default

    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(
            f"{environment_name} 必须是整数"
        ) from error

    if value <= 0:
        raise ValueError(
            f"{environment_name} 必须大于 0"
        )

    return value


def load_ocr_service_config() -> OCRServiceConfig:
    """从环境变量读取 OCR 服务配置。"""

    return OCRServiceConfig(
        base_url=os.getenv(
            OCR_BASE_URL_ENV,
            DEFAULT_OCR_BASE_URL,
        ).strip().rstrip("/"),
        api_key=os.getenv(
            OCR_API_KEY_ENV,
            DEFAULT_OCR_API_KEY,
        ).strip(),
        model_name=os.getenv(
            OCR_MODEL_ENV,
            DEFAULT_OCR_MODEL,
        ).strip(),
        timeout_seconds=_read_positive_int(
            OCR_TIMEOUT_ENV,
            DEFAULT_OCR_TIMEOUT_SECONDS,
        ),
    )