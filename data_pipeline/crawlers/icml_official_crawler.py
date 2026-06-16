from copy import deepcopy
from urllib.parse import urljoin

import time
import requests
import re
from bs4 import BeautifulSoup

from ai4research.data_pipeline.crawlers.base import BaseCrawler
from ai4research.data_pipeline.schemas.paper_schema import DEFAULT_PAPER_FIELDS
from ai4research.data_pipeline.source_configs.conference_gen_config import CONFERENCES
from ai4research.data_pipeline.utils.text_utils import paper_id_from_title


class ICMLOfficialCrawler(BaseCrawler):
    """
    ICML official website crawler.

    当前主要用于 ICML 2026：
    - 官方 Downloads 页面已有 title / detail_url
    - detail 页面有 authors / abstract / accept_type
    - 暂时没有 PDF
    """

    BASE_URL = "https://icml.cc"

    def __init__(self, year, max_results=None, fetch_details=False):
        self.venue = "ICML"
        self.year = year
        self.max_results = max_results
        self.fetch_details = fetch_details

        self.config = CONFERENCES[self.venue]

        if self.year not in self.config["available_years"]:
            raise ValueError(f"Unsupported ICML official year: {self.year}")

        self.list_url = self.config["base_url_template"].format(year=self.year)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; AI4Research/1.0)"
        })

    def crawl(self, start_date=None, end_date=None):
        print(f"🚀 Crawling ICML official site year={self.year}")
        print(f"🔎 list_url: {self.list_url}")

        items = self._fetch_list_items()

        if self.max_results is not None:
            items = items[: self.max_results]

        print(f"📄 Candidate items parsed from ICML official list page: {len(items)}")

        source_context = f"ICML Official {self.year}"

        for item in items:
            if self.fetch_details and item.get("detail_url"):
                detail = self._fetch_detail(item["detail_url"])
                item.update(detail)

                # 如果详情页 title 更完整，则用详情页 title
                if item.get("detail_title"):
                    item["title"] = item["detail_title"]

            paper_data = self._item_to_paper_data(item)
            yield paper_data, source_context

    def _fetch_list_items(self):
        resp = self.session.get(self.list_url, timeout=60)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        main = soup.select_one("main") or soup.body

        results = []
        seen_urls = set()

        for a in main.find_all("a"):
            title = a.get_text(" ", strip=True)
            href = a.get("href", "")

            if not title or not href:
                continue

            detail_url = urljoin(self.list_url, href)

            # ICML 2026 主列表目前是 /virtual/2026/poster/{id}
            if f"/virtual/{self.year}/poster/" not in detail_url:
                continue

            if detail_url in seen_urls:
                continue

            seen_urls.add(detail_url)

            results.append({
                "title": title,
                "detail_url": detail_url,
                "accept_type": "Poster",
            })

        return results
    

    def _clean_abstract(self, text):
        text = (text or "").strip()

        # ICML 官网摘要折叠按钮文本会被 BeautifulSoup 一起抓到
        if text.endswith("Show more"):
            text = text[: -len("Show more")].strip()

        if text.endswith("Show less"):
            text = text[: -len("Show less")].strip()

        return text
    

    def _fetch_detail(self, detail_url):
        # resp = self.session.get(detail_url, timeout=60)
        # resp.raise_for_status()

        # soup = BeautifulSoup(resp.text, "html.parser")

        for attempt in range(1, 4):
            try:
                resp = self.session.get(detail_url, timeout=60)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                break

            except requests.RequestException as e:
                print(
                    f"⚠️ Failed to fetch detail page "
                    f"attempt={attempt}/3 url={detail_url} error={e}"
                )

                if attempt < 3:
                    time.sleep(5 * attempt)
        else:
            print(f"❌ Skip detail page after 3 failed attempts: {detail_url}")
            return {
                "detail_title": "",
                "accept_type": "",
                "authors": [],
                "abstract": "",
                "keywords": [],
            }

        title_tag = soup.select_one("h1.event-title")
        accept_type_tag = soup.select_one("span.event-type-badge")
        authors_tag = soup.select_one("div.event-organizers")
        abstract_tag = (
            soup.select_one("div.abstract-content")
            or soup.select_one("div.abstract-text-inner")
            or soup.select_one("#abstractText")
        )

        keywords_meta = soup.find("meta", attrs={"name": "keywords"})

        title = title_tag.get_text(" ", strip=True) if title_tag else ""
        accept_type = accept_type_tag.get_text(" ", strip=True) if accept_type_tag else ""
        authors_text = authors_tag.get_text(" ", strip=True) if authors_tag else ""
        
        abstract = abstract_tag.get_text(" ", strip=True) if abstract_tag else ""
        abstract = self._clean_abstract(abstract)

        keywords_text = keywords_meta.get("content", "").strip() if keywords_meta else ""

        authors = [x.strip() for x in authors_text.split("⋅") if x.strip()]

        keywords = []
        if keywords_text:
            # 例如：Optimization:Discrete and Combinatorial Optimization
            keywords = [x.strip() for x in keywords_text.split(";") if x.strip()]
            if len(keywords) == 1 and "," in keywords_text:
                keywords = [x.strip() for x in keywords_text.split(",") if x.strip()]

        return {
            "detail_title": title,
            "accept_type": accept_type,
            "authors": authors,
            "abstract": abstract,
            "keywords": keywords,
        }


    def _parse_event_id(self, detail_url):
        match = re.search(r"/virtual/\d+/poster/(\d+)", detail_url or "")
        if match:
            return match.group(1)
        return ""


    def _item_to_paper_data(self, item):
        paper = deepcopy(DEFAULT_PAPER_FIELDS)

        title = item["title"]

        paper["_id"] = paper_id_from_title(title)
        paper["title"] = title
        paper["authors"] = [
            {
                "name": name,
                "affiliation": "",
                "homepage": "",
            }
            for name in item.get("authors", [])
        ]

        paper["abstract"] = item.get("abstract", "")
        paper["keywords"] = item.get("keywords", [])

        paper["accepted_by"] = f"ICML {self.year}"


        official_url = item.get("detail_url", "")
        official_pdf_url = ""

        paper["base_urls"] = {
            "official_url": official_url,
            "official_pdf_url": official_pdf_url,
        }

        paper["more_urls"] = {}

        paper["icml_official_obj"] = {
            "venue": self.venue,
            "year": str(self.year),
            "event_id": self._parse_event_id(official_url),
            "event_type": "poster",
            "accept_type": item.get("accept_type", ""),
            "official_url": official_url,
            "official_pdf_url": official_pdf_url,
            "keywords": item.get("keywords", []),
        }

        paper["tags"] = []
        paper["pipeline"] = ""

        # 暂时不新增 icml_official_obj schema，第一版先放在已有字段里。
        # 后续如果官网源稳定，再考虑 icml_official_obj 作为单独 schema，并迁移相关字段过去。
        return paper