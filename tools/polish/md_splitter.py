"""Markdown splitter that preserves code blocks, headings, images and other
non-prose blocks while exposing prose paragraphs and list items as polish
targets.

Splitting is line-based rather than AST-based so we can write blocks back to
disk byte-for-byte in their original order.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List
import re


PROSE = "prose"
SKIP = "skip"

_FENCE_RE = re.compile(r"^\s{0,3}(```|~~~)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
_HR_RE = re.compile(r"^\s*([-*_])\s*\1\s*\1[\s\1]*$")
_IMAGE_ONLY_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]+\)\s*$")
_FOOTNOTE_DEF_RE = re.compile(r"^\s*\[\^[^\]]+\]:\s")


@dataclass
class Block:
    id: int
    type: str  # "prose" or "skip"
    text: str  # raw text including original whitespace, no trailing newline


def _is_skip_line(line: str) -> bool:
    """A line that, when standing alone as a paragraph, should not be polished."""
    stripped = line.strip()
    if not stripped:
        return True
    if _HEADING_RE.match(line):
        return True
    if _HR_RE.match(line):
        return True
    if _IMAGE_ONLY_RE.match(line):
        return True
    if _FOOTNOTE_DEF_RE.match(line):
        return True
    return False


def split(md: str) -> List[Block]:
    """Split markdown into ordered blocks. Concatenating the .text of each block
    with no separator reproduces the original input exactly."""
    lines = md.splitlines(keepends=True)
    blocks: List[Block] = []
    i = 0
    n = len(lines)
    next_id = 0

    def push(btype: str, chunk_lines: List[str]) -> None:
        nonlocal next_id
        if not chunk_lines:
            return
        blocks.append(Block(id=next_id, type=btype, text="".join(chunk_lines)))
        next_id += 1

    while i < n:
        line = lines[i]

        # Fenced code block — keep as a single SKIP block including the fences.
        m = _FENCE_RE.match(line)
        if m:
            fence = m.group(1)
            chunk = [line]
            i += 1
            while i < n:
                chunk.append(lines[i])
                if lines[i].lstrip().startswith(fence):
                    i += 1
                    break
                i += 1
            push(SKIP, chunk)
            continue

        # Blank line — own SKIP block (preserves spacing exactly).
        if line.strip() == "":
            push(SKIP, [line])
            i += 1
            continue

        # Heading / hr / image-only / footnote def — own SKIP block (one line).
        if _is_skip_line(line):
            push(SKIP, [line])
            i += 1
            continue

        # Otherwise, accumulate consecutive non-blank lines as one prose block.
        # Blockquotes (lines starting with >) are also treated as prose — DeepSeek
        # is told to keep the > marker intact.
        chunk = [line]
        i += 1
        while i < n and lines[i].strip() != "" and not _is_skip_line(lines[i]) \
                and not _FENCE_RE.match(lines[i]):
            chunk.append(lines[i])
            i += 1
        push(PROSE, chunk)

    return blocks


def join(blocks: List[Block]) -> str:
    return "".join(b.text for b in blocks)


def to_dicts(blocks: List[Block]) -> List[dict]:
    return [asdict(b) for b in blocks]
