"""
OpenReview 数据源配置。

说明：
1. 如果某个会议年份在 OpenReview 上可以获取完整论文元数据，则优先使用 OpenReview；
2. 被 OpenReview 覆盖的 venue/year，后续会议官网爬虫应跳过；
3. 这里先只配置元信息，不写任何爬取逻辑。
"""

# Update date: 2026-06-08


OPENREVIEW_VENUES = {
    "ICLR": {
        "venue": "ICLR",
        "years": {
            2026: {
                "venue_id": "ICLR.cc/2026/Conference",
                "source": "OpenReview",
                "skip_official_site": True,
                "note": "ICLR 2026 homepage does not provide complete download page yet; use OpenReview as primary source.",
            },
        },
    },

    "ICML": {
        "venue": "ICML",
        "years": {
            # 2026 暂不配置，等放榜或 OpenReview 页面稳定后再补。
        },
    },

    "NeurIPS": {
        "venue": "NeurIPS",
        "years": {
            # 2026 暂不配置，等放榜或 OpenReview 页面稳定后再补。
        },
    },
}


def get_openreview_config(venue: str, year: int):
    """
    获取指定会议年份的 OpenReview 配置。

    如果该 venue/year 没有配置，则返回 None。
    """
    venue_config = OPENREVIEW_VENUES.get(venue)
    if not venue_config:
        return None

    return venue_config.get("years", {}).get(year)


def should_skip_official_site(venue: str, year: int) -> bool:
    """
    判断某个会议年份是否应该跳过会议官网源。
    """
    config = get_openreview_config(venue, year)
    if not config:
        return False

    return config.get("skip_official_site", False)