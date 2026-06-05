"""
需要注意的2点内容：
❶ 一篇论文的类别可能包含多个类别，例如：cs.AI, cs.LG, cs.CL等；我们需要分别记录所有的类别，以便后续分析。
❷ 如果一篇论文，它的类别是cs.AI，那它也可能同时标记了cs.CV，而cs.CV并不在我们的兴趣列表，所以，实际上我们的论文列表中还是会有cs.CV的论文；
"""

# 感兴趣的类别，以后可能会增加（可扩展参数）
CATEGORIES = [
    "cs.AI",  # Artificial Intelligence
    # "cs.LG",  # Machine Learning
    "cs.CL",  # Computation and Language
    # "cs.MA",  # Multiagent Systems
    # "cs.IR",  # Information Retrieval
    # "cs.NE",  # Neural and Evolutionary Computing
    # "cs.HC",  # Human-Computer Interaction
    # "cs.SI",  # Social and Information Networks
    # "cs.SC",  # Symbolic Computation
]

