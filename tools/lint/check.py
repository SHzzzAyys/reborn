#!/usr/bin/env python3
"""Reborn Markdown lint — read-only quality scanner.

Scans every .md file in the repository root and reports issues that
DeepSeek-based polishing won't catch (broken images, orphan footnotes,
duplicate chars, mixed punctuation, trailing whitespace).

Never modifies any chapter file. Optional HTML report is written to
tools/lint/report.html (gitignored).

Usage:
    python tools/lint/check.py
    python tools/lint/check.py --html
    python tools/lint/check.py --rule duplicate-char
    python tools/lint/check.py --quiet
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List

# Anchored to the repo root regardless of the CWD the user runs from.
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
REPORT_PATH = HERE / "report.html"

LEVEL_ERROR = "error"
LEVEL_WARN = "warn"


@dataclass(frozen=True)
class Issue:
    file: str       # filename relative to repo root, e.g. "A07.md"
    line: int       # 1-based line number
    rule: str       # rule id
    level: str      # "error" | "warn"
    message: str    # human-readable description


# ---------------------------------------------------------------------------
# Rule: broken-image
# ---------------------------------------------------------------------------

_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def check_images(file: str, lines: List[str]) -> List[Issue]:
    issues: List[Issue] = []
    for i, line in enumerate(lines, start=1):
        for match in _IMG_RE.finditer(line):
            target = match.group(1).strip()
            # Skip remote images and data URIs.
            if target.startswith(("http://", "https://", "data:")):
                continue
            # Strip optional title: ![](path "title")
            target = target.split(" ", 1)[0]
            resolved = (REPO_ROOT / target).resolve()
            try:
                resolved.relative_to(REPO_ROOT)
            except ValueError:
                issues.append(Issue(file, i, "broken-image", LEVEL_ERROR,
                                    f"图片路径越出仓库：{target}"))
                continue
            if not resolved.is_file():
                issues.append(Issue(file, i, "broken-image", LEVEL_ERROR,
                                    f"图片不存在：{target}"))
    return issues


# ---------------------------------------------------------------------------
# Rule: footnotes (broken-ref + unused-def)
# ---------------------------------------------------------------------------

# Footnote reference: [^X] not immediately followed by ":"
_FN_REF_RE = re.compile(r"\[\^([^\]\s]+)\](?!:)")
# Footnote definition: line starting with [^X]:
_FN_DEF_RE = re.compile(r"^\s*\[\^([^\]]+)\]:\s")


def check_footnotes(file: str, lines: List[str]) -> List[Issue]:
    issues: List[Issue] = []
    refs: dict[str, int] = {}        # ident -> first-seen line
    defs: dict[str, int] = {}        # ident -> definition line

    for i, line in enumerate(lines, start=1):
        m = _FN_DEF_RE.match(line)
        if m:
            ident = m.group(1)
            # The "[^N]:" inside a definition line is NOT a reference; strip
            # the prefix before scanning for refs in the same line.
            rest = line[m.end():]
            for rm in _FN_REF_RE.finditer(rest):
                refs.setdefault(rm.group(1), i)
            defs[ident] = i
            continue
        for rm in _FN_REF_RE.finditer(line):
            refs.setdefault(rm.group(1), i)

    for ident, line_no in refs.items():
        if ident not in defs:
            issues.append(Issue(file, line_no, "broken-footnote-ref",
                                LEVEL_ERROR,
                                f"脚注 [^{ident}] 引用了但本文件无定义"))
    for ident, line_no in defs.items():
        if ident not in refs:
            issues.append(Issue(file, line_no, "unused-footnote-def",
                                LEVEL_WARN,
                                f"脚注 [^{ident}] 已定义但本文件未引用"))
    return issues


# ---------------------------------------------------------------------------
# Rule: duplicate-char (with context-aware exclusions)
# ---------------------------------------------------------------------------

# (pattern, prev_excl, next_excl)
# prev_excl: if the char BEFORE the match is in this set, skip (false positive)
# next_excl: if the char AFTER the match is in this set, skip
_DUP_RULES: List[tuple[str, set[str], set[str]]] = [
    ("的的", set(), set()),
    ("在在", {"现"}, set()),            # "现在在..." 合法

    ("是是", set(), {"否", "非"}),     # "是是否" "是是非" 合法
    ("了了", {"为", "不"}, set()),     # "为了了解"、"不了了之" 合法
    ("吗吗", set(), set()),
    ("呢呢", set(), set()),
    ("啊啊", set(), set()),
]


def _excerpt(line: str, idx: int, span: int = 2, width: int = 14) -> str:
    """Return a small excerpt around [idx, idx+span) for display."""
    start = max(0, idx - width // 2)
    end = min(len(line), idx + span + width // 2)
    snippet = line[start:end].rstrip("\n").strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(line) else ""
    return prefix + snippet + suffix


def check_duplicate_chars(file: str, lines: List[str]) -> List[Issue]:
    issues: List[Issue] = []
    for i, line in enumerate(lines, start=1):
        for pattern, prev_excl, next_excl in _DUP_RULES:
            start = 0
            while True:
                idx = line.find(pattern, start)
                if idx == -1:
                    break
                prev_ch = line[idx - 1] if idx > 0 else ""
                next_ch = line[idx + len(pattern)] if idx + len(pattern) < len(line) else ""
                if prev_ch not in prev_excl and next_ch not in next_excl:
                    issues.append(Issue(
                        file, i, "duplicate-char", LEVEL_WARN,
                        f'发现叠字 "{pattern}"：{_excerpt(line, idx)}',
                    ))
                start = idx + 1   # allow overlapping detection ("的的的")
    return issues


# ---------------------------------------------------------------------------
# Rule: mixed-cn-en-punct (per-line)
# ---------------------------------------------------------------------------

def check_mixed_punct(file: str, lines: List[str]) -> List[Issue]:
    issues: List[Issue] = []
    for i, line in enumerate(lines, start=1):
        # Skip lines that look like code (contain backticks) or links — they
        # legitimately mix English punctuation.
        if "`" in line or "http://" in line or "https://" in line:
            continue
        # Strip inline links/images so URL punctuation doesn't trigger.
        cleaned = re.sub(r"!?\[[^\]]*\]\([^)]+\)", "", line)
        # Heuristic: a line is "Chinese" if it has at least one CJK char.
        if not re.search(r"[一-鿿]", cleaned):
            continue
        # English period before an ASCII letter (decimal/abbrev) is fine —
        # only flag a period followed by space/end which mimics 句号 usage.
        has_cn_period = "。" in cleaned
        has_en_sentence_period = bool(re.search(r"\.(\s|$)", cleaned))
        if has_cn_period and has_en_sentence_period:
            issues.append(Issue(
                file, i, "mixed-cn-en-punct", LEVEL_WARN,
                "同行混用中文 。 和英文句号 .",
            ))
            continue
        if "，" in cleaned and re.search(r",\s", cleaned):
            issues.append(Issue(
                file, i, "mixed-cn-en-punct", LEVEL_WARN,
                "同行混用中文 ， 和英文逗号 ,",
            ))
    return issues


# ---------------------------------------------------------------------------
# Rule: whitespace (trailing-whitespace + multiple-blank-lines)
# ---------------------------------------------------------------------------

def check_whitespace(file: str, lines: List[str]) -> List[Issue]:
    issues: List[Issue] = []
    blank_run = 0
    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n").rstrip("\r")
        if line.strip() == "":
            blank_run += 1
            if blank_run == 3:
                issues.append(Issue(
                    file, i, "multiple-blank-lines", LEVEL_WARN,
                    "出现 3 个或更多连续空行",
                ))
        else:
            blank_run = 0
            if line != line.rstrip():
                issues.append(Issue(
                    file, i, "trailing-whitespace", LEVEL_WARN,
                    "行尾包含空格或 Tab",
                ))
    return issues


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

CheckFn = Callable[[str, List[str]], List[Issue]]

ALL_CHECKS: List[CheckFn] = [
    check_images,
    check_footnotes,
    check_duplicate_chars,
    check_mixed_punct,
    check_whitespace,
]

ALL_RULE_IDS = {
    "broken-image",
    "broken-footnote-ref",
    "unused-footnote-def",
    "duplicate-char",
    "mixed-cn-en-punct",
    "trailing-whitespace",
    "multiple-blank-lines",
}


def lint_file(path: Path, only_rule: str | None = None) -> List[Issue]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    name = path.name
    issues: List[Issue] = []
    for fn in ALL_CHECKS:
        issues.extend(fn(name, lines))
    if only_rule:
        issues = [iss for iss in issues if iss.rule == only_rule]
    return issues


def render_terminal(issues: List[Issue], use_color: bool) -> str:
    if not issues:
        return "✓ 无问题。"

    def color(text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if use_color else text

    by_file: dict[str, List[Issue]] = {}
    for iss in issues:
        by_file.setdefault(iss.file, []).append(iss)

    out: List[str] = []
    for file in sorted(by_file):
        out.append(color(file, "1;36"))
        for iss in sorted(by_file[file], key=lambda x: (x.line, x.rule)):
            level_color = "1;31" if iss.level == LEVEL_ERROR else "1;33"
            out.append(
                f"  L{iss.line:<5} "
                f"{color(iss.level.ljust(5), level_color)}  "
                f"{iss.rule.ljust(22)}  {iss.message}"
            )
    n_err = sum(1 for i in issues if i.level == LEVEL_ERROR)
    n_warn = len(issues) - n_err
    out.append("")
    out.append(
        f"总计：{len(by_file)} 个文件，"
        f"{color(str(n_err), '1;31')} error，"
        f"{color(str(n_warn), '1;33')} warn"
    )
    return "\n".join(out)


def render_html(issues: List[Issue]) -> str:
    rows: List[str] = []
    for iss in sorted(issues, key=lambda x: (x.file, x.line, x.rule)):
        cls = "err" if iss.level == LEVEL_ERROR else "warn"
        rows.append(
            f'<tr class="{cls}">'
            f'<td class="file">{html.escape(iss.file)}</td>'
            f'<td class="line">L{iss.line}</td>'
            f'<td class="level">{iss.level}</td>'
            f'<td class="rule">{html.escape(iss.rule)}</td>'
            f'<td class="msg">{html.escape(iss.message)}</td>'
            f"</tr>"
        )
    n_err = sum(1 for i in issues if i.level == LEVEL_ERROR)
    n_warn = len(issues) - n_err
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Reborn Lint Report</title>
<style>
body {{ font-family: -apple-system, "PingFang SC", sans-serif; margin: 24px; color:#222; }}
h1 {{ font-size: 18px; margin-bottom: 4px; }}
.summary {{ color: #666; margin-bottom: 16px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #eee; vertical-align: top; }}
th {{ background: #f6f6f3; }}
tr.err td.level {{ color: #b04444; font-weight: 600; }}
tr.warn td.level {{ color: #b07a1a; font-weight: 600; }}
td.file {{ font-family: ui-monospace, Menlo, Consolas, monospace; }}
td.line {{ color: #888; width: 60px; }}
td.rule {{ color: #555; width: 200px; }}
</style></head><body>
<h1>Reborn Lint Report</h1>
<div class="summary">{len(issues)} 个问题（{n_err} error / {n_warn} warn）</div>
<table>
<thead><tr><th>文件</th><th>行</th><th>级别</th><th>规则</th><th>说明</th></tr></thead>
<tbody>
{chr(10).join(rows) if rows else '<tr><td colspan="5">✓ 无问题。</td></tr>'}
</tbody></table>
</body></html>
"""


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reborn Markdown lint — read-only quality scanner.",
    )
    parser.add_argument("--html", action="store_true",
                        help="生成 tools/lint/report.html")
    parser.add_argument("--rule", metavar="ID",
                        help=f"只跑某条规则；可选：{sorted(ALL_RULE_IDS)}")
    parser.add_argument("--quiet", action="store_true",
                        help="只输出汇总行")
    parser.add_argument("--no-color", action="store_true",
                        help="禁用终端颜色")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.rule and args.rule not in ALL_RULE_IDS:
        parser.error(f"未知规则：{args.rule}（可选：{sorted(ALL_RULE_IDS)}）")

    md_files = sorted(REPO_ROOT.glob("*.md"))
    all_issues: List[Issue] = []
    for path in md_files:
        all_issues.extend(lint_file(path, only_rule=args.rule))

    use_color = sys.stdout.isatty() and not args.no_color

    if args.quiet:
        n_err = sum(1 for i in all_issues if i.level == LEVEL_ERROR)
        n_warn = len(all_issues) - n_err
        print(f"扫描 {len(md_files)} 个文件，{n_err} error，{n_warn} warn")
    else:
        print(render_terminal(all_issues, use_color=use_color))

    if args.html:
        REPORT_PATH.write_text(render_html(all_issues), encoding="utf-8")
        print(f"\nHTML 报告已写入：{REPORT_PATH.relative_to(REPO_ROOT)}")

    return 1 if any(i.level == LEVEL_ERROR for i in all_issues) else 0


if __name__ == "__main__":
    sys.exit(main())
