"""
OpenReview venue 抓取流水线：把 OpenReviewCrawler 产出的论文逐篇写入 MongoDB，
并在开启 vault 时额外写一份 Obsidian Markdown“论文画像”。

与 arxiv_daily.py 结构一致：crawler → pipeline → db_ops（upsert）→ MongoDB。
"""

from tqdm import tqdm
from rich import print

from ai4research.data_pipeline.crawlers.openreview_crawler import OpenReviewCrawler
from ai4research.data_pipeline.crawlers.openreview import vault_writer
from ai4research.data_pipeline.db_ops.paper_repository import upsert_openreview_paper


def crawl_openreview(
    venue,
    *,
    write_vault=False,
    dry_run=False,
    **crawler_kwargs,
):
    """抓取一个 OpenReview venue 并逐篇写入 MongoDB。

    :param venue: OpenReview venue id，例如 "ICLR.cc/2026/Conference"
    :param write_vault: 是否额外输出 Markdown 论文画像（vault）
    :param dry_run: 只抓取与富化、不写库也不写文件（仍会写本地缓存）
    :param crawler_kwargs: 透传给 OpenReviewCrawler 的其余参数
                           （api / categories / enrich / profiles / github /
                            cited_history / llm_extract / llm_provider / limit /
                            ids / username / password / out(vault 根目录) / ...）
    """
    crawler = OpenReviewCrawler(venue, dry_run=dry_run, **crawler_kwargs)

    pbar = tqdm(desc="OpenReview papers", unit="paper")

    count = 0
    collected = []

    for paper_data, venue_label in crawler.crawl():
        # 弹出瞬时挂载的原始 PaperRecord（用于可选的 vault 写出，绝不入库）
        rec = paper_data.pop("_openreview_record", None)
        if rec is not None:
            collected.append(rec)

        if not dry_run:
            upsert_openreview_paper(paper_data=paper_data, venue=venue_label)
        else:
            print(f"[dim]🧪 dry-run: would upsert {paper_data['_id']} "
                  f"(accepted_by={paper_data['accepted_by']})[/dim]")

        count += 1
        pbar.update(1)

    pbar.close()

    # 可选：写 Markdown vault（dry-run 下 write_vault 内部也不会真正写盘）
    if write_vault and collected:
        vault_writer.write_vault(
            records=collected,
            venue=crawler.venue,
            api_version=crawler.api_version,
            cfg=crawler.cfg,
        )
        print(f"📝 [bold]Vault[/bold] written under: {crawler.cfg.out_venue_dir}")

    print(
        f"🎉 [bold italic underline red]OpenReview venue [cyan]{venue}[/cyan] "
        f"crawl finished. Total papers processed: {count}"
    )
    return count
