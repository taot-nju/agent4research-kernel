"""
MongoDB Research Topic 词法召回器。

第一版通过标题、摘要、关键词和标签进行候选召回，
再在 Python 中计算可解释的相关度分数。
"""

import re
from typing import Any

from ai4research.data_pipeline.db_settings.mongo_client import (
    MongoDBClient,
)
from ai4research.data_pipeline.utils.text_utils import (
    normalize_title,
)
from ai4research.research_pipeline.retrieval.base import (
    TopicCandidate,
    TopicRetriever,
)


RETRIEVER_VERSION = "2"

SEARCH_FIELDS = (
    "title",
    "abstract",
    "keywords",
    "tags",
    "openreview_obj.keywords",
    "openreview_obj.tldr",
    "icml_official_obj.keywords",
)

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def _value_to_text(value: Any) -> str:
    """将字符串或字符串列表转换为统一文本。"""

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        return " ".join(
            str(item)
            for item in value
            if item is not None
        )

    return ""


def _get_nested_value(
    document: dict[str, Any],
    field_path: str,
) -> Any:
    """读取 MongoDB 文档中的点路径字段。"""

    current: Any = document

    for key in field_path.split("."):
        if not isinstance(current, dict):
            return None

        current = current.get(key)

        if current is None:
            return None

    return current


def _extract_topic_tokens(
    topic: str,
) -> tuple[str, ...]:
    """提取用于检索的有效 Topic 词项。"""

    normalized_topic = normalize_title(
        topic
    )

    if not normalized_topic:
        raise ValueError(
            "research topic 不能为空"
        )

    all_tokens = normalized_topic.split()

    meaningful_tokens = [
        token
        for token in all_tokens
        if token not in STOPWORDS
        and len(token) >= 2
    ]

    tokens = (
        meaningful_tokens
        if meaningful_tokens
        else all_tokens
    )

    # 去重并保持原始顺序。
    return tuple(
        dict.fromkeys(tokens)
    )


def _build_token_condition(
    token: str,
) -> dict[str, Any]:
    """构造一个词项在所有检索字段中的查询条件。"""

    pattern = re.compile(
        re.escape(token),
        re.IGNORECASE,
    )

    return {
        "$or": [
            {
                field: {
                    "$regex": pattern,
                }
            }
            for field in SEARCH_FIELDS
        ]
    }


class MongoLexicalTopicRetriever(
    TopicRetriever
):
    """基于 MongoDB 字段的可解释词法召回器。"""

    def __init__(
        self,
        collection=None,
        *,
        candidate_pool_size: int = 1000,
    ) -> None:
        if candidate_pool_size <= 0:
            raise ValueError(
                "candidate_pool_size 必须大于 0"
            )

        self._collection = collection
        self._candidate_pool_size = (
            candidate_pool_size
        )

    @property
    def name(self) -> str:
        return "mongo-lexical-topic-retriever"

    @property
    def version(self) -> str:
        return RETRIEVER_VERSION

    def _get_collection(self):
        if self._collection is None:
            self._collection = (
                MongoDBClient.get_collection()
            )

        return self._collection

    @staticmethod
    def _score_document(
        *,
        document: dict[str, Any],
        normalized_topic: str,
        tokens: tuple[str, ...],
    ) -> tuple[float, tuple[str, ...]]:
        """计算一篇论文的词法相关度分数。"""

        normalized_fields = {
            field: normalize_title(
                _value_to_text(
                    _get_nested_value(
                        document,
                        field,
                    )
                )
            )
            for field in SEARCH_FIELDS
        }

        score = 0.0
        matched_fields: set[str] = set()
        matched_tokens: set[str] = set()

        title_text = normalized_fields[
            "title"
        ]
        abstract_text = normalized_fields[
            "abstract"
        ]

        if (
            normalized_topic
            and normalized_topic in title_text
        ):
            score += 12.0
            matched_fields.add("title")

        if (
            normalized_topic
            and normalized_topic
            in abstract_text
        ):
            score += 6.0
            matched_fields.add("abstract")

        for token in tokens:
            if token in title_text:
                score += 4.0
                matched_fields.add("title")
                matched_tokens.add(token)

            if token in abstract_text:
                score += 1.5
                matched_fields.add("abstract")
                matched_tokens.add(token)

            for field in (
                "keywords",
                "tags",
                "openreview_obj.keywords",
                "openreview_obj.tldr",
                "icml_official_obj.keywords",
            ):
                if token in normalized_fields[field]:
                    score += 2.5
                    matched_fields.add(field)
                    matched_tokens.add(token)

        if tokens:
            coverage = (
                len(matched_tokens)
                / len(tokens)
            )
            score += coverage * 5.0

        # pdf_status = str(
        #     _get_nested_value(
        #         document,
        #         "pdf_asset.status",
        #     )
        #     or ""
        # )
        # document_status = str(
        #     _get_nested_value(
        #         document,
        #         "document_asset.status",
        #     )
        #     or ""
        # )

        # # 少量复用加分，不应压过主题相关性。
        # if pdf_status == "success":
        #     score += 1.0
        #     matched_fields.add(
        #         "pdf_asset.status"
        #     )

        # if document_status == "success":
        #     score += 2.0
        #     matched_fields.add(
        #         "document_asset.status"
        #     )

        return (
            score,
            tuple(sorted(matched_fields)),
        )

    def search(
        self,
        *,
        topic: str,
        limit: int,
    ) -> list[TopicCandidate]:
        """召回并排序与 Topic 相关的论文。"""

        normalized_topic = normalize_title(
            topic
        )
        tokens = _extract_topic_tokens(
            topic
        )

        if limit <= 0:
            raise ValueError(
                "limit 必须大于 0"
            )

        projection = {
            "title": 1,
            "abstract": 1,
            "accepted_by": 1,
            "keywords": 1,
            "tags": 1,
            "openreview_obj.keywords": 1,
            "openreview_obj.tldr": 1,
            "icml_official_obj.keywords": 1,
        }

        strict_query = {
            "$and": [
                _build_token_condition(token)
                for token in tokens
            ]
        }

        collection = self._get_collection()

        documents = list(
            collection.find(
                strict_query,
                projection,
            ).limit(
                self._candidate_pool_size
            )
        )

        # 严格查询不足时，退化为任意词项命中。
        if len(documents) < limit:
            seen_ids = {
                document["_id"]
                for document in documents
            }

            fallback_query = {
                "$or": [
                    _build_token_condition(
                        token
                    )
                    for token in tokens
                ]
            }

            remaining_limit = (
                self._candidate_pool_size
                - len(documents)
            )

            if remaining_limit > 0:
                for document in collection.find(
                    fallback_query,
                    projection,
                ).limit(remaining_limit):
                    if (
                        document["_id"]
                        in seen_ids
                    ):
                        continue

                    seen_ids.add(
                        document["_id"]
                    )
                    documents.append(document)

        candidates = []

        for document in documents:
            title = str(
                document.get("title", "")
            ).strip()

            if not title:
                continue

            score, matched_fields = (
                self._score_document(
                    document=document,
                    normalized_topic=(
                        normalized_topic
                    ),
                    tokens=tokens,
                )
            )

            if score <= 0:
                continue

            candidates.append(
                TopicCandidate(
                    paper_id=str(
                        document["_id"]
                    ),
                    title=title,
                    accepted_by=str(
                        document.get(
                            "accepted_by",
                            "",
                        )
                    ),
                    score=score,
                    matched_fields=(
                        matched_fields
                    ),
                )
            )

        candidates.sort(
            key=lambda candidate: (
                -candidate.score,
                candidate.title.lower(),
                candidate.paper_id,
            )
        )

        return candidates[:limit]
