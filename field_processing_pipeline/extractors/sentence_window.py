"""
读时窗口：给定 body_sentences 数组、某次出现的 sentence_index 和 N，
现算"前 N 句 + 本句 + 后 N 句"。窗口绝不预存（PLAN §4.3 工程铁律）。

默认在同一章节内裁剪（窗口不跨小标题、不溢进别的 section）。
"""


def build_window(body_sentences, sentence_index, n, clamp_section=True):
    """
    返回 body_sentences[i-n : i+n+1] 的子列表（Python 切片天然处理边界）。

    clamp_section=True 时，窗口被裁剪到与中心句相同的 section（窗口不跨章节）。
    """
    if not body_sentences:
        return []
    # body_sentences 的下标即 s_idx（连续递增），直接用列表下标。
    i = sentence_index
    if i < 0 or i >= len(body_sentences):
        # 兼容传入的是 s_idx 而非列表下标的情况：按 s_idx 定位
        idx_map = {s["s_idx"]: k for k, s in enumerate(body_sentences)}
        if sentence_index not in idx_map:
            return []
        i = idx_map[sentence_index]

    lo = max(0, i - n)
    hi = min(len(body_sentences), i + n + 1)
    window = body_sentences[lo:hi]

    if clamp_section:
        center_section = body_sentences[i].get("section")
        window = [s for s in window if s.get("section") == center_section]
    return window


def render_window_text(window) -> str:
    return " ".join(s["text"] for s in window)
