#!/usr/bin/env python3
"""
中文关键词提取工具 — 零依赖，基于 TF-IDF 变体

用法:
  python keywords.py <file.md>        # 从文件读取
  echo "文本" | python keywords.py    # 从 stdin 读取
  python keywords.py -n 30 <file>     # 输出 Top-30
"""

import re
import sys
import math
import argparse
from collections import Counter

# ================================================================
# 内嵌停用词表（约 150 个）
# ================================================================
STOPWORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
    "都", "一", "上", "出", "里", "你", "他", "她", "们", "这",
    "那", "什么", "没有", "可以", "因为", "所以", "但是", "如果",
    "虽然", "然而", "为了", "通过", "对于", "关于", "按照", "根据",
    "包括", "以及", "需要", "可能", "已经", "进行", "提供", "使用",
    "成为", "发展", "问题", "工作", "时间", "方式", "内容", "结果",
    "过程", "系统", "数据", "技术", "研究", "分析", "一个", "一些",
    "这些", "那些", "这个", "那个", "我们", "他们", "她们", "它们",
    "自己", "只是", "还是", "还有", "而且", "并且", "因此", "然后",
    "这里", "那里", "其中", "其实", "其他", "非常", "比较", "更加",
    "最终", "最终", "同时", "此时", "当时", "之后", "之前", "以后",
    "以前", "目前", "现在", "将来", "未来", "已经", "正在", "能够",
    "应该", "可以", "需要", "希望", "认为", "知道", "看到", "说明",
    "表示", "表明", "提出", "提到", "提高", "提供", "进一步", "更多",
    "很多", "大量", "少量", "部分", "全部", "所有", "每个", "各种",
    "各类", "不同", "相同", "相关", "重要", "主要", "基本", "一般",
    "特别", "具体", "实际", "有效", "主要", "主体", "核心", "关键",
    "重点", "总体", "整体", "全面", "方面", "领域", "层面", "角度",
    "方向", "目标", "要求", "条件", "基础", "背景", "情况", "状态",
    "水平", "程度", "效果", "影响", "作用", "意义", "价值", "能力",
    "水平", "质量", "标准", "模式", "机制", "结构", "体系", "框架",
    "具有", "存在", "形成", "建立", "实现", "完成", "开展", "推动",
    "促进", "加强", "提升", "改善", "解决", "处理", "面对", "考虑",
    "选择", "决定", "确定", "评估", "判断", "分类", "整合", "优化",
    "完善", "改进", "更新", "继续", "坚持", "保持", "维持", "支持",
    "帮助", "参与", "负责", "管理", "控制", "监测", "检测", "验证",
    "按照", "依据", "基于", "用于", "适用", "服务", "应用", "针对",
    "来自", "属于", "取决", "在于", "主要是", "重要是", "应当",
}


def extract_words(text: str) -> list[str]:
    """用正则提取 2-6 字中文词，过滤停用词"""
    tokens = re.findall(r'[一-鿿]{2,6}', text)
    return [t for t in tokens if t not in STOPWORDS]


def compute_tfidf(words: list[str]) -> list[tuple[str, int, float]]:
    """
    计算简化版 TF-IDF 分数（单文档模式）。
    TF  = 词频 / 文档总词数
    IDF = log(1 + 1 / (词频 + 1))   — 逆词频惩罚高频词
    score = TF × IDF
    """
    if not words:
        return []

    freq = Counter(words)
    total = len(words)
    results = []

    for word, count in freq.items():
        tf = count / total
        idf = math.log(1 + 1 / (count + 1))
        score = tf * idf
        results.append((word, count, score))

    results.sort(key=lambda x: x[2], reverse=True)
    return results


def format_table(results: list[tuple[str, int, float]], top_n: int) -> str:
    """格式化输出表格"""
    top = results[:top_n]
    lines = [f"# Top-{len(top)} 关键词\n"]
    header = f"{'排名':<6}{'关键词':<12}{'频次':<8}{'TF-IDF分'}"
    lines.append(header)
    lines.append("-" * len(header.expandtabs()))

    for i, (word, count, score) in enumerate(top, 1):
        lines.append(f"{i:<6}{word:<12}{count:<8}{score:.4f}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="中文关键词提取工具 — 基于 TF-IDF 变体，零依赖",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("file", nargs="?", help="输入文件路径（省略则从 stdin 读取）")
    parser.add_argument("-n", "--top", type=int, default=20, metavar="N",
                        help="输出关键词数量（默认 20）")
    args = parser.parse_args()

    # 读取文本
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            print(f"错误：找不到文件 '{args.file}'", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"错误：无法读取文件 — {e}", file=sys.stderr)
            sys.exit(1)
    else:
        if sys.stdin.isatty():
            print("请输入文本（Ctrl+D 结束）：", file=sys.stderr)
        text = sys.stdin.read()

    if not text.strip():
        print("错误：输入文本为空", file=sys.stderr)
        sys.exit(1)

    # 提取 + 计算
    words = extract_words(text)
    if not words:
        print("未找到有效中文词语（长度 2-6 字）", file=sys.stderr)
        sys.exit(1)

    results = compute_tfidf(words)
    print(format_table(results, args.top))


if __name__ == "__main__":
    main()
