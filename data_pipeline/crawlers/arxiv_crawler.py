"""
基于 arXiv 官方 Python SDK 的爬虫。

目标：
1. 支持按 arXiv category 爬取；
2. 支持指定日期范围；
3. 未指定日期时默认爬取当天；
4. 一篇论文解析完成后立即 yield；
5. 输出结构尽量贴合 paper_schema.py。
"""

import copy
import re
from datetime import datetime, timezone

import arxiv

from ai4research.data_pipeline.crawlers.base import BaseCrawler
from ai4research.data_pipeline.schemas.paper_schema import DEFAULT_PAPER_FIELDS
from ai4research.data_pipeline.source_configs.arxiv_spec_config import CATEGORIES
from ai4research.data_pipeline.utils.text_utils import paper_id_from_title


class ArxivCrawler(BaseCrawler):
    """
    使用 arXiv 官方 SDK 爬取论文。
    """

    # # 调试用：固定50篇/每类，避免爬太多数据
    # def __init__(self, categories=None, page_size=100, delay_seconds=3, num_retries=5, max_results=50):
    #     self.categories = categories or CATEGORIES
    #     self.max_results = max_results
    #     self.client = arxiv.Client(
    #         page_size=page_size,
    #         delay_seconds=delay_seconds,
    #         num_retries=num_retries,
    #     )

    def __init__(
        self,
        categories=None,
        page_size=100,
        delay_seconds=3,
        num_retries=5,
        max_results=None,
    ):
        """
        max_results:
            None 表示不限制结果数量，适合正式爬取；
            整数表示最多爬取多少篇，适合调试，例如 max_results=50。
        """
        self.categories = categories or CATEGORIES
        self.max_results = max_results
        self.client = arxiv.Client(
            page_size=page_size,
            delay_seconds=delay_seconds,
            num_retries=num_retries,
        )



    def crawl(self, start_date=None, end_date=None):
        """
        start_date / end_date: YYYY-MM-DD

        如果都不传，默认爬取 UTC 当天。
        注意：arXiv API 的 submittedDate 使用 UTC 时间。
        """
        if start_date is None and end_date is None:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            start_date = end_date = today

        start_query_time = start_date.replace("-", "") + "000000"
        end_query_time = end_date.replace("-", "") + "235959"

        for category in self.categories:
            query = f"cat:{category} AND submittedDate:[{start_query_time} TO {end_query_time}]"

            print(f"🚀 Crawling arXiv category={category}, date={start_date} ~ {end_date}")
            print(f"🔎 Query: {query}")

            search = arxiv.Search(
                query=query,
                max_results=self.max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )

            seen_ids = set()

            for result in self.client.results(search):
                paper_data = self._result_to_paper_data(result)

                if paper_data["_id"] in seen_ids:
                    continue

                seen_ids.add(paper_data["_id"])

                # category 表示“这篇论文是从哪个入口类别被发现的”
                yield paper_data, category

    def _result_to_paper_data(self, result):
        """
        将 arxiv.Result 转换为符合 paper_schema.py 的 paper_data。
        """
        paper_data = copy.deepcopy(DEFAULT_PAPER_FIELDS)

        title = self._clean_text(result.title)
        abstract = self._clean_text(result.summary)

        arxiv_id_with_version = result.get_short_id()
        arxiv_id = self._strip_arxiv_version(arxiv_id_with_version)

        authors = [
            {
                "name": author.name,
                "affiliation": "",
                "homepage": "",
            }
            for author in result.authors
        ]

        arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
        arxiv_pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

        published_date = self._date_to_str(result.published)
        updated_date = self._date_to_str(result.updated)

        paper_data.update({
            "_id": paper_id_from_title(title),

            "title": title,
            "authors": authors,
            "abstract": abstract,

            "accepted_by": "arXiv",

            "arxiv_obj": {
                "arxiv_id": arxiv_id,
                "arxiv_url": arxiv_url,
                "arxiv_pdf_url": arxiv_pdf_url,
                "arxiv_categories": list(result.categories),
                "comment": result.comment or "",
                "doi": result.doi or "",
                "submission_history": [
                    {
                        "version": arxiv_id_with_version.replace(arxiv_id, "") or "v1",
                        "date": published_date,
                    }
                ],
            },

            "base_urls": {
                "arxiv_url": arxiv_url,
                "arxiv_pdf_url": arxiv_pdf_url,
            },
        })

        # 如果 updated 和 published 不同，记录一个 latest 版本信息。
        # 注意：arXiv API 不完整提供所有历史版本，这里先记录可直接获得的信息。
        if updated_date and updated_date != published_date:
            paper_data["arxiv_obj"]["submission_history"].append({
                "version": "latest",
                "date": updated_date,
            })

        return paper_data

    @staticmethod
    def _clean_text(text):
        """
        清理 arXiv 返回文本中的多余空白。
        """
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _strip_arxiv_version(arxiv_id):
        """
        去掉 arXiv id 末尾的版本号。
        例如：
            2401.12345v2 -> 2401.12345
        """
        return re.sub(r"v\d+$", "", arxiv_id)

    @staticmethod
    def _date_to_str(dt):
        """
        datetime -> YYYY-MM-DD
        """
        if dt is None:
            return ""
        return dt.strftime("%Y-%m-%d")