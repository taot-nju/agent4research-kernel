"""
Research Topic 论文召回统一接口。

当前 MVP 使用 MongoDB 词法召回；
未来可以增加 BM25、向量检索或混合检索实现。
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TopicCandidate:
    """Research Topic 召回的一篇候选论文。"""

    paper_id: str
    title: str
    accepted_by: str
    score: float
    matched_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.paper_id.strip():
            raise ValueError(
                "paper_id 不能为空"
            )

        if not self.title.strip():
            raise ValueError(
                "title 不能为空"
            )

        if self.score < 0:
            raise ValueError(
                "score 不能小于 0"
            )

    def to_dict(self) -> dict:
        """转换为普通字典。"""

        return asdict(self)


class TopicRetriever(ABC):
    """所有 Topic 论文召回器必须实现的接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """召回器稳定名称。"""

        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        """召回策略版本。"""

        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        *,
        topic: str,
        limit: int,
    ) -> list[TopicCandidate]:
        """返回按相关度降序排列的候选论文。"""

        raise NotImplementedError
