"""
论文记录的Schema定义：

定义了论文记录中包含的字段以及它们的默认值；这些字段包括论文的基本信息（例如标题、作者、摘要等），以及一些后续处理得到的信息（例如标签、目录结构、参考文献等）；

同时还定义了一些标记字段，用于跟踪论文记录的处理状态，例如PDF是否已经下载完成，文本是否已经提取完成，等等。

"""

# -----------------------------------------------------------------------------------------------------------------------

# 当前 schema 版本号（非常重要：用于标记当前的Schema更新了多少版）
CURRENT_SCHEMA_VERSION = 1


# 默认字段结构：以后可能会随着分析的深入，增加更多自定义字段
# 🟢表示所有记录都拥有的自然属性（可以直接获取的字段，例如，通过爬虫得到。）
# 🔴表示后续需要处理才能得到的字段
DEFAULT_PAPER_FIELDS = {
    "title": "",  # 🟢
    "aliases": [], # 论文的别名，例如：CoT, Chain-of-Thought, Manual CoT, Few-shot CoT
    "authors": [],  # 🟢
    "abstract": "",  # 🟢
    "abstract_entities": [],  # 🔴从摘要中提取的实体，例如：模型名称、数据集名称、任务名称等


    # arXiv特有的字段：因为arXiv预印本的记录可能会随着时间的推移而不断更新，所以需要记录一些特有的字段来跟踪这些变化；而对于会议或期刊论文，这些字段则不适用，因此保持为空。
    # 🟢包含arXiv_id, arXiv_online_url, arXiv_pdf_url, arXiv_comment, arXiv_categories, arXiv_versions_history等；非arXiv记录该字段为空

    "arxiv_obj": {
        "arxiv_id": "",
        "arxiv_url": "",
        "arxiv_pdf_url": "",
        "arxiv_categories": [],
        "comment": "",
        "doi": "",

        # 把一篇 arXiv 论文的所有版本都记录下来。
        # 例如：
        # [
        #     {"version": "v1", "date": "2024-01-01"},
        #     {"version": "v2", "date": "2024-02-01"}
        # ]
        "submission_history": [
            {
                "version": "",
                "date": ""
            }
        ]
    },


    # OpenReview 特有字段：
    # 用于记录 OpenReview 上的 note/forum/venue/pdf 等信息。
    # 对于非 OpenReview 来源的论文，该字段保持默认空值。
    "openreview_obj": {
        "note_id": "",  # OpenReview note 的 id，例如 6T3wJQhvc3
        "forum_id": "",  # OpenReview forum id，通常和 note_id 一样
        "number": "",  # OpenReview 上的 submission number
        "venue": "",  # 例如 ICLR 2026 Poster
        "venueid": "",  # 例如 ICLR.cc/2026/Conference
        "paperhash": "",  # OpenReview 给出的 paperhash
        "pdf_url": "",  # 完整 PDF 地址
        "forum_url": "",  # OpenReview 论文页面地址
        "keywords": [],  # OpenReview 页面为每篇投稿设置了必填项：关键词（由作者自己填写）
        "tldr": "",  # OpenReview 里的 TLDR
        "primary_area": "",  # 论文方向
        "accept_type": "",  # 从 venue 中解析出的 Poster / Oral / Spotlight 等类型
    },



    # 如果一篇论文既在arxiv的cs.CL分类下出现过，也在cs.AI分类下出现过，那么这个字段就记录["cs.CL", "cs.AI"]；
    # 如果一篇论文只在arXiv的cs.CL分类下出现过，那么这个字段就记录["cs.CL"]。
    "seen_in_categories": [], # 🟢

 
    # 所有刊物（arXiv, conference, journal）都可以有的字段：这些字段对于所有类型的论文记录都是适用的，无论是arXiv预印本还是会议/期刊论文都可以使用这些字段来记录相关信息。
    "accepted_by": "", # 🟢被哪个会议或期刊接受，例如："ICLR 2026"；如果是arXiv预印本，则该字段为"arXiv 2026"；如果一篇论文既在arXiv上出现过，也被ICLR 2026接受了，那么该字段就记录"ICLR 2026"（以会议/期刊为主，覆盖掉arXiv的记录）。


    # URLs
    # arxiv_online_url, arXiv_pdf_url, openreview_url, etc.；
    # 如果一篇论文既在arXiv上出现过，也被ICLR 2026接受了，那么这个字段就记录{"arXiv_online_url": "https://arxiv.org/abs/1234.56789", "arXiv_pdf_url": "https://arxiv.org/pdf/1234.56789.pdf", "openreview_url": "https://openreview.net/forum?id=abcdefg", "official_url": "https://iclr.cc/virtual/2026/poster/abcdefg"}；
    # 如果一篇论文只在arXiv的cs.CL分类下出现过，那么这个字段就记录{"arXiv_online_url": "https://arxiv.org/abs/1234.56789", "arXiv_pdf_url": "https://arxiv.org/pdf/1234.56789.pdf"}。
    "base_urls": {},  # 🟢
    "more_urls": {},  # 🟢除了pdf, openreview, arxiv之外的其他链接，例如：code, project page, video, slides, etc.


    "cite_numbers": [],  # 🟢从Google Scholar爬取的引文数据（或者是Semantic Scholar）


    # 需要经过处理才能得到的字段：从论文中抽取得到的结构化信息。
    "tags": [],  # 🔴从论文正文提取的标签，例如：reasoning, chain-of-thought, few-shot, zero-shot, etc.
    "toc_tree": [],  # 🔴从论文提取的目录结构
    "references": [],  # 🔴从论文提取的参考文献列表
    "keywords": [], # 🔴从论文正文提取的关键字
    "summary_short":"",  # 🔴对论文做一个简短的总结
    "summary_long":"",  # 🔴对论文做一个长总结
    "txt_contributions": "",  # 🔴从论文正文提取的贡献总结，例如：我们提出了一种新的方法，叫做XYZ，该方法在ABC数据集上取得了SOTA性能，并且在DEF任务上表现出色。
    "txt_scientific_question": "",  # 🔴从论文分析得到该论文主要研究的“关键的科学问题”是什么


    # 论文4要素
    "pipeline": "",  # 🔴 论文的实验流程
    "baselines": [],  # 🔴 论文的对比方法
    "benchmarks": [],  # 🔴 论文的评测数据集
    "metrics": [],  # 🔴 论文的评测指标
    

    # 标记论文的某些字段是否已经处理完成，例如：目录是否已经提取完成，参考文献是否已经提取完成，PDF是否已经下载完成，文本是否已经提取完成，等等；这些字段的作用是为了避免重复处理同一篇论文的同一项内容，从而提高效率。
    "processing_status": {
        "toc_extracted": False,  
        "references_extracted": False,

        "pdf_downloaded": False,  # 该字段标记论文的PDF是否已经成功下载
        "txt_extracted": False,  # 如果通过了OCR识别，则对应的.txt必然存在，该字段值则置为True。
        "json_extracted": False
    },
    "local_txt_path": "",  # 考虑到直接用MongoDB存储大量文本数据可能会导致性能问题，因此我们选择将文本数据存储在本地文件系统中，并在MongoDB中记录对应的文件路径；如果txt_extracted为True，则local_txt_path必然不为空。
    "local_pdf_path": "",  
    "local_json_path": "",


    "seen_in_sources": [],  # 记录一篇论文在哪些来源中出现过，例如：arXiv, ICLR, NeurIPS, etc.；如果一篇论文既在arXiv上出现过，也被ICLR 2026接受了，那么这个字段就记录["arXiv", "ICLR 2026"]。


    "edit_logs": []  # 记录对该论文记录进行的编辑操作
    # edit_log = {
    #     "time": now_beijing_iso(),
    #     "op": f"insert from {source}" + (f" @ {category}" if category else ""),
    #     "detail": "insert paper metadata"
    # }
}


