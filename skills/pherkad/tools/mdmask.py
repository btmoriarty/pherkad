#!/usr/bin/env python3
"""mdmask: one reading of Markdown structure for both linters.

Roadmap item 5. voicelint and structlint each carried their own idea of what
in a Markdown file is prose: voicelint blanked code and read directives,
structlint skipped blockquotes, tables, headings, field lines, and list items
by its own regexes, and the two drifted (voicelint linted quoted text that
structlint skipped). This module is the single answer. It classifies every
line, and it masks the kinds a caller names to same-length whitespace so line
and column offsets never move.

    kinds = line_kinds(text)          # one of KINDS per line, 0-based
    masked = mask(text, ("code", "blockquote"))
    masked = strip_inline_code(text)  # `spans` become spaces

Kinds:
    code        inside a fence (the fence lines included), backtick or tilde,
                three or more, closed by a fence of the same character at least
                as long, or by the end of the file
    blockquote  a line starting with ">" (someone else's words)
    table       a pipe-delimited table row, delimiter rows included
    heading     an ATX heading
    field       a run of two or more bold labels ("**Type:** **Title:** ...")
    list        a bullet or a numbered item
    blank       whitespace only
    prose       everything else

Line-level kinds are decided in this order: code wins over everything (a ">"
inside a fence is code), then blockquote, table, heading, field, list, blank.
A list item that continues onto an indented next line is prose on that line;
that is what both tools did before and it keeps hard-wrapped items readable.

Stdlib only. Vendored beside voicelint.py wherever voicelint is.
"""
from __future__ import annotations
import re

KINDS = ("code", "blockquote", "table", "heading", "field", "list", "blank", "prose")

FENCE = re.compile(r"^[ \t]{0,3}(?P<fence>(?P<c>[`~])(?P=c){2,})[ \t]*(?P<info>[^\n]*)$")
BLOCKQUOTE = re.compile(r"^\s*>")
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
FIELD_LINE = re.compile(r"^\s*(\*\*[^*]{1,40}:\*\*\s*){2,}")
LIST_ITEM = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
INLINE_CODE = re.compile(r"`[^`\n]*`")


def line_kinds(text: str) -> list[str]:
    """One kind per line of ``text`` (split on "\\n", so the count matches
    ``text.split("\\n")``)."""
    out: list[str] = []
    fence_char, fence_len = None, 0
    for line in text.split("\n"):
        m = FENCE.match(line)
        if fence_char:
            out.append("code")
            if m and m.group("c") == fence_char and len(m.group("fence")) >= fence_len \
                    and not m.group("info").strip():
                fence_char, fence_len = None, 0
            continue
        if m and (m.group("c") == "~" or "`" not in m.group("info")):
            fence_char, fence_len = m.group("c"), len(m.group("fence"))
            out.append("code")
            continue
        if BLOCKQUOTE.match(line):
            out.append("blockquote")
        elif TABLE_ROW.match(line):
            out.append("table")
        elif HEADING.match(line):
            out.append("heading")
        elif FIELD_LINE.match(line):
            out.append("field")
        elif LIST_ITEM.match(line):
            out.append("list")
        elif not line.strip():
            out.append("blank")
        else:
            out.append("prose")
    return out


def blank(s: str) -> str:
    """Same-length whitespace: newlines stay, every other character is a space."""
    return re.sub(r"[^\n]", " ", s)


def mask(text: str, kinds=("code",), inline_code: bool = True) -> str:
    """``text`` with every line of a kind in ``kinds`` blanked, and (by default)
    inline code spans blanked on the lines that remain. Length and line
    structure are unchanged, so offsets computed on the result point into the
    original."""
    kinds = set(kinds)
    lines = text.split("\n")
    kind = line_kinds(text)
    out = []
    for line, k in zip(lines, kind):
        if k in kinds:
            out.append(blank(line))
        elif inline_code and k != "code":
            out.append(INLINE_CODE.sub(lambda m: blank(m.group(0)), line))
        else:
            out.append(line)
    return "\n".join(out)


def strip_inline_code(text: str) -> str:
    return INLINE_CODE.sub(lambda m: blank(m.group(0)), text)


def heading_text(line: str) -> str | None:
    """The text of an ATX heading line, or None."""
    m = HEADING.match(line)
    return m.group(1).strip() if m else None


def is_list_item(line: str) -> bool:
    return bool(LIST_ITEM.match(line))
