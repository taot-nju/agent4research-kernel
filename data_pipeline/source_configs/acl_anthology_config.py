# ACL Anthology volume configs
#
# Stable source:
#   https://aclanthology.org/volumes/{volume_id}/
#
# Examples:
#   ACL Long Papers: 2025.acl-long
#   ACL Short Papers: 2025.acl-short
#   Findings of ACL: 2025.findings-acl

ACL_ANTHOLOGY_BASE_URL = "https://aclanthology.org"


ACL_ANTHOLOGY_VOLUMES = {
    "ACL": {
        "venue": "ACL",
        "years": {
            2025: {
                "long": {
                    "volume_id": "2025.acl-long",
                    "url": "https://aclanthology.org/volumes/2025.acl-long/",
                    "accepted_by": "ACL 2025",
                    "subtype": "Long Paper",
                    "source": "ACL Anthology",
                },
                "short": {
                    "volume_id": "2025.acl-short",
                    "url": "https://aclanthology.org/volumes/2025.acl-short/",
                    "accepted_by": "ACL 2025",
                    "subtype": "Short Paper",
                    "source": "ACL Anthology",
                },
                "findings": {
                    "volume_id": "2025.findings-acl",
                    "url": "https://aclanthology.org/volumes/2025.findings-acl/",
                    "accepted_by": "ACL Findings 2025",
                    "subtype": "Findings",
                    "source": "ACL Anthology",
                },
            },
            2024: {
                "long": {
                    "volume_id": "2024.acl-long",
                    "url": "https://aclanthology.org/volumes/2024.acl-long/",
                    "accepted_by": "ACL 2024",
                    "subtype": "Long Paper",
                    "source": "ACL Anthology",
                },
                "short": {
                    "volume_id": "2024.acl-short",
                    "url": "https://aclanthology.org/volumes/2024.acl-short/",
                    "accepted_by": "ACL 2024",
                    "subtype": "Short Paper",
                    "source": "ACL Anthology",
                },
                "findings": {
                    "volume_id": "2024.findings-acl",
                    "url": "https://aclanthology.org/volumes/2024.findings-acl/",
                    "accepted_by": "ACL Findings 2024",
                    "subtype": "Findings",
                    "source": "ACL Anthology",
                },
            },
            2023: {
                "long": {
                    "volume_id": "2023.acl-long",
                    "url": "https://aclanthology.org/volumes/2023.acl-long/",
                    "accepted_by": "ACL 2023",
                    "subtype": "Long Paper",
                    "source": "ACL Anthology",
                },
                "short": {
                    "volume_id": "2023.acl-short",
                    "url": "https://aclanthology.org/volumes/2023.acl-short/",
                    "accepted_by": "ACL 2023",
                    "subtype": "Short Paper",
                    "source": "ACL Anthology",
                },
                "findings": {
                    "volume_id": "2023.findings-acl",
                    "url": "https://aclanthology.org/volumes/2023.findings-acl/",
                    "accepted_by": "ACL Findings 2023",
                    "subtype": "Findings",
                    "source": "ACL Anthology",
                },
            },
            2022: {
                "long": {
                    "volume_id": "2022.acl-long",
                    "url": "https://aclanthology.org/volumes/2022.acl-long/",
                    "accepted_by": "ACL 2022",
                    "subtype": "Long Paper",
                    "source": "ACL Anthology",
                },
                "short": {
                    "volume_id": "2022.acl-short",
                    "url": "https://aclanthology.org/volumes/2022.acl-short/",
                    "accepted_by": "ACL 2022",
                    "subtype": "Short Paper",
                    "source": "ACL Anthology",
                },
                "findings": {
                    "volume_id": "2022.findings-acl",
                    "url": "https://aclanthology.org/volumes/2022.findings-acl/",
                    "accepted_by": "ACL Findings 2022",
                    "subtype": "Findings",
                    "source": "ACL Anthology",
                },
            },
        },
    }
}


def get_acl_anthology_config(venue: str, year: int, subtype: str):
    venue = venue.upper()
    subtype = subtype.lower()

    venue_config = ACL_ANTHOLOGY_VOLUMES.get(venue)
    if venue_config is None:
        return None

    year_config = venue_config["years"].get(year)
    if year_config is None:
        return None

    return year_config.get(subtype)