"""
全文资产存储配置。

PDF、TXT 等大文件不放在 Git 项目目录中，而是统一存放在
AI4RESEARCH_DATA_ROOT 指定的数据目录下。

例如：

export AI4RESEARCH_DATA_ROOT=/data/ai4research_assets

如果没有设置该环境变量，则默认使用：

~/ai4research_assets
"""

import os
from pathlib import Path


# 环境变量名称。
DATA_ROOT_ENV_NAME = "AI4RESEARCH_DATA_ROOT"


def get_data_root() -> Path:
    """
    返回全文资产的根目录。

    优先读取环境变量 AI4RESEARCH_DATA_ROOT；
    如果没有配置，则默认使用当前用户家目录下的：

        ~/ai4research_assets
    """

    configured_root = os.getenv(DATA_ROOT_ENV_NAME)

    if configured_root:
        return Path(configured_root).expanduser().resolve()

    return (Path.home() / "ai4research_assets").resolve()


def get_pdf_root() -> Path:
    """返回 PDF 文件的存储根目录。"""

    return get_data_root() / "pdf"


def get_txt_root() -> Path:
    """返回 TXT 文件的存储根目录。"""

    return get_data_root() / "txt"


def get_structured_root() -> Path:
    """返回结构化解析结果的存储根目录。"""

    return get_data_root() / "structured"


def get_temp_root() -> Path:
    """
    返回临时文件目录。

    PDF 下载过程中会先写入 .part 临时文件，
    校验成功后再原子重命名为正式 PDF。
    """

    return get_data_root() / "temp"


def ensure_asset_directories() -> None:
    """
    创建全文处理阶段需要使用的基础目录。

    exist_ok=True 保证该函数可以重复执行。
    """

    directories = [
        get_pdf_root(),
        get_txt_root(),
        get_structured_root(),
        get_temp_root(),
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
