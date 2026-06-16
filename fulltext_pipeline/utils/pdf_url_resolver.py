"""
论文 PDF 候选地址解析器。

一篇论文可能同时具有会议正式版、OpenReview 版本和 arXiv 版本。
本模块负责：

1. 从不同来源字段中读取 PDF URL；
2. 按“会议正式版优先，arXiv 兜底”的原则排序；
3. 去除重复 URL；
4. 为后续下载器提供统一入口；
5. 不修改 MongoDB 记录，也不执行网络请求。
"""

from typing import Any


# PDF 来源优先级：越靠前，优先级越高。
#
# 正式出版版本：
#   ACL Anthology、AAAI Official、PMLR
#
# 接收或投稿版本：
#   OpenReview
#
# 预印本兜底：
#   arXiv
#
# base_urls 中的字段主要用于兼容历史数据。
PDF_SOURCE_PRIORITY: tuple[dict[str, str], ...] = (
    {
        "source": "ACL Anthology",
        "field": "acl_anthology_obj.pdf_url",
    },
    {
        "source": "AAAI Official",
        "field": "aaai_obj.official_pdf_url",
    },
    {
        "source": "PMLR",
        "field": "base_urls.pmlr_pdf_url",
    },
    {
        "source": "OpenReview",
        "field": "openreview_obj.pdf_url",
    },
    {
        "source": "arXiv",
        "field": "arxiv_obj.arxiv_pdf_url",
    },

    # 历史字段或重复字段兜底。
    {
        "source": "ACL Anthology",
        "field": "base_urls.acl_anthology_pdf_url",
    },
    {
        "source": "Official",
        "field": "base_urls.official_pdf_url",
    },
    {
        "source": "OpenReview",
        "field": "base_urls.openreview_pdf_url",
    },
    {
        "source": "arXiv",
        "field": "base_urls.arxiv_pdf_url",
    },
)


def get_nested_value(
    data: dict[str, Any],
    field_path: str,
) -> Any:
    """
    根据点号分隔的字段路径读取嵌套字典中的值。

    示例：

        field_path = "acl_anthology_obj.pdf_url"

    相当于读取：

        data["acl_anthology_obj"]["pdf_url"]

    如果中间字段不存在或不是字典，则返回 None。
    """

    current: Any = data

    for key in field_path.split("."):
        if not isinstance(current, dict):
            return None

        current = current.get(key)

        if current is None:
            return None

    return current


def resolve_pdf_candidates(
    paper: dict[str, Any],
) -> list[dict[str, str]]:
    """
    返回一篇论文的全部有效 PDF 候选地址。

    返回顺序即下载尝试顺序。相同 URL 只保留第一次出现，
    也就是保留优先级更高的来源描述。

    返回示例：

        [
            {
                "source": "ACL Anthology",
                "field": "acl_anthology_obj.pdf_url",
                "url": "https://aclanthology.org/2025.acl-long.1.pdf",
            },
            {
                "source": "arXiv",
                "field": "arxiv_obj.arxiv_pdf_url",
                "url": "https://arxiv.org/pdf/2501.00001",
            },
        ]
    """

    candidates: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for source_config in PDF_SOURCE_PRIORITY:
        source = source_config["source"]
        field = source_config["field"]

        raw_value = get_nested_value(paper, field)

        if not isinstance(raw_value, str):
            continue

        url = raw_value.strip()

        if not url:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(url)

        candidates.append(
            {
                "source": source,
                "field": field,
                "url": url,
            }
        )

    return candidates


def resolve_preferred_pdf(
    paper: dict[str, Any],
) -> dict[str, str] | None:
    """
    返回优先级最高的 PDF 候选地址。

    如果该论文没有任何可用 PDF URL，则返回 None。
    """

    candidates = resolve_pdf_candidates(paper)

    if not candidates:
        return None

    return candidates[0]


def has_pdf_candidate(paper: dict[str, Any]) -> bool:
    """
    判断一篇论文是否至少具有一个可用 PDF URL。
    """

    return resolve_preferred_pdf(paper) is not None