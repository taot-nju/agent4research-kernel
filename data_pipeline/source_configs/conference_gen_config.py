"""
会议通用的配置项，包含会议名称、下载链接模板、可用年份等信息。
每个会议的配置项结构相似，但可能包含特定于该会议的字段，例如 ACL 的类别信息。
"""


NEURIPS = {
    "venue": "NeurIPS",
    "base_url_template": "https://neurips.cc/Downloads/{year}",
    "available_years": list(range(2021, 2026))  # 可继续扩
}

ICLR = {
    "venue": "ICLR",
    "base_url_template": "https://iclr.cc/Downloads/{year}",
    "available_years": list(range(2022, 2026))
}

ICML = {
    "venue": "ICML",
    "base_url_template": "https://icml.cc/Downloads/{year}",
    "available_years": list(range(2022, 2026))
}

ACL = {
    "venue": "ACL",
    "base_url_template": "https://aclanthology.org/events/acl-{year}",
    "categories": ["long", "short", "findings"],     # 未来可扩展更多类别    
    "category_anchor_id": "{year}acl-{cat_key}",  # 用于定位每类论文 div 的 id
    "available_years": list(range(2021, 2026))  # 现在先抓 2021~2025
}


CONFERENCES = {
    "NeurIPS": NEURIPS,
    "ICLR": ICLR,
    "ICML": ICML,
    "ACL": ACL,
}
