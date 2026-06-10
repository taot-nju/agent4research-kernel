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
                "api_version": "v2",
                "query_type": "content_venueid",
                "source": "OpenReview",
                "skip_official_site": True,
                "note": "Use OpenReview as primary source.",
            },
            2025: {
                "venue_id": "ICLR.cc/2025/Conference",
                "api_version": "v2",
                "query_type": "content_venueid",
                "source": "OpenReview",
                "skip_official_site": True,
                "note": "Use OpenReview as primary source.",
            },
            2024: {
                "venue_id": "ICLR.cc/2024/Conference",
                "api_version": "v2",  # 用 openreview.api.OpenReviewClient(baseurl="https://api2.openreview.net")
                "query_type": "content_venueid",
                "source": "OpenReview",
                "skip_official_site": True,
                "note": "Use OpenReview as primary source.",
            },
            2023: {
                "venue_id": "ICLR.cc/2023/Conference",
                "api_version": "v1",  # 用 openreview.Client(baseurl="https://api.openreview.net")
                "query_type": "content_venueid",
                "source": "OpenReview",
                "skip_official_site": True,
                "accepted_venues": [  # 只保留这些 venue 字段对应的录用论文
                    "ICLR 2023 poster",
                    "ICLR 2023 notable top 25%",
                    "ICLR 2023 notable top 5%",
                ],
                "note": "ICLR 2023 uses OpenReview v1 API. Filter accepted papers by venue field.",
            },
            2022: {
                "venue_id": "ICLR.cc/2022/Conference",
                "api_version": "v1",
                "query_type": "content_venueid",
                "source": "OpenReview",
                "skip_official_site": True,
                "accepted_venues": [
                    "ICLR 2022 Poster",
                    "ICLR 2022 Spotlight",
                    "ICLR 2022 Oral",
                ],
                "note": "ICLR 2022 uses OpenReview v1 API. Filter accepted papers by venue field.",
            },
        },
    },

    # "ICML": {
    #     "venue": "ICML",
    #     "years": {
    #         # 2026 暂不配置，等放榜或 OpenReview 页面稳定后再补。
    #     },
    # },

    "ICML": {
        "venue": "ICML",
        "years": {
            2025: {
                "venue_id": "ICML.cc/2025/Conference",
                "api_version": "v2",
                "query_type": "content_venueid",
                "source": "OpenReview",
                "skip_official_site": True,
                "note": "Use OpenReview as primary source.",
            },
            2024: {
                "venue_id": "ICML.cc/2024/Conference",
                "api_version": "v2",
                "query_type": "content_venueid",
                "source": "OpenReview",
                "skip_official_site": True,
                "note": "Use OpenReview as primary source.",
            },
            2023: {
                "venue_id": "ICML.cc/2023/Conference",
                "api_version": "v2",
                "query_type": "content_venueid",
                "source": "OpenReview",
                "skip_official_site": True,
                "note": "Use OpenReview as primary source.",
            },
        },
    },

    "NeurIPS": {
        "years": {
            2022: {
                "venue_id": "NeurIPS.cc/2022/Conference",
                "api_version": "v1",
                "query_type": "content_venueid",
                "source": "OpenReview",
                "skip_official_site": True,
                "accepted_venues": [
                    "NeurIPS 2022 Accept",
                ],
                "note": "NeurIPS 2022 uses OpenReview v1 API. Filter accepted papers by venue field.",
            },
            2023: {
                "venue_id": "NeurIPS.cc/2023/Conference",
                "api_version": "v2",
                "query_type": "content_venueid",
                "source": "OpenReview",
                "skip_official_site": True,
                "note": "NeurIPS 2023 uses OpenReview v2 API. Accepted papers can be queried by venueid.",
            },
            2024: {
                "venue_id": "NeurIPS.cc/2024/Conference",
                "api_version": "v2",
                "query_type": "content_venueid",
                "source": "OpenReview",
                "skip_official_site": True,
                "note": "NeurIPS 2024 uses OpenReview v2 API. Accepted papers can be queried by venueid.",
            },
            2025: {
                "venue_id": "NeurIPS.cc/2025/Conference",
                "api_version": "v2",
                "query_type": "content_venueid",
                "source": "OpenReview",
                "skip_official_site": True,
                "note": "NeurIPS 2025 uses OpenReview v2 API. Accepted papers can be queried by venueid.",
            },
        }
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