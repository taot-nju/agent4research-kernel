import copy
import re
import time

import requests
from bs4 import BeautifulSoup

from ai4research.data_pipeline.crawlers.base import BaseCrawler
from ai4research.data_pipeline.schemas.paper_schema import DEFAULT_PAPER_FIELDS
from ai4research.data_pipeline.source_configs.acl_anthology_config import (
    ACL_ANTHOLOGY_BASE_URL,
    get_acl_anthology_config,
)
from ai4research.data_pipeline.utils.text_utils import paper_id_from_title


class ACLAnthologyCrawler(BaseCrawler):
    """
    Crawl papers from ACL Anthology volume pages.

    Current target:
    - ACL Long Papers: https://aclanthology.org/volumes/{year}.acl-long/

    Strategy:
    - Volume page: collect anthology paper ids, e.g. 2025.acl-long.1
    - Paper page: parse clean metadata from citation_* meta tags and div.acl-abstract
    """

    def __init__(
        self,
        venue: str,
        year: int,
        subtype: str = "long",
        max_results=None,
        delay_seconds: float = 0.5,
    ):
        self.venue = venue.upper()
        self.year = year
        self.subtype = subtype.lower()
        self.max_results = max_results
        self.delay_seconds = delay_seconds

        self.failed_ids = []
        self.not_found_ids = []

        self.config = get_acl_anthology_config(
            venue=self.venue,
            year=self.year,
            subtype=self.subtype,
        )
        if self.config is None:
            raise ValueError(
                f"Unsupported ACL Anthology config: "
                f"venue={self.venue}, year={self.year}, subtype={self.subtype}"
            )

        self.volume_id = self.config["volume_id"]
        self.volume_url = self.config["url"]

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; AI4Research/1.0; "
                    "mailto:research@example.com)"
                )
            }
        )

    def crawl(self, start_date=None, end_date=None):
        print(
            f"🚀 Crawling ACL Anthology venue={self.venue} "
            f"year={self.year} subtype={self.subtype}"
        )
        print(f"🔎 volume_id: {self.volume_id}")
        print(f"🔗 volume_url: {self.volume_url}")

        paper_ids = self._fetch_paper_ids()
        print(f"📄 Total paper ids found: {len(paper_ids)}")

        if self.max_results is not None:
            paper_ids = paper_ids[: self.max_results]
            print(f"📄 Limited paper ids by max_results={self.max_results}")

        source_context = f"{self.venue} {self.year} {self.config['subtype']}"

        for idx, anthology_id in enumerate(paper_ids, start=1):
            paper_data = self._fetch_paper_detail(anthology_id)
            if paper_data is None:
                print(f"⚠️ Skip failed paper: {anthology_id}")
                continue

            print(f"✅ Parsed [{idx}/{len(paper_ids)}]: {paper_data['title']}")

            yield paper_data, source_context

            if self.delay_seconds:
                time.sleep(self.delay_seconds)

        if self.failed_ids:
            print("=" * 80)
            print(f"⚠️ Failed paper ids: {len(self.failed_ids)}")
            for x in self.failed_ids:
                print(x)

        if self.not_found_ids:
            print("=" * 80)
            print(f"⚠️ 404 not found paper ids: {len(self.not_found_ids)}")
            for x in self.not_found_ids:
                print(x)

    def _fetch_paper_ids(self):
        resp = self.session.get(self.volume_url, timeout=60)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        pattern = re.compile(rf"^/{re.escape(self.volume_id)}\.(\d+)/$")

        paper_ids = []
        seen = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            match = pattern.match(href)
            if not match:
                continue

            paper_no = int(match.group(1))

            # .0 is the proceedings volume itself, not a paper.
            if paper_no == 0:
                continue

            anthology_id = href.strip("/")

            if anthology_id in seen:
                continue

            seen.add(anthology_id)
            paper_ids.append(anthology_id)

        paper_ids.sort(key=self._paper_id_sort_key)
        return paper_ids

    @staticmethod
    def _paper_id_sort_key(anthology_id: str):
        match = re.search(r"\.(\d+)$", anthology_id)
        if match:
            return int(match.group(1))
        return 10**12

    def _fetch_paper_detail(self, anthology_id: str):
        paper_url = f"{ACL_ANTHOLOGY_BASE_URL}/{anthology_id}/"

        # try:
        #     resp = self.session.get(paper_url, timeout=60)
        #     resp.raise_for_status()
        # except Exception as e:
        #     print(f"⚠️ Failed to fetch {paper_url}: {e}")
        #     return None
        resp = None
        last_error = None

        for attempt in range(1, 4):
            try:
                resp = self.session.get(paper_url, timeout=60)

                if resp.status_code == 404:
                    print(f"⚠️ 404 not found: {paper_url}")
                    self.not_found_ids.append(anthology_id)
                    return None

                resp.raise_for_status()
                break

            except Exception as e:
                last_error = e
                print(
                    f"⚠️ Fetch failed "
                    f"attempt={attempt}/3, url={paper_url}, error={e}"
                )

                if attempt < 3:
                    time.sleep(2 * attempt)

        if resp is None:
            print(f"⚠️ Failed after retries: {paper_url}, error={last_error}")
            self.failed_ids.append(anthology_id)
            return None
        

        soup = BeautifulSoup(resp.text, "html.parser")

        title = self._get_meta_content(soup, "citation_title")
        if not title:
            print(f"⚠️ Missing title: {paper_url}")
            self.failed_ids.append(anthology_id)
            return None


        authors = [
            {"name": meta.get("content", "").strip(), "affiliation": "", "homepage": ""}
            for meta in soup.find_all("meta", attrs={"name": "citation_author"})
            if meta.get("content", "").strip()
        ]

        pdf_url = self._get_meta_content(soup, "citation_pdf_url")
        doi = self._get_meta_content(soup, "citation_doi")
        publication_date = self._get_meta_content(soup, "citation_publication_date")
        first_page = self._get_meta_content(soup, "citation_firstpage")
        last_page = self._get_meta_content(soup, "citation_lastpage")

        abstract = self._parse_abstract(soup)

        paper_data = copy.deepcopy(DEFAULT_PAPER_FIELDS)

        paper_data["_id"] = paper_id_from_title(title)
        paper_data["title"] = title
        paper_data["authors"] = authors
        paper_data["abstract"] = abstract

        paper_data["accepted_by"] = self.config["accepted_by"]

        paper_data["acl_anthology_obj"] = {
            "anthology_id": anthology_id,
            "volume_id": self.volume_id,
            "venue": self.venue,
            "year": self.year,
            "subtype": self.config["subtype"],
            "paper_url": paper_url,
            "pdf_url": pdf_url,
            "bib_url": f"{ACL_ANTHOLOGY_BASE_URL}/{anthology_id}.bib",
            "doi": doi,
            "first_page": first_page,
            "last_page": last_page,
            "publication_date": publication_date,
        }

        paper_data["base_urls"] = {
            "acl_anthology_url": paper_url,
            "acl_anthology_pdf_url": pdf_url,
        }

        paper_data["more_urls"] = {
            "bib_url": f"{ACL_ANTHOLOGY_BASE_URL}/{anthology_id}.bib",
        }

        return paper_data

    @staticmethod
    def _get_meta_content(soup, name: str) -> str:
        meta = soup.find("meta", attrs={"name": name})
        if meta and meta.get("content"):
            return meta["content"].strip()
        return ""

    @staticmethod
    def _parse_abstract(soup) -> str:
        abstract_div = soup.select_one("div.acl-abstract")
        if abstract_div is None:
            return ""

        abstract = abstract_div.get_text(" ", strip=True)

        # Remove leading label.
        abstract = re.sub(r"^Abstract\s*", "", abstract).strip()

        return abstract