"""
全文资产路径生成工具。

MongoDB 中只保存相对于 AI4RESEARCH_DATA_ROOT 的相对路径，例如：

    pdf/98/0f/980fb775eaf76edc01e7469ade0b1e190785989a.pdf

实际绝对路径由 AI4RESEARCH_DATA_ROOT 与相对路径拼接得到。
这样将资产迁移到另一台机器时，不需要逐条修改数据库路径。
"""

from pathlib import Path

from ai4research.fulltext_pipeline.config import get_data_root


def validate_paper_id(paper_id: str) -> str:
    """
    检查并标准化论文 ID。

    当前论文 _id 通常是长度为 40 的 SHA1 字符串。
    此处不强制限定长度，只检查基本路径安全性。
    """

    if not isinstance(paper_id, str):
        raise TypeError("paper_id 必须是字符串")

    normalized_id = paper_id.strip()

    if not normalized_id:
        raise ValueError("paper_id 不能为空")

    if "/" in normalized_id or "\\" in normalized_id:
        raise ValueError("paper_id 中不能包含路径分隔符")

    return normalized_id


def build_asset_relative_path(
    paper_id: str,
    asset_type: str,
    extension: str,
) -> Path:
    """
    根据论文 ID 生成资产相对路径。

    使用论文 ID 的前四个字符进行两级分目录，避免把数万文件
    全部放在同一个目录中。

    示例：

        paper_id = 980fb775...
        asset_type = pdf
        extension = pdf

    返回：

        pdf/98/0f/980fb775....pdf
    """

    normalized_id = validate_paper_id(paper_id)

    normalized_asset_type = asset_type.strip().lower()
    normalized_extension = extension.strip().lower().lstrip(".")

    if not normalized_asset_type:
        raise ValueError("asset_type 不能为空")

    if not normalized_extension:
        raise ValueError("extension 不能为空")

    first_level = normalized_id[:2]
    second_level = normalized_id[2:4]

    return (
        Path(normalized_asset_type)
        / first_level
        / second_level
        / f"{normalized_id}.{normalized_extension}"
    )


def get_pdf_relative_path(paper_id: str) -> Path:
    """返回论文 PDF 的相对路径。"""

    return build_asset_relative_path(
        paper_id=paper_id,
        asset_type="pdf",
        extension="pdf",
    )


def get_txt_relative_path(paper_id: str) -> Path:
    """返回论文 TXT 的相对路径。"""

    return build_asset_relative_path(
        paper_id=paper_id,
        asset_type="txt",
        extension="txt",
    )


def get_structured_relative_path(paper_id: str) -> Path:
    """返回论文结构化 JSON 的相对路径。"""

    return build_asset_relative_path(
        paper_id=paper_id,
        asset_type="structured",
        extension="json",
    )


def resolve_asset_path(relative_path: str | Path) -> Path:
    """
    将数据库中的资产相对路径转换为当前机器上的绝对路径。
    """

    path = Path(relative_path)

    if path.is_absolute():
        raise ValueError("数据库中应保存相对路径，不能传入绝对路径")

    return get_data_root() / path


def ensure_parent_directory(file_path: str | Path) -> None:
    """
    创建目标文件的父目录。

    例如下载一篇 PDF 前，将自动创建：

        /data/ai4research_assets/pdf/98/0f/
    """

    Path(file_path).parent.mkdir(parents=True, exist_ok=True)