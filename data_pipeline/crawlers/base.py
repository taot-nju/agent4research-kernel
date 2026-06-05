from abc import ABC, abstractmethod


class BaseCrawler(ABC):
    """
    抽象语义：
    - 一个 crawler = 一个“论文流”
    - crawl 返回的是 generator，而不是 list
    - 每次 yield 一篇论文及其来源上下文
    """

    @abstractmethod
    def crawl(self, start_date=None, end_date=None):
        """
        yield:
            paper_data, source_context

        例如：
            arXiv crawler:
                yield paper_data, category

            conference crawler:
                yield paper_data, venue_year
        """
        pass