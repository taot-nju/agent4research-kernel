"""
AAAI 官方 Proceedings 数据源配置。

默认只爬取：
1. AAAI Main Technical Tracks
2. AAAI Special Tracks

默认排除：
IAAI、EAAI、Journal Track、Student Abstracts、Doctoral Consortium、
Undergraduate Consortium、Demonstrations、Senior Member Presentations、
New Faculty Highlights 等非 AAAI 主会正式研究论文类别。
"""


AAAI_YEARS = {
    2026: {
        "venue": "AAAI",
        "year": 2026,
        "conference_number": 40,
        "proceedings_url": "https://aaai.org/proceeding/aaai-40-2026/",
    },
    2025: {
        "venue": "AAAI",
        "year": 2025,
        "conference_number": 39,
        "proceedings_url": "https://aaai.org/proceeding/aaai-39-2025/",
    },
    2024: {
        "venue": "AAAI",
        "year": 2024,
        "conference_number": 38,
        "proceedings_url": "https://aaai.org/proceeding/aaai-38-2024/",
    },
    2023: {
        "venue": "AAAI",
        "year": 2023,
        "conference_number": 37,
        "proceedings_url": "https://aaai.org/proceeding/aaai-37-2023/",
    },
    2022: {
        "venue": "AAAI",
        "year": 2022,
        "conference_number": 36,
        "proceedings_url": "https://aaai.org/proceeding/aaai-36-2022/",
    },
}


INCLUDE_ISSUE_KEYWORDS = [
    "Technical Tracks",
    "Technical Track",
    "Special Track",
    "Special Tracks",
]


EXCLUDE_ISSUE_KEYWORDS = [
    "IAAI",
    "EAAI",
    "Journal Track",
    "Student Abstract",
    "Doctoral Consortium",
    "Undergraduate Consortium",
    "Demonstration",
    "Senior Member",
    "New Faculty Highlights",
    "Emerging Trends",
]