from datetime import datetime, timezone

from tqdm import tqdm
from rich import print

from ai4research.data_pipeline.crawlers.arxiv_crawler import ArxivCrawler
from ai4research.data_pipeline.db_ops.paper_repository import upsert_paper


def crawl_daily(start_date=None, end_date=None, max_results=None, categories=None):
    """
    爬取指定日期范围内的 arXiv 论文，并逐篇写入 MongoDB。

    start_date / end_date: YYYY-MM-DD
    如果都不传，默认爬取 UTC 当天。
    """
    if start_date is None and end_date is None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start_date = end_date = today

    crawler = ArxivCrawler(max_results=max_results, categories=categories)

    
    pbar = tqdm(desc="Crawling papers", unit="paper")

    count = 0

    for paper_data, category in crawler.crawl(start_date=start_date, end_date=end_date):
        upsert_paper(
            paper_data=paper_data,
            source="arXiv",
            category=category,
        )
        count += 1
        pbar.update(1)

    pbar.close()

    print(
        f"🎉 [bold italic underline red]{start_date} ~ {end_date} "
        f"crawl finished. Total papers processed: {count}"
    )