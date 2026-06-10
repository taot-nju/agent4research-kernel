from tqdm import tqdm
from rich import print

from ai4research.data_pipeline.crawlers.icml_official_crawler import ICMLOfficialCrawler
from ai4research.data_pipeline.db_ops.paper_repository import upsert_paper


def crawl_icml_official(year, max_results=None, fetch_details=False):
    crawler = ICMLOfficialCrawler(
        year=year,
        max_results=max_results,
        fetch_details=fetch_details,
    )

    total = 0

    pbar = tqdm(desc=f"Crawling ICML official {year}", unit="paper")

    for paper_data, source_context in crawler.crawl():
        upsert_paper(
            paper_data=paper_data,
            source="ICML Official",
            category=source_context,
        )

        total += 1
        pbar.update(1)

    pbar.close()

    print(
        f"🎉 ICML official {year} crawl finished. "
        f"Total papers processed: {total}"
    )