from copy import deepcopy

import requests
from bs4 import BeautifulSoup

from ai4research.data_pipeline.crawlers.base import BaseCrawler
from ai4research.data_pipeline.schemas.paper_schema import DEFAULT_PAPER_FIELDS
from ai4research.data_pipeline.source_configs.pmlr_gen_config import get_pmlr_config
from ai4research.data_pipeline.utils.text_utils import paper_id_from_title


class PMLRCrawler(BaseCrawler):
    """
    PMLR proceedings crawler.

    第一版：
    - 只解析 volume 列表页
    - 获取 title / authors / abs_url / pdf_url
    - 暂不进入详情页抓 abstract
    """

    def __init__(self, venue, year, max_results=None, fetch_details=False):
        self.venue = venue.upper()
        self.year = year
        self.max_results = max_results
        self.fetch_details = fetch_details

        self.config = get_pmlr_config(self.venue, self.year)

        self.volume = self.config["volume"]
        self.volume_url = self.config["volume_url"]
        self.accepted_by = self.config["accepted_by"]
        self.accept_type = self.config.get("accept_type", "Proceedings")

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; AI4Research/1.0)"
        })

    def crawl(self, start_date=None, end_date=None):
        print(f"🚀 Crawling PMLR venue={self.venue} year={self.year}")
        print(f"🔎 volume: {self.volume}")
        print(f"🔎 volume_url: {self.volume_url}")

        papers = self._fetch_volume_papers()

        if self.max_results is not None:
            papers = papers[: self.max_results]

        print(f"📄 Papers parsed from PMLR volume page: {len(papers)}")

        source_context = f"PMLR v{self.volume}"

        # for item in papers:
        #     paper_data = self._item_to_paper_data(item)
        #     yield paper_data, source_context
        for item in papers:
            if self.fetch_details and item.get("abs_url"):
                detail = self._fetch_detail(item["abs_url"])
                item.update(detail)

            paper_data = self._item_to_paper_data(item)
            yield paper_data, source_context


    def _fetch_volume_papers(self):
        resp = self.session.get(self.volume_url, timeout=60)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        paper_blocks = soup.select(".paper")

        results = []

        for block in paper_blocks:
            title_tag = block.select_one(".title")
            authors_tag = block.select_one(".authors")

            title = title_tag.get_text(" ", strip=True) if title_tag else ""
            authors_text = authors_tag.get_text(" ", strip=True) if authors_tag else ""

            abs_url = ""
            pdf_url = ""

            for a in block.find_all("a"):
                text = a.get_text(" ", strip=True).lower()
                href = a.get("href", "")

                if text == "abs":
                    abs_url = href
                elif "pdf" in text:
                    pdf_url = href

            if not title:
                continue

            results.append({
                "title": title,
                "authors_text": authors_text,
                "abs_url": abs_url,
                "pdf_url": pdf_url,
            })

        return results


    def _fetch_detail(self, abs_url):
        try:
            resp = self.session.get(abs_url, timeout=60)
            resp.raise_for_status()
        except Exception as e:
            print(f"⚠️ Failed to fetch detail page: {abs_url} | {e}")
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")

        def meta_content(name):
            tag = soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                return tag["content"].strip()
            return ""

        abstract = ""

        abstract_tag = soup.select_one("#abstract") or soup.select_one("div.abstract")
        if abstract_tag:
            abstract = abstract_tag.get_text(" ", strip=True)

        authors = [
            tag.get("content", "").strip()
            for tag in soup.find_all("meta", attrs={"name": "citation_author"})
            if tag.get("content")
        ]

        return {
            "detail_title": meta_content("citation_title"),
            "detail_authors": authors,
            "abstract": abstract,
            "publication_date": meta_content("citation_publication_date"),
            "firstpage": meta_content("citation_firstpage"),
            "lastpage": meta_content("citation_lastpage"),
            "citation_pdf_url": meta_content("citation_pdf_url"),
            "citation_abs_url": meta_content("citation_abstract_html_url"),
        }


    def _item_to_paper_data(self, item):
        paper = deepcopy(DEFAULT_PAPER_FIELDS)

        title = item["title"]

        paper["_id"] = paper_id_from_title(title)
        paper["title"] = title
        paper["authors"] = self._parse_authors(item.get("authors_text", ""))
        paper["abstract"] = item.get("abstract", "")

        paper["accepted_by"] = self.accepted_by

        paper["base_urls"] = {
            "pmlr_abs_url": item.get("abs_url", ""),
            "pmlr_pdf_url": item.get("pdf_url", ""),
        }


        paper["more_urls"] = {
            "pmlr_volume_url": self.volume_url,
            "pmlr_publication_date": item.get("publication_date", ""),
            "pmlr_firstpage": item.get("firstpage", ""),
            "pmlr_lastpage": item.get("lastpage", ""),
        }


        paper["pipeline"] = ""
        paper["tags"] = []

        return paper

    def _parse_authors(self, authors_text):
        if not authors_text:
            return []

        names = [x.strip() for x in authors_text.split(",") if x.strip()]

        return [
            {
                "name": name,
                "affiliation": "",
                "homepage": "",
            }
            for name in names
        ]