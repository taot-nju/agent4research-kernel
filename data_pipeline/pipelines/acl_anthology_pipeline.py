from tqdm import tqdm

from ai4research.data_pipeline.crawlers.acl_anthology_crawler import ACLAnthologyCrawler
from ai4research.data_pipeline.db_ops.paper_repository import upsert_paper


def crawl_acl_anthology(
    venue: str,
    year: int,
    subtype: str = "long",
    max_results=None,
    delay_seconds: float = 0.5,
):
    crawler = ACLAnthologyCrawler(
        venue=venue,
        year=year,
        subtype=subtype,
        max_results=max_results,
        delay_seconds=delay_seconds,
    )

    pbar = tqdm(
        desc=f"Crawling ACL Anthology {venue} {year} {subtype}",
        unit="paper",
    )

    count = 0

    for paper_data, source_context in crawler.crawl():
        upsert_paper(
            paper_data=paper_data,
            source="ACL Anthology",
            category=source_context,
        )

        count += 1
        pbar.update(1)

    pbar.close()

    print(
        f"🎉 ACL Anthology crawl finished. "
        f"venue={venue}, year={year}, subtype={subtype}, "
        f"total papers processed: {count}"
    )