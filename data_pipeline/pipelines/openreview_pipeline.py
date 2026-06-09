from tqdm import tqdm
from rich import print

from ai4research.data_pipeline.crawlers.openreview_crawler import OpenReviewCrawler
from ai4research.data_pipeline.db_ops.paper_repository import upsert_paper


def crawl_openreview(venue: str, year: int, max_results=None):
    """
    爬取指定 OpenReview venue/year 的论文，并逐篇写入 MongoDB。

    例如：
        crawl_openreview("ICLR", 2026, max_results=10)
    """
    crawler = OpenReviewCrawler(
        venue=venue,
        year=year,
        max_results=max_results,
    )

    venue_year = f"{venue} {year}"

    pbar = tqdm(desc=f"Crawling OpenReview {venue_year}", unit="paper")

    count = 0

    for paper_data, source_context in crawler.crawl():
        upsert_paper(
            paper_data=paper_data,
            source="OpenReview",
            category=None,
        )
        count += 1
        pbar.update(1)

    pbar.close()

    print(
        f"🎉 [bold italic underline red]OpenReview {venue_year} crawl finished. "
        f"Total papers processed: {count}"
    )