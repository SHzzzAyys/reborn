#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
keywords.py —— 中文关键词抓取小工具（零依赖版）

算法说明
--------
基于"新词发现"思想（Matrix67 经典方法），不依赖任何词典：
  1. N-gram 候选：扫描所有 2~4 字中文片段
  2. 词频过滤：出现次数 < min_count 的丢弃
  3. 凝固度（Pointwise Mutual Information）：片段内部粘合紧不紧
  4. 自由度（左右邻字熵）：片段左右搭配是否丰富
  5. 综合得分 = log(freq) × min(PMI, entropy)

优点：
  - 能自动识别"复利效应"、"第二宇宙速度"、"财务自由"这类专有组合
  - 不需要安装 jieba / HanLP 等库

用法
----
    python3 keywords.py                      # 对当前目录所有 .md 提取全书关键词
    python3 keywords.py --top 50             # 输出前 50 个
    python3 keywords.py --file A01.md        # 只对单个文件
    python3 keywords.py --out keywords.csv   # 结果写入 CSV
    python3 keywords.py --per-chapter        # 每一章单独输出 top 10
"""

from __future__ import annotations

import argparse
import csv
import glob
import math
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Tuple


# ---------------------------------------------------------------------------
# 文本清洗
# ---------------------------------------------------------------------------

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`]*`")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG = re.compile(r"<[^>]+>")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_FOOTNOTE_REF = re.compile(r"\[\^[^\]]+\]")
_MD_HEADING = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_MD_BOLD = re.compile(r"\*{1,3}")
_MD_QUOTE = re.compile(r"^>+\s?", re.MULTILINE)

# 只保留中文字符；其他全部视作切分边界
_CHINESE_RUN = re.compile(r"[\u4e00-\u9fff]+")


def clean_markdown(text: str) -> str:
    """去掉 Markdown 语法、HTML、URL、英文、标点，只留下中文片段（以非中文为分隔）。"""
    text = _HTML_COMMENT.sub(" ", text)
    text = _CODE_BLOCK.sub(" ", text)
    text = _INLINE_CODE.sub(" ", text)
    text = _IMAGE.sub(" ", text)
    text = _LINK.sub(r"\1", text)  # 保留链接的显示文字
    text = _URL.sub(" ", text)
    text = _FOOTNOTE_REF.sub(" ", text)
    text = _HTML_TAG.sub(" ", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_QUOTE.sub("", text)
    text = _MD_BOLD.sub(" ", text)
    return text


def chinese_segments(text: str) -> List[str]:
    """把清洗后的文本切成纯中文片段列表。"""
    return _CHINESE_RUN.findall(text)


# ---------------------------------------------------------------------------
# 停用词（常用虚词/副词，不算真正的关键词）
# ---------------------------------------------------------------------------

STOPWORDS = set("""
的 了 是 在 我 你 他 她 它 我们 你们 他们 这 那 这些 那些 这个 那个
和 与 及 或 并 而 也 就 都 还 又 才 再 很 更 最 太 越 已 已经 将 会
有 没 没有 不 不是 不要 别 莫 未 非 无 要 可 可以 能 能够 应该 必须
之 其 者 所 被 把 为 给 对 向 从 到 于 由 自 按 跟 同 与 比 因为 所以 但是 但 然而 不过
什么 怎么 怎样 如何 为什么 多少 几个 哪 哪里 哪些 谁 任何 每 各
一 二 三 四 五 六 七 八 九 十 百 千 万 几 多 少 第一 第二
一个 一些 一种 一样 一下 一起 一直 一定 一般 一下子 一点 一点点
比如 例如 比方 就是 或者 然后 接着 后来 之后 以后 以前 之前 现在 目前 当时 当年 当初
的确 确实 真的 其实 其实是 特别 非常 极其 尤其 居然 竟然 当然 果然 原来 本来
可能 也许 大概 差不多 大约 似乎 好像 仿佛 好 好的 好了
出来 出去 上去 下去 起来 下来 过来 过去
没关系 不行 行不行 可是 而且 并且 以及 还有 至于 关于 通过 根据 按照 由于
做 作 搞 弄 干 说 讲 谈 想 要 看 听 走 去 来 回 用 让 叫
自己 别人 人家 大家 我们 咱们 今天 今年 明天 昨天 去年 明年
那时 这时 此时 此刻 以来 以来的 其中 其他 其它 另外 另 另一
那样 这样 同样 一样 反正 总之 总的来说 总是 常常 经常 偶尔 有时
此 本 该 某 诸 各位 这里 那里 哪里 里面 外面 上面 下面 前面 后面 中间
东西 事情 情况 问题 原因 结果 方法 办法 方式 样子 程度 方面 时候 时间
二零 零零 一五 一六 一四
""".split())


# 补充：常见副词、动词、虚化名词，这些出现频率再高也不是"关键词"
STOPWORDS.update([
    # 副词
    "甚至", "即便", "虽然", "彻底", "直接", "完全", "肯定", "确实", "的确",
    "根本", "纯粹", "刚刚", "刚才", "马上", "立刻", "顿时", "陆续", "渐渐",
    "逐步", "逐渐", "始终", "仍然", "依然", "依旧", "一直", "一旦", "终于",
    "居然", "竟然", "原来", "本来", "到底", "究竟", "毕竟", "反而", "反正",
    "绝对", "简直", "或许", "也许", "大约", "恐怕", "似乎", "未必",
    # 虚化副词短语
    "实际上", "事实上", "基本上", "总的来说", "绝大多数", "绝大部分",
    "进一步", "其实是", "其实就是", "如果", "要是", "假如", "除非",
    # 常见动词（太泛，不具识别度）
    "开始", "觉得", "知道", "看到", "听到", "认为", "以为", "想到", "说到",
    "发现", "看见", "明白", "理解", "相信", "希望", "喜欢", "讨厌", "需要",
    "想要", "得到", "获得", "拥有", "存在", "出现", "产生", "形成", "发生",
    "做到", "达到", "碰到", "遇到", "关于", "表示", "进行", "接受", "注意",
    # 虚化名词
    "东西", "事儿", "事情", "情况", "事实", "样子", "地方", "里面", "里头",
    "结果", "原因", "方式", "方法", "方面", "过程", "基础", "部分",
    # 人称/泛称
    "人们", "人类", "自己", "别人", "大家", "咱们", "我们", "你们", "他们",
    # 频次极高但信息量低
    "一种", "一个", "一些", "这种", "那种", "这样", "那样", "这里", "那里",
    "时候", "时间", "今天", "明天", "昨天", "今年", "明年", "去年",
    "真正", "清楚", "永远", "足够", "反复",
])


# ---------------------------------------------------------------------------
# 核心算法：新词发现
# ---------------------------------------------------------------------------

def count_ngrams(segments: Iterable[str],
                 max_n: int = 4) -> Tuple[Counter, int, Dict[str, Counter], Dict[str, Counter]]:
    """
    返回:
      freq    : { ngram -> count }          各 n-gram 出现次数（包含单字）
      total   : int                         所有单字总数（计算 PMI 用）
      left    : { ngram -> Counter{左邻字:次数} }
      right   : { ngram -> Counter{右邻字:次数} }
    """
    freq: Counter = Counter()
    left: Dict[str, Counter] = defaultdict(Counter)
    right: Dict[str, Counter] = defaultdict(Counter)
    total_chars = 0

    for seg in segments:
        L = len(seg)
        total_chars += L
        # 单字
        for i, ch in enumerate(seg):
            freq[ch] += 1
        # 2..max_n gram
        for n in range(2, max_n + 1):
            for i in range(L - n + 1):
                gram = seg[i:i + n]
                freq[gram] += 1
                if i > 0:
                    left[gram][seg[i - 1]] += 1
                if i + n < L:
                    right[gram][seg[i + n]] += 1

    return freq, total_chars, left, right


def entropy(counter: Counter) -> float:
    """香农熵。Counter 为空时返回 0。"""
    total = sum(counter.values())
    if total == 0:
        return 0.0
    return -sum((c / total) * math.log(c / total) for c in counter.values() if c > 0)


def pmi_min(gram: str, freq: Counter, total: int) -> float:
    """
    对多字词取"最小切分点的 PMI"，作为凝固度。
    PMI = log( P(gram) / max over split { P(left) * P(right) } )
    值越大说明越不像随机拼接。
    """
    if len(gram) < 2:
        return 0.0
    p_gram = freq[gram] / total
    best = 0.0  # 我们想最小化 P(left)*P(right)，等价于最大化 PMI
    worst_pmi = float("inf")
    for i in range(1, len(gram)):
        l, r = gram[:i], gram[i:]
        if freq[l] == 0 or freq[r] == 0:
            continue
        p_l = freq[l] / total
        p_r = freq[r] / total
        split_pmi = math.log(p_gram / (p_l * p_r))
        if split_pmi < worst_pmi:
            worst_pmi = split_pmi
    return worst_pmi if worst_pmi != float("inf") else 0.0


def score_candidates(freq: Counter,
                     total: int,
                     left: Dict[str, Counter],
                     right: Dict[str, Counter],
                     min_count: int = 5,
                     min_pmi: float = 3.0,
                     min_entropy: float = 1.2) -> List[Tuple[str, float, int]]:
    """
    返回按得分降序排列的关键词列表: [(word, score, freq), ...]
    对 3/4 字词使用更宽松的阈值，鼓励专有组合词(如"复利效应")出现。
    """
    scored = []
    for gram, c in freq.items():
        n = len(gram)
        if n < 2 or n > 4:
            continue
        if c < min_count:
            continue
        if gram in STOPWORDS:
            continue
        if gram[0] in STOPWORDS or gram[-1] in STOPWORDS:
            continue

        pmi = pmi_min(gram, freq, total)
        # 长词的凝固度门槛适当降低
        pmi_thresh = min_pmi if n == 2 else min_pmi - 1.0
        if pmi < pmi_thresh:
            continue

        le = entropy(left.get(gram, Counter()))
        re_ = entropy(right.get(gram, Counter()))
        free = min(le, re_)
        ent_thresh = min_entropy if n == 2 else min_entropy - 0.3
        if free < ent_thresh:
            continue

        # 综合得分：长词加权，避免被 2 字词淹没
        length_boost = 1.0 + 0.25 * (n - 2)
        score = math.log(c) * min(pmi, free * 2) * length_boost
        scored.append((gram, score, c))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


# ---------------------------------------------------------------------------
# 去除包含关系的子串 (比如同时出现"复利"和"复利效应"时保留后者)
# ---------------------------------------------------------------------------

def dedup_substring(words: List[Tuple[str, float, int]]) -> List[Tuple[str, float, int]]:
    kept: List[Tuple[str, float, int]] = []
    for w, s, c in words:
        # 若已保留的更长词包含 w，且二者词频接近，则丢弃 w
        subsumed = False
        for kw, ks, kc in kept:
            if w in kw and len(kw) > len(w) and kc >= c * 0.6:
                subsumed = True
                break
        if not subsumed:
            kept.append((w, s, c))
    return kept


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def extract_from_files(paths: List[str],
                       top: int,
                       min_count: int) -> List[Tuple[str, float, int]]:
    all_segments: List[str] = []
    for p in paths:
        with open(p, "r", encoding="utf-8") as f:
            cleaned = clean_markdown(f.read())
        all_segments.extend(chinese_segments(cleaned))

    freq, total, left, right = count_ngrams(all_segments, max_n=4)
    scored = score_candidates(freq, total, left, right, min_count=min_count)
    scored = dedup_substring(scored)
    return scored[:top]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="《新生——七年就是一辈子》关键词抓取工具（零依赖）")
    parser.add_argument("--dir", default=".", help="书稿目录（默认当前目录）")
    parser.add_argument("--file", help="只处理单个 .md 文件")
    parser.add_argument("--top", type=int, default=30, help="输出前 N 个关键词")
    parser.add_argument("--min-count", type=int, default=5,
                        help="最小出现次数（全书默认 5，单章建议 3）")
    parser.add_argument("--out", help="输出 CSV 文件路径（默认只打印到终端）")
    parser.add_argument("--per-chapter", action="store_true",
                        help="每一章单独输出 top N")
    args = parser.parse_args()

    if args.file:
        files = [args.file]
    else:
        files = sorted(glob.glob(os.path.join(args.dir, "*.md")))
        # 排除 README
        files = [f for f in files if os.path.basename(f) != "README.md"]

    if not files:
        print("未找到 Markdown 文件。", file=sys.stderr)
        return 1

    rows: List[Tuple[str, str, float, int]] = []  # (chapter, word, score, freq)

    if args.per_chapter:
        for fp in files:
            chap = os.path.basename(fp)
            kws = extract_from_files([fp], top=args.top,
                                     min_count=max(args.min_count - 2, 2))
            print(f"\n=== {chap} ===")
            for w, s, c in kws:
                print(f"  {w:8s}  freq={c:4d}  score={s:6.2f}")
                rows.append((chap, w, s, c))
    else:
        kws = extract_from_files(files, top=args.top, min_count=args.min_count)
        title = "全书" if len(files) > 1 else os.path.basename(files[0])
        print(f"\n=== {title} 关键词 Top {args.top} ===")
        print(f"{'排名':<4}{'关键词':<10}{'词频':>6}{'得分':>10}")
        print("-" * 34)
        for i, (w, s, c) in enumerate(kws, 1):
            print(f"{i:<4}{w:<10}{c:>6}{s:>10.2f}")
            rows.append((title, w, s, c))

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["chapter", "keyword", "score", "freq"])
            for r in rows:
                writer.writerow(r)
        print(f"\n已写入 {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
