"""
AAAI 官方 Proceedings 爬取 Pipeline。

负责串联：
AAAIOfficialCrawler
    -> 逐篇生成 paper_data
    -> upsert_paper
    -> MongoDB
"""

from rich import print
from tqdm import tqdm

from ai4research.data_pipeline.crawlers.aaai_official_crawler import (
    AAAIOfficialCrawler,
)
from ai4research.data_pipeline.db_ops.paper_repository import upsert_paper


def crawl_aaai_official(
    year: int,
    max_results=None,
):
    """
    爬取指定年份的 AAAI 正式论文，并逐篇写入 MongoDB。

    默认包含：
    - AAAI Technical Tracks
    - AAAI Special Tracks

    默认排除：
    - Journal Track
    - IAAI / EAAI
    - Student Abstracts
    - Doctoral Consortium
    - Demonstrations
    - Senior Member Presentations
    - 其他非主会正式研究论文类别

    :param year: AAAI 年份，例如 2026
    :param max_results: 调试时限制处理数量；None 表示不限制
    """
    crawler = AAAIOfficialCrawler(
        year=year,
        max_results=max_results,
    )

    venue_year = f"AAAI {year}"

    pbar = tqdm(
        desc=f"Crawling AAAI official {year}",
        unit="paper",
    )

    count = 0

    for paper_data, source_context in crawler.crawl():
        upsert_paper(
            paper_data=paper_data,
            source="AAAI Official",
            category=None,
        )

        count += 1
        pbar.update(1)

    pbar.close()

    print(
        f"🎉 [bold italic underline red]{venue_year} official crawl finished. "
        f"Total papers processed: {count}"
    )