"""
会议通用的配置项，包含会议名称、下载链接模板、可用年份等信息。
每个会议的配置项结构相似，但可能包含特定于该会议的字段，例如 ACL 的类别信息。
"""

# Update date: 2026-06-08 19:49:57


# NeurIPS在OpenReview上有挂载信息，但是2026年的还没有放榜
NEURIPS = {
    "venue": "NeurIPS",
    "base_url_template": "https://neurips.cc/Downloads/{year}",  # https://neurips.cc/Downloads
    "available_years": list(range(2022, 2026))  # 2022, 2023, 2024, 2025; 2026年的还没有放榜
}


# ICLR在OpenReview上有挂载信息，2026年的也已经放榜
ICLR = {
    "venue": "ICLR",
    "base_url_template": "https://iclr.cc/Downloads/{year}",  # https://iclr.cc/Downloads
    "available_years": list(range(2022, 2026))  # 2022, 2023, 2024, 2025; 2026年：主页没有，OpenReview有pdf
}


# ICML在OpenReview上有挂载信息，但是2026年的还没有放榜
ICML = {
    "venue": "ICML",
    "base_url_template": "https://icml.cc/Downloads/{year}",  # https://icml.cc/Downloads
    "available_years": list(range(2022, 2027)),  # 2022, 2023, 2024, 2025; 2026年：主页有简单信息，OpenReview暂时没有
    "source_note": "ICML 2026 official Downloads page is used before OpenReview/PMLR proceedings become available.",
}


# ACL 在OpenReview上没有挂载，需要从ACL官网爬取，因此配置项不同于其他会议
ACL = {
    "venue": "ACL",
    "base_url_template": "https://aclanthology.org/events/acl-{year}",  # https://aclanthology.org/events/acl-2021
    "categories": ["long", "short", "findings"],     # 未来可扩展更多类别    
    "category_anchor_id": "{year}acl-{cat_key}",  # 用于定位每类论文 div 的 id
    "available_years": list(range(2022, 2026))  # 2022, 2023, 2024, 2025; 2026年的还没有放榜
}


CONFERENCES = {
    "NeurIPS": NEURIPS,
    "ICLR": ICLR,
    "ICML": ICML,
    "ACL": ACL,
}
