"""
AAAI 官方 Proceedings 爬虫。

当前阶段只实现：
1. 请求单篇 AAAI OJS article 页面；
2. 解析页面中的标准 meta 元数据；
3. 转换为统一的 paper_data。

后续再补：
年度页面 -> issue -> section -> article 的完整遍历流程。
"""

from urllib.parse import urljoin

import copy
import re

import time

import requests
from bs4 import BeautifulSoup, Tag, NavigableString

from ai4research.data_pipeline.crawlers.base import BaseCrawler
from ai4research.data_pipeline.schemas.paper_schema import DEFAULT_PAPER_FIELDS
from ai4research.data_pipeline.source_configs.aaai_config import (
    AAAI_YEARS,
    INCLUDE_ISSUE_KEYWORDS,
    EXCLUDE_ISSUE_KEYWORDS,
)
from ai4research.data_pipeline.utils.text_utils import paper_id_from_title

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class AAAIOfficialCrawler(BaseCrawler):
    """
    基于 AAAI 官方 OJS Proceedings 页面的爬虫。
    """
    
    def __init__(
        self,
        year: int,
        timeout: int = 30,
        max_results=None,
        request_delay: float = 0.3,
    ):
        if year not in AAAI_YEARS:
            raise ValueError(f"No AAAI config found for year={year}")

        self.year = year
        self.config = AAAI_YEARS[year]
        self.timeout = timeout
        self.max_results = max_results

        self.request_delay = request_delay

        self.session = requests.Session()
        retry_strategy = Retry(
            total=5,
            connect=5,
            read=5,
            status=5,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            respect_retry_after_header=True,
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)

        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (compatible; ai4research/1.0; "
                "+https://github.com/)"
            )
        })


    def crawl(self, start_date=None, end_date=None):
        """
        流式爬取指定年份的 AAAI 正式论文。

        流程：
            年度页 -> issue -> section -> article -> paper_data

        每解析完一篇论文，立即 yield：
            paper_data, venue_year
        """
        issues = self.parse_year_issues()
        venue_year = f"AAAI {self.year}"

        processed_count = 0

        for issue_index, issue in enumerate(issues, start=1):
            issue_title = issue["issue_title"]
            issue_url = issue["issue_url"]
            decision = issue["decision"]

            if decision == "SKIP":
                print(f"⏭️ Skip AAAI issue: {issue_title}")
                continue

            print(
                f"📚 Parsing issue {issue_index}/{len(issues)}: "
                f"{issue_title}"
            )

            # article_contexts = self.parse_issue(
            #     issue_url=issue_url,
            #     issue_title=issue_title,
            # )
            page_style = issue.get("page_style", "ojs")

            if page_style == "ojs":
                article_contexts = self.parse_issue(
                    issue_url=issue_url,
                    issue_title=issue_title,
                )

            elif page_style == "legacy_wordpress":
                article_contexts = self.parse_legacy_issue(
                    issue_url=issue_url,
                    issue_title=issue_title,
                )

            else:
                raise ValueError(
                    f"Unsupported AAAI page_style: {page_style}"
                )



            for context in article_contexts:
                article_url = context["article_url"]

                # try:
                #     paper_data = self.parse_article(
                #         article_url=article_url,
                #         issue_title=context["issue_title"],
                #         track_name=context["track_name"],
                #     )
                # except Exception as error:
                #     print(
                #         f"⚠️ Failed to parse AAAI article: {article_url}\n"
                #         f"   {type(error).__name__}: {error}"
                #     )
                #     continue
                try:
                    if page_style == "ojs":
                        paper_data = self.parse_article(
                            article_url=article_url,
                            issue_title=context["issue_title"],
                            track_name=context["track_name"],
                        )

                    elif page_style == "legacy_wordpress":
                        paper_data = self.parse_legacy_article(
                            article_url=article_url,
                            issue_title=context["issue_title"],
                            track_name=context["track_name"],
                            official_pdf_url=context.get(
                                "official_pdf_url",
                                "",
                            ),
                            pages=context.get("pages", ""),
                        )

                    else:
                        raise ValueError(
                            f"Unsupported AAAI page_style: {page_style}"
                        )

                except Exception as error:
                    print(
                        f"⚠️ Failed to parse AAAI article: {article_url}\n"
                        f"   {type(error).__name__}: {error}"
                    )
                    continue

                yield paper_data, venue_year

                processed_count += 1

                if (
                    self.max_results is not None
                    and processed_count >= self.max_results
                ):
                    print(
                        f"🛑 Reached max_results={self.max_results}, "
                        f"stop crawling."
                    )
                    return

    def parse_issue(
        self,
        issue_url: str,
        issue_title: str = "",
    ) -> list[dict]:
        """
        解析一个 AAAI issue 页面，返回应当保留的论文链接。

        每条结果包含：
        - issue_title
        - issue_url
        - track_name
        - track_type
        - article_url
        """
        response = self.session.get(
            issue_url,
            timeout=self.timeout,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        if not issue_title:
            title_node = soup.find("h1")
            if title_node:
                issue_title = self._clean_text(
                    title_node.get_text(" ", strip=True)
                )

        articles = []
        seen_article_urls = set()

        for section_heading in soup.find_all("h2"):
            track_name = self._clean_text(
                section_heading.get_text(" ", strip=True)
            )

            if not track_name:
                continue

            if not self._should_keep_section(track_name):
                print(f"⏭️ Skip AAAI section: {track_name}")
                continue

            track_type = self._parse_track_type(
                track_name=track_name,
                issue_title=issue_title,
            )

            # 从当前 h2 开始向后遍历 h3；
            # 遇到下一个 h2，说明进入了新的 section。
            for node in section_heading.find_all_next(["h2", "h3"]):
                if node.name == "h2":
                    break

                link = node.find("a", href=True)
                if link is None:
                    continue

                article_url = urljoin(issue_url, link["href"])

                if "/article/view/" not in article_url:
                    continue

                if article_url in seen_article_urls:
                    continue

                seen_article_urls.add(article_url)

                articles.append({
                    "issue_title": issue_title,
                    "issue_url": issue_url,
                    "track_name": track_name,
                    "track_type": track_type,
                    "article_url": article_url,
                })

        return articles

    @staticmethod
    def _should_keep_section(section_title: str) -> bool:
        """
        判断 AAAI section 是否属于需要爬取的正式论文范围。
        """
        lower_title = section_title.lower()

        has_include = any(
            keyword.lower() in lower_title
            for keyword in INCLUDE_ISSUE_KEYWORDS
        )

        has_exclude = any(
            keyword.lower() in lower_title
            for keyword in EXCLUDE_ISSUE_KEYWORDS
        )

        return has_include and not has_exclude

    def parse_year_issues(self) -> list[dict]:
        """
        解析 AAAI 某一年的 Proceedings 总页面。

        返回每个 issue 的：
        - issue_title
        - issue_url
        - decision: KEEP / MIXED / SKIP
        """
        proceedings_url = self.config["proceedings_url"]

        response = self.session.get(
            proceedings_url,
            timeout=self.timeout,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        issue_title_pattern = re.compile(
            r"^(?:Vol\.?\s+\d+\s+)?No\.?\s+\d+\s*:",
            re.IGNORECASE,
        )

        issues = []
        seen_issue_urls = set()

        for link in soup.find_all("a", href=True):
            issue_title = self._clean_text(
                link.get_text(" ", strip=True)
            )

            if not issue_title_pattern.search(issue_title):
                continue

            issue_url = urljoin(
                proceedings_url,
                link["href"],
            )

            # 2023-2026 使用 OJS issue 页面；
            # 2022 使用 AAAI 官网旧版 WordPress proceedings 页面。
            if "/issue/view/" in issue_url:
                page_style = "ojs"

            elif (
                issue_url.startswith("https://aaai.org/proceeding/")
                and issue_url.rstrip("/") != proceedings_url.rstrip("/")
            ):
                page_style = "legacy_wordpress"

            else:
                continue

            if issue_url in seen_issue_urls:
                continue

            seen_issue_urls.add(issue_url)

            lower_title = issue_title.lower()

            has_include = any(
                keyword.lower() in lower_title
                for keyword in INCLUDE_ISSUE_KEYWORDS
            )

            has_exclude = any(
                keyword.lower() in lower_title
                for keyword in EXCLUDE_ISSUE_KEYWORDS
            )

            if has_include and has_exclude:
                decision = "MIXED"
            elif has_include:
                decision = "KEEP"
            else:
                decision = "SKIP"

            issues.append({
                "issue_title": issue_title,
                "issue_url": issue_url,
                "decision": decision,
                "page_style": page_style,
            })

        return issues
    

    def parse_article(
        self,
        article_url: str,
        issue_title: str = "",
        track_name: str = "",
    ) -> dict:
        """
        请求并解析一篇 AAAI article 页面。
        """
        if self.request_delay > 0:
            time.sleep(self.request_delay)

        response = self.session.get(
            article_url,
            timeout=self.timeout,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        return self._article_soup_to_paper_data(
            soup=soup,
            article_url=article_url,
            issue_title=issue_title,
            track_name=track_name,
        )
    

    def collect_article_contexts(self) -> list[dict]:
        """
        遍历某一年的全部 issue，汇总需要爬取的论文链接。

        这里只访问年度页和 issue 页，不访问单篇 article 页面。
        """
        issues = self.parse_year_issues()

        all_articles = []
        seen_article_urls = set()

        for index, issue in enumerate(issues, start=1):
            issue_title = issue["issue_title"]
            issue_url = issue["issue_url"]
            decision = issue["decision"]

            if decision == "SKIP":
                print(f"⏭️ Skip AAAI issue: {issue_title}")
                continue

            print(
                f"📚 Parsing issue {index}/{len(issues)}: "
                f"{issue_title}"
            )

            # articles = self.parse_issue(
            #     issue_url=issue_url,
            #     issue_title=issue_title,
            # )
            page_style = issue.get("page_style", "ojs")

            if page_style == "ojs":
                articles = self.parse_issue(
                    issue_url=issue_url,
                    issue_title=issue_title,
                )

            elif page_style == "legacy_wordpress":
                articles = self.parse_legacy_issue(
                    issue_url=issue_url,
                    issue_title=issue_title,
                )

            else:
                raise ValueError(
                    f"Unsupported AAAI page_style: {page_style}"
                )


            for article in articles:
                article_url = article["article_url"]

                if article_url in seen_article_urls:
                    continue

                seen_article_urls.add(article_url)
                all_articles.append(article)

            print(
                f"   kept articles in issue: {len(articles)}, "
                f"total unique articles: {len(all_articles)}"
            )

        return all_articles

    def _article_soup_to_paper_data(
        self,
        soup: BeautifulSoup,
        article_url: str,
        issue_title: str,
        track_name: str,
    ) -> dict:
        """
        将 article 页面的 meta 标签转换为 paper_data。
        """
        paper_data = copy.deepcopy(DEFAULT_PAPER_FIELDS)

        title = self._get_first_meta(
            soup,
            ["citation_title", "DC.Title"],
        )

        abstract = self._get_first_meta(
            soup,
            ["citation_abstract", "DC.Description"],
        )

        authors = self._extract_authors(soup)

        volume = self._get_first_meta(
            soup,
            ["citation_volume", "DC.Source.Volume"],
        )

        issue = self._get_first_meta(
            soup,
            ["citation_issue", "DC.Source.Issue"],
        )

        first_page = self._get_first_meta(
            soup,
            ["citation_firstpage"],
        )

        last_page = self._get_first_meta(
            soup,
            ["citation_lastpage"],
        )

        pages = self._build_pages(
            first_page=first_page,
            last_page=last_page,
            fallback=self._get_first_meta(
                soup,
                ["DC.Identifier.pageNumber"],
            ),
        )

        doi = self._get_first_meta(
            soup,
            ["citation_doi", "DC.Identifier.DOI"],
        )

        pdf_url = self._get_first_meta(
            soup,
            ["citation_pdf_url"],
        )

        published = self._get_first_meta(
            soup,
            ["citation_date", "DC.Date.issued"],
        )
        published = self._normalize_date(published)

        article_id = self._get_first_meta(
            soup,
            ["DC.Identifier"],
        )

        meta_article_url = self._get_first_meta(
            soup,
            ["DC.Identifier.URI", "citation_abstract_html_url"],
        )

        if meta_article_url:
            article_url = meta_article_url

        meta_track_name = self._get_first_meta(
            soup,
            ["DC.Type.articleType"],
        )

        if meta_track_name:
            track_name = meta_track_name

        # track_type = self._parse_track_type(track_name)
        track_type = self._parse_track_type(
            track_name=track_name,
            issue_title=issue_title,
        )

        paper_data.update({
            "_id": paper_id_from_title(title),

            "title": title,
            "authors": authors,
            "abstract": abstract,

            "accepted_by": f"AAAI {self.year}",

            "aaai_obj": {
                "year": self.year,
                "conference_number": self.config["conference_number"],
                "volume": volume,
                "issue": issue,
                "issue_title": issue_title,
                "track_type": track_type,
                "track_name": track_name,
                "article_id": article_id,
                "article_url": article_url,
                "official_pdf_url": pdf_url,
                "doi": doi,
                "pages": pages,
                "published": published,
            },

            "base_urls": {
                "official_url": article_url,
                "official_pdf_url": pdf_url,
            },

            "more_urls": {
                "doi_url": f"https://doi.org/{doi}" if doi else "",
            },
        })

        return paper_data

    @staticmethod
    def _get_meta_values(soup: BeautifulSoup, name: str) -> list[str]:
        """
        获取指定 meta name 的所有 content 值。

        meta name 大小写不敏感。
        """
        values = []

        for meta in soup.find_all("meta"):
            meta_name = meta.get("name") or meta.get("property") or ""

            if meta_name.lower() != name.lower():
                continue

            content = meta.get("content", "")
            content = AAAIOfficialCrawler._clean_text(content)

            if content:
                values.append(content)

        return values

    @classmethod
    def _get_first_meta(
        cls,
        soup: BeautifulSoup,
        candidate_names: list[str],
    ) -> str:
        """
        按候选字段顺序返回第一个非空 meta 值。
        """
        for name in candidate_names:
            values = cls._get_meta_values(soup, name)

            if values:
                return values[0]

        return ""

    @classmethod
    def _extract_authors(cls, soup: BeautifulSoup) -> list[dict]:
        """
        按页面中的出现顺序配对作者和单位。

        一般情况下：
            citation_author
            citation_author_institution
            citation_author
            citation_author_institution
            ...

        如果单位数量不足，则剩余作者的 affiliation 保持为空。
        """
        author_names = cls._get_meta_values(
            soup,
            "citation_author",
        )

        affiliations = cls._get_meta_values(
            soup,
            "citation_author_institution",
        )

        authors = []

        for index, author_name in enumerate(author_names):
            affiliation = (
                affiliations[index]
                if index < len(affiliations)
                else ""
            )

            authors.append({
                "name": author_name,
                "affiliation": affiliation,
                "homepage": "",
            })

        return authors

    @classmethod
    def _extract_legacy_authors(
        cls,
        soup: BeautifulSoup,
    ) -> list[dict]:
        """
        解析 AAAI 2022 旧版 WordPress 论文页中的作者和单位。

        页面结构通常为：

            <div class="author-output">
                <p class="bold">Author Name</p>
                <p>Affiliation</p>
                <br/>
                ...
            </div>
        """
        author_container = soup.find(
            "div",
            class_="author-output",
        )

        if author_container is None:
            return []

        paragraph_nodes = author_container.find_all(
            "p",
            recursive=False,
        )

        authors = []
        index = 0

        while index < len(paragraph_nodes):
            author_node = paragraph_nodes[index]

            # 作者名对应 p.bold
            classes = author_node.get("class", [])

            if "bold" not in classes:
                index += 1
                continue

            author_name = cls._clean_text(
                author_node.get_text(" ", strip=True)
            )

            affiliation = ""

            # 通常紧跟作者名的下一个 p 是单位
            if index + 1 < len(paragraph_nodes):
                affiliation_node = paragraph_nodes[index + 1]
                affiliation_classes = affiliation_node.get("class", [])

                if "bold" not in affiliation_classes:
                    affiliation = cls._clean_text(
                        affiliation_node.get_text(" ", strip=True)
                    )

            if author_name:
                authors.append({
                    "name": author_name,
                    "affiliation": affiliation,
                    "homepage": "",
                })

            index += 2

        return authors


    @classmethod
    def _get_legacy_section_text(
        cls,
        soup: BeautifulSoup,
        heading_name: str,
    ) -> str:
        """
        获取 AAAI 2022 旧版论文页中某个 h4 区块的文本。

        例如：
            Track -> AAAI Technical Track on ...
            Abstract -> 论文摘要
            DOI -> 10.1609/...
        """
        target_heading = None

        for heading in soup.find_all("h4"):
            heading_text = cls._clean_text(
                heading.get_text(" ", strip=True)
            ).rstrip(":")

            if heading_text.lower() == heading_name.lower().rstrip(":"):
                target_heading = heading
                break

        if target_heading is None:
            return ""

        contents = []

        for sibling in target_heading.next_siblings:
            if isinstance(sibling, Tag) and sibling.name == "h4":
                break

            if isinstance(sibling, NavigableString):
                text = cls._clean_text(str(sibling))
            elif isinstance(sibling, Tag):
                text = cls._clean_text(
                    sibling.get_text(" ", strip=True)
                )
            else:
                text = ""

            if text:
                contents.append(text)

        return cls._clean_text(" ".join(contents))



    def parse_legacy_issue(
        self,
        issue_url: str,
        issue_title: str = "",
    ) -> list[dict]:
        """
        解析 AAAI 2022 旧版 WordPress 分卷页面。

        返回需要保留的论文上下文：
        - issue_title
        - issue_url
        - track_name
        - track_type
        - article_url
        - official_pdf_url
        - pages
        """
        response = self.session.get(
            issue_url,
            timeout=self.timeout,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        if not issue_title:
            title_node = soup.find("h1", class_="archive-title")

            if title_node:
                issue_title = self._clean_text(
                    title_node.get_text(" ", strip=True)
                )

        articles = []
        seen_article_urls = set()

        for track_container in soup.find_all(
            "div",
            class_="track-wrap",
        ):
            track_heading = track_container.find("h2")

            if track_heading is None:
                continue

            track_name = self._clean_text(
                track_heading.get_text(" ", strip=True)
            )

            if not track_name:
                continue

            if not self._should_keep_section(track_name):
                print(f"⏭️ Skip AAAI legacy section: {track_name}")
                continue

            track_type = self._parse_track_type(
                track_name=track_name,
                issue_title=issue_title,
            )

            for paper_node in track_container.find_all(
                "li",
                class_="paper-wrap",
            ):
                title_heading = paper_node.find("h5")

                if title_heading is None:
                    continue

                article_link = title_heading.find(
                    "a",
                    href=True,
                )

                if article_link is None:
                    continue

                article_url = urljoin(
                    issue_url,
                    article_link["href"],
                )

                if "/papers/" not in article_url:
                    continue

                if article_url in seen_article_urls:
                    continue

                seen_article_urls.add(article_url)

                title = self._clean_text(
                    article_link.get_text(" ", strip=True)
                )

                pdf_url = ""

                for link in paper_node.find_all("a", href=True):
                    href = urljoin(issue_url, link["href"])
                    link_text = self._clean_text(
                        link.get_text(" ", strip=True)
                    )

                    if (
                        ".pdf" in href.lower()
                        or link_text.lower() == "pdf"
                    ):
                        pdf_url = href
                        break

                paper_text = self._clean_text(
                    paper_node.get_text(" ", strip=True)
                )

                page_match = re.search(
                    r"\b(\d+)\s*-\s*(\d+)\b",
                    paper_text,
                )

                pages = ""

                if page_match:
                    pages = (
                        f"{page_match.group(1)}-"
                        f"{page_match.group(2)}"
                    )

                articles.append({
                    "issue_title": issue_title,
                    "issue_url": issue_url,
                    "page_style": "legacy_wordpress",
                    "track_name": track_name,
                    "track_type": track_type,
                    "title": title,
                    "article_url": article_url,
                    "official_pdf_url": pdf_url,
                    "pages": pages,
                })

        return articles


    def parse_legacy_article(
        self,
        article_url: str,
        issue_title: str = "",
        track_name: str = "",
        official_pdf_url: str = "",
        pages: str = "",
    ) -> dict:
        """
        解析 AAAI 2022 旧版 WordPress 论文详情页，
        并转换为统一的 paper_data。
        """
        if self.request_delay > 0:
            time.sleep(self.request_delay)

        response = self.session.get(
            article_url,
            timeout=self.timeout,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        paper_data = copy.deepcopy(DEFAULT_PAPER_FIELDS)

        # 标题优先从 h1 获取，meta 作为备用
        title_node = soup.find("h1")
        title = (
            self._clean_text(title_node.get_text(" ", strip=True))
            if title_node
            else ""
        )

        if not title:
            title = self._get_first_meta(
                soup,
                ["DC.title", "citation_title"],
            )

        authors = self._extract_legacy_authors(soup)

        abstract = self._get_legacy_section_text(
            soup,
            "Abstract",
        )

        doi = self._get_legacy_section_text(
            soup,
            "DOI",
        )

        page_track_name = self._get_legacy_section_text(
            soup,
            "Track",
        )

        if page_track_name:
            track_name = page_track_name

        proceedings_text = self._get_legacy_section_text(
            soup,
            "Proceedings",
        )

        issue_text = self._get_legacy_section_text(
            soup,
            "Issue",
        )

        # 例如：
        # No. 1: AAAI-22 Technical Tracks 1
        issue_match = re.search(
            r"No\.?\s*(\d+)",
            issue_title or proceedings_text,
            re.IGNORECASE,
        )
        issue = issue_match.group(1) if issue_match else ""

        # 例如：
        # Proceedings of the AAAI Conference on Artificial Intelligence, 36
        volume_match = re.search(
            r",\s*(\d+)\s*$",
            issue_text,
        )
        volume = volume_match.group(1) if volume_match else ""

        # 页面 meta 通常只提供年份，例如 2022
        published = self._get_first_meta(
            soup,
            ["DC.issued", "DC.Date.issued"],
        )

        # 如果分卷页没有传入 PDF，则从 Downloads 区块寻找
        if not official_pdf_url:
            for link in soup.find_all("a", href=True):
                href = urljoin(article_url, link["href"])
                link_text = self._clean_text(
                    link.get_text(" ", strip=True)
                )

                if (
                    ".pdf" in href.lower()
                    or link_text.lower() == "download pdf"
                ):
                    official_pdf_url = href
                    break

        track_type = self._parse_track_type(
            track_name=track_name,
            issue_title=issue_title,
        )

        # DOI 示例：10.1609/aaai.v36i1.19873
        article_id = ""

        if doi:
            article_id = doi.rsplit(".", 1)[-1]

        paper_data.update({
            "_id": paper_id_from_title(title),

            "title": title,
            "authors": authors,
            "abstract": abstract,

            "accepted_by": f"AAAI {self.year}",

            "aaai_obj": {
                "year": self.year,
                "conference_number": self.config["conference_number"],
                "volume": volume,
                "issue": issue,
                "issue_title": issue_title,
                "track_type": track_type,
                "track_name": track_name,
                "article_id": article_id,
                "article_url": article_url,
                "official_pdf_url": official_pdf_url,
                "doi": doi,
                "pages": pages,
                "published": published,
            },

            "base_urls": {
                "official_url": article_url,
                "official_pdf_url": official_pdf_url,
            },

            "more_urls": {
                "doi_url": f"https://doi.org/{doi}" if doi else "",
            },
        })

        return paper_data


    @staticmethod
    def _parse_track_type(
        track_name: str,
        issue_title: str = "",
    ) -> str:
        """
        判断 AAAI Track 类型。

        优先根据 issue_title 判断，因为部分 AAAI OJS 页面存在：
        issue 标题写 Special Track，
        但内部 section 错写为 Technical Track 的情况。
        """
        lower_issue_title = issue_title.lower()
        lower_track_name = track_name.lower()

        if "special track" in lower_issue_title:
            return "special"

        if "special track" in lower_track_name:
            return "special"

        if "technical track" in lower_track_name:
            return "technical"

        return ""

    @staticmethod
    def _build_pages(
        first_page: str,
        last_page: str,
        fallback: str = "",
    ) -> str:
        if first_page and last_page:
            return f"{first_page}-{last_page}"

        if first_page:
            return first_page

        return fallback

    @staticmethod
    def _normalize_date(value: str) -> str:
        """
        将 2026/03/17 统一为 2026-03-17。
        """
        if not value:
            return ""

        return value.replace("/", "-")

    @staticmethod
    def _clean_text(value) -> str:
        """
        清理换行和多余空格。
        """
        if not value:
            return ""

        return re.sub(r"\s+", " ", str(value)).strip()
