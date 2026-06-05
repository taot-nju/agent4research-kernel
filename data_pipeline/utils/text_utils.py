import hashlib
import re


def normalize_title(title: str) -> str:
    """
    统一标题规范：
    - 小写
    - 去掉标点
    - 合并多余空格
    """
    title = title.lower()
    title = re.sub(r"[^a-z0-9\s]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def paper_id_from_title(title: str) -> str:
    normalized_title = normalize_title(title)

    if not normalized_title:
        raise ValueError("Cannot generate paper_id from empty title.")

    return hashlib.sha1(
        normalized_title.encode("utf-8")
    ).hexdigest()


if __name__ == '__main__':
    # title1 = "A Novel Approach to AI Research: Challenges & Opportunities!"
    # title2 = "A novel approach to AI research - challenges and opportunities"
    # title3 = "  A Novel Approach to AI Research: Challenges & Opportunities!!!  "

    # id1 = paper_id_from_title(title1)
    # id2 = paper_id_from_title(title2)
    # id3 = paper_id_from_title(title3)

    # print(f"Title 1 ID: {id1}")
    # print(f"Title 2 ID: {id2}")
    # print(f"Title 3 ID: {id3}")

    # assert id1 == id2 == id3, "The same paper should have the same ID regardless of title formatting."
    # print("✅ All titles generated the same paper ID as expected.")
    print(paper_id_from_title('Attention Is All You Need'))

# python -m ai4research.data_pipeline.utils.text_utils