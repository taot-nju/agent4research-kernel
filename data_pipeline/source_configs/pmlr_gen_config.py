PMLR_CONFERENCES = {
    "ICML": {
        "venue": "ICML",
        "years": {
            2022: {
                "volume": "162",
                "volume_url": "https://proceedings.mlr.press/v162/",
                "source": "PMLR",
                "accepted_by": "ICML 2022",
                "accept_type": "Proceedings",
                "skip_official_site": True,
                "note": "ICML 2022 proceedings are available from PMLR Volume 162.",
            },
        },
    },
}


def get_pmlr_config(venue, year):
    venue = venue.upper()

    if venue not in PMLR_CONFERENCES:
        raise ValueError(f"Unsupported PMLR venue: {venue}")

    years = PMLR_CONFERENCES[venue]["years"]

    if year not in years:
        raise ValueError(f"Unsupported PMLR year: {venue} {year}")

    config = dict(years[year])
    config["venue"] = PMLR_CONFERENCES[venue]["venue"]
    config["year"] = year

    return config