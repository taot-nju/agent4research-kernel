"""
基于 openreview-py 的 OpenReview 爬虫。

目标：
1. 按 venue/year 爬取 OpenReview 上的论文；
2. 将 OpenReview note 转换为 paper_schema.py 对应的 paper_data；
3. 每篇论文转换完成后 yield；
4. 后续由 pipeline 负责写入 MongoDB。
"""

import copy
import re

import openreview

from ai4research.data_pipeline.crawlers.base import BaseCrawler
from ai4research.data_pipeline.schemas.paper_schema import DEFAULT_PAPER_FIELDS
from ai4research.data_pipeline.source_configs.openreview_gen_config import get_openreview_config
from ai4research.data_pipeline.utils.text_utils import paper_id_from_title


class OpenReviewCrawler(BaseCrawler):
    """
    使用 OpenReview 官方 Python 客户端爬取论文。
    """

    BASE_URL = "https://openreview.net"
    API2_URL = "https://api2.openreview.net"

    def __init__(self, venue: str, year: int, max_results=None):
        """
        :param venue: 会议名称，例如 "ICLR"
        :param year: 年份，例如 2026
        :param max_results: 调试用，最多处理多少篇；None 表示不限制
        """
        self.venue = venue
        self.year = year
        self.max_results = max_results

        self.config = get_openreview_config(venue, year)
        if self.config is None:
            raise ValueError(f"No OpenReview config found for {venue} {year}")

        self.venue_id = self.config["venue_id"]

        # self.client = openreview.api.OpenReviewClient(baseurl=self.API2_URL)

        self.api_version = self.config.get("api_version", "v2")

        if self.api_version == "v2":
            self.client = openreview.api.OpenReviewClient(baseurl=self.API2_URL)
        elif self.api_version == "v1":
            self.client = openreview.Client(baseurl="https://api.openreview.net")
        else:
            raise ValueError(f"Unsupported OpenReview api_version: {self.api_version}")


    def _fetch_notes(self):
        """
        根据 api_version 和 max_results 获取 OpenReview notes。

        v2:
            - 调试模式：get_notes(limit=max_results)
            - 正式模式：get_all_notes()

        v1:
            - 调试模式：get_notes(limit=max_results)
            - 正式模式：分页 get_notes(limit=1000, offset=...)
        """
        query_type = self.config.get("query_type", "content_venueid")

        if query_type != "content_venueid":
            raise ValueError(f"Unsupported OpenReview query_type: {query_type}")

        query_kwargs = {
            "content": {"venueid": self.venue_id}
        }

        # 调试模式：只取 max_results 条
        if self.max_results is not None:
            notes = self.client.get_notes(
                **query_kwargs,
                limit=self.max_results,
                offset=0,
            )
            print(
                f"📄 Notes fetched from OpenReview: "
                f"{len(notes)} / max_results={self.max_results}"
            )
            return notes

        # 正式模式：v2 可以直接 get_all_notes
        if self.api_version == "v2":
            notes = self.client.get_all_notes(**query_kwargs)
            print(f"📄 Total notes fetched from OpenReview: {len(notes)}")
            return notes

        # 正式模式：v1 需要分页，单次 limit <= 1000
        if self.api_version == "v1":
            limit = 1000
            offset = 0
            all_notes = []

            while True:
                notes = self.client.get_notes(
                    **query_kwargs,
                    limit=limit,
                    offset=offset,
                )

                print(f"📄 Fetched OpenReview v1 notes: offset={offset}, num={len(notes)}")

                if not notes:
                    break

                all_notes.extend(notes)

                if len(notes) < limit:
                    break

                offset += limit

            print(f"📄 Total notes fetched from OpenReview: {len(all_notes)}")
            return all_notes

        raise ValueError(f"Unsupported OpenReview api_version: {self.api_version}")


    def crawl(self, start_date=None, end_date=None):
        """
        OpenReview 不是按日期范围爬取，因此 start_date/end_date 暂时不用。

        yield:
            paper_data, venue_year
        """
        print(f"🚀 Crawling OpenReview venue={self.venue} year={self.year}")
        print(f"🔎 venue_id: {self.venue_id}")

        # notes = self.client.get_all_notes(
        #     content={"venueid": self.venue_id}
        # )

        # print(f"📄 Total notes fetched from OpenReview: {len(notes)}")

        # if self.max_results is not None:
        #     notes = notes[:self.max_results]


        # if self.max_results is not None:
        #     notes = self.client.get_notes(
        #         content={"venueid": self.venue_id},
        #         limit=self.max_results,
        #         offset=0,
        #     )
        #     print(f"📄 Notes fetched from OpenReview: {len(notes)} / max_results={self.max_results}")
        # else:
        #     notes = self.client.get_all_notes(
        #         content={"venueid": self.venue_id}
        #     )
        #     print(f"📄 Total notes fetched from OpenReview: {len(notes)}")
        notes = self._fetch_notes()


        # venue_year = f"{self.venue} {self.year}"

        # for note in notes:
        #     paper_data = self._note_to_paper_data(note)
        #     yield paper_data, venue_year

        

        accepted_venues = self.config.get("accepted_venues")

        if accepted_venues:
            before_count = len(notes)

            filtered_notes = []
            for note in notes:
                venue_value = self._get_content_value(note, "venue")
                if venue_value in accepted_venues:
                    filtered_notes.append(note)

            notes = filtered_notes

            print(
                f"🧹 Filtered accepted papers by venue: "
                f"{len(notes)} / {before_count}"
            )

        venue_year = f"{self.venue} {self.year}"

        for note in notes:
            paper_data = self._note_to_paper_data(note)
            yield paper_data, venue_year



    def _note_to_paper_data(self, note):
        """
        将 OpenReview note 转换为符合 paper_schema.py 的 paper_data。
        """
        paper_data = copy.deepcopy(DEFAULT_PAPER_FIELDS)

        title = self._clean_text(self._get_content_value(note, "title"))
        abstract = self._clean_text(self._get_content_value(note, "abstract"))

        authors_raw = self._get_content_value(note, "authors")
        authors = self._parse_authors(authors_raw)

        keywords = self._get_content_value(note, "keywords")
        if not isinstance(keywords, list):
            keywords = []

        venue_text = self._clean_text(self._get_content_value(note, "venue"))
        venueid = self._clean_text(self._get_content_value(note, "venueid"))
        paperhash = self._clean_text(self._get_content_value(note, "paperhash"))
        tldr = self._clean_text(self._get_content_value(note, "TLDR"))
        primary_area = self._clean_text(self._get_content_value(note, "primary_area"))

        pdf_path = self._clean_text(self._get_content_value(note, "pdf"))
        pdf_url = self._to_openreview_url(pdf_path)

        supplementary_path = self._clean_text(
            self._get_content_value(note, "supplementary_material")
        )
        supplementary_url = self._to_openreview_url(supplementary_path)

        forum_url = f"{self.BASE_URL}/forum?id={note.forum}"

        accept_type = self._parse_accept_type(venue_text)

        paper_data.update({
            "_id": paper_id_from_title(title),

            "title": title,
            "authors": authors,
            "abstract": abstract,
            "keywords": keywords,

            "accepted_by": f"{self.venue} {self.year}",

            "openreview_obj": {
                "note_id": note.id,
                "forum_id": note.forum,
                "number": str(getattr(note, "number", "")),
                "venue": venue_text,
                "venueid": venueid,
                "paperhash": paperhash,
                "pdf_url": pdf_url,
                "forum_url": forum_url,
                "keywords": keywords,
                "tldr": tldr,
                "primary_area": primary_area,
                "accept_type": accept_type,
            },

            "base_urls": {
                "openreview_forum_url": forum_url,
                "openreview_pdf_url": pdf_url,
            },

            "more_urls": {
                "supplementary_material_url": supplementary_url,
            },
        })

        return paper_data

    @staticmethod
    def _get_content_value(note, key, default=""):
        """
        OpenReview API2 的 content 字段通常是：
            {"title": {"value": "..."}}

        但为了兼容不同版本，也支持直接返回普通值。
        """
        value = note.content.get(key, default)

        if isinstance(value, dict):
            return value.get("value", default)

        return value

    @staticmethod
    def _parse_authors(authors_raw):
        """
        将 OpenReview authors 转成 schema 里的 authors 结构。
        """
        if not isinstance(authors_raw, list):
            return []

        return [
            {
                "name": str(author),
                "affiliation": "",
                "homepage": "",
            }
            for author in authors_raw
        ]

    @classmethod
    def _to_openreview_url(cls, path):
        """
        OpenReview 返回的 pdf 通常是相对路径：
            /pdf/xxx.pdf

        需要转成：
            https://openreview.net/pdf/xxx.pdf
        """
        if not path:
            return ""

        if path.startswith("http://") or path.startswith("https://"):
            return path

        if path.startswith("/"):
            return cls.BASE_URL + path

        return cls.BASE_URL + "/" + path

    # @staticmethod
    # def _parse_accept_type(venue_text):
    #     """
    #     从 venue 字段中解析录用类型。

    #     例如：
    #         ICLR 2026 Poster -> Poster
    #         ICLR 2026 Oral -> Oral
    #         ICLR 2026 Spotlight -> Spotlight
    #     """
    #     if not venue_text:
    #         return ""

    #     parts = venue_text.split()
    #     if len(parts) <= 2:
    #         return ""

    #     return " ".join(parts[2:])

    def _parse_accept_type(self, venue_text: str) -> str:
        """
        从 OpenReview venue 字段中解析录用类型。

        示例：
        - ICLR 2026 Poster -> Poster
        - ICLR 2026 Oral -> Oral
        - ICLR 2024 spotlight -> Spotlight
        - ICLR 2023 poster -> Poster
        - ICLR 2023 notable top 25% -> Notable Top 25%
        - ICLR 2023 notable top 5% -> Notable Top 5%
        """
        if not venue_text:
            return ""

        text = venue_text.strip()
        lower_text = text.lower()

        known_types = [
            ("notable top 25%", "Notable Top 25%"),
            ("notable top 5%", "Notable Top 5%"),
            ("spotlight", "Spotlight"),
            ("oral", "Oral"),
            ("poster", "Poster"),
        ]

        for pattern, normalized in known_types:
            if pattern in lower_text:
                return normalized

        # fallback：保留最后一个词，但首字母大写
        parts = text.split()
        if not parts:
            return ""

        return parts[-1].capitalize()

    

    @staticmethod
    def _clean_text(text):
        """
        清理多余空白。
        """
        if not text:
            return ""

        return re.sub(r"\s+", " ", str(text)).strip()