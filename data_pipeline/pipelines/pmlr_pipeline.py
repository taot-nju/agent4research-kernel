from tqdm import tqdm
from rich import print

from ai4research.data_pipeline.crawlers.pmlr_crawler import PMLRCrawler
from ai4research.data_pipeline.db_ops.paper_repository import upsert_paper


def crawl_pmlr(venue, year, max_results=None, fetch_details=False):
    crawler = PMLRCrawler(
        venue=venue,
        year=year,
        max_results=max_results,
        fetch_details=fetch_details,
    )

    total = 0

    pbar = tqdm(desc=f"Crawling PMLR {venue.upper()} {year}", unit="paper")

    for paper_data, source_context in crawler.crawl():
        upsert_paper(
            paper_data=paper_data,
            source="PMLR",
            category=source_context,
        )

        total += 1
        pbar.update(1)

    pbar.close()

    print(
        f"🎉 PMLR {venue.upper()} {year} crawl finished. "
        f"Total papers processed: {total}"
    )