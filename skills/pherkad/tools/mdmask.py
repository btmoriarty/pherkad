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
                as long, by the end of its list item, or by the end of the file;
                an indented code block; a pre, script, style or textarea block
    comment     an HTML comment block, to its closing -->
    blockquote  a line starting with ">" (someone else's words), and the lazy
                lines that continue it
    table       a pipe-delimited table row, delimiter rows included
    heading     an ATX heading, or a setext heading and its underline
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

KINDS = ("code", "comment", "blockquote", "table", "heading", "field", "list", "blank", "prose")

FENCE = re.compile(r"^[ \t]{0,3}(?P<fence>(?P<c>[`~])(?P=c){2,})[ \t]*(?P<info>[^\n]*)$")
BLOCKQUOTE = re.compile(r"^ {0,3}>")
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
# linear on long whitespace runs; the old pattern backtracked cubically (I071)
HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+(.*))?$")  # group 1 carries trailing space; callers strip
FIELD_LINE = re.compile(r"^\s*(\*\*[^*]{1,40}:\*\*\s*){2,}")
LIST_ITEM = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
INLINE_CODE = re.compile(r"`[^`\n]*`")

# One character for one: typographic quotes and the modifier apostrophe to ASCII
# quotes, the no-break and thin spaces to a space, the non-breaking and Unicode
# hyphens to '-'. Offsets are preserved. Shared so voicelint and structlint read
# the same characters (I096).
FOLD = {0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x02BC: "'",
        0x00A0: " ", 0x202F: " ", 0x2007: " ", 0x2009: " ", 0x200A: " ", 0x2002: " ", 0x2003: " ",
        0x2004: " ", 0x2005: " ", 0x2006: " ", 0x2008: " ", 0x2010: "-", 0x2011: "-"}


def fold(text: str) -> str:
    return text.translate(FOLD)


def _indent(line: str) -> tuple[int, int]:
    """(columns of leading whitespace with tabs to the next multiple of 4, index of the first other character)."""
    col = 0
    for i, ch in enumerate(line):
        if ch == " ":
            col += 1
        elif ch == "\t":
            col += 4 - col % 4
        else:
            return col, i
    return col, len(line)


_FENCE_OPEN = re.compile(r"(?P<fence>(?P<c>[`~])(?P=c){2,})[ \t]*(?P<info>[^\n]*)$")
_SETEXT = re.compile(r"(?:=+|-+)[ \t]*$")
_HTML1 = re.compile(r"<(pre|script|style|textarea)(?:[\s>]|$)", re.I)
_LIST_MARK = re.compile(r"([-*+]|\d{1,9}[.)])([ \t]+|$)")


def line_kinds(text: str) -> list[str]:
    """One kind per line of ``text`` (split on "\\n", so the count matches
    ``text.split("\\n")``).

    A line reader that keeps the block state CommonMark needs for what this
    tool masks (I070, I073): a fence opened inside a list item closes at the
    first line indented less than the item's content; a line indented four
    columns after a blank (outside a list) is code; tabs count to the next
    multiple of four; a line right after a quoted line is quoted too unless it
    starts a block of its own; a line of = or - under prose makes a setext
    heading; an HTML comment and a pre, script, style or textarea block run to
    their terminator, and no fence is read inside them."""
    lines = text.split("\n")
    out: list[str] = []
    fence = None      # (char, length, container column) of an open fence
    html_end = None   # (compiled terminator, kind) of an open HTML block
    list_col = None   # content column of the innermost open list item
    prev = None       # the previous line's kind
    for line in lines:
        ind, first = _indent(line)
        body = line[first:]
        blank_line = not body.strip()
        if html_end:
            out.append(html_end[1])
            if html_end[0].search(line):
                html_end = None
            prev = out[-1]
            continue
        if fence:
            c, n, container = fence
            if not blank_line and container and ind < container:
                fence = None  # the list item ended, and its unclosed fence with it
            else:
                m = _FENCE_OPEN.match(body)
                if m and m.group("c") == c and len(m.group("fence")) >= n and not m.group("info").strip() \
                        and ind - container <= 3:
                    fence = None
                out.append("code")
                prev = "code"
                continue
        if list_col is not None and not blank_line and ind < list_col and not _LIST_MARK.match(body) \
                and prev == "blank":
            list_col = None
        rel = ind - list_col if list_col is not None and ind >= list_col else ind
        container = list_col if list_col is not None and ind >= list_col else 0
        m = _FENCE_OPEN.match(body)
        if not blank_line and rel <= 3 and m and (m.group("c") == "~" or "`" not in m.group("info")):
            fence = (m.group("c"), len(m.group("fence")), container)
            kind = "code"
        elif not blank_line and rel <= 3 and body.startswith("<!--"):
            kind = "comment"
            if "-->" not in body[4:]:
                html_end = (re.compile(r"-->"), "comment")
        elif not blank_line and rel <= 3 and _HTML1.match(body):
            kind = "code"
            tag = _HTML1.match(body).group(1)
            if not re.search(rf"</{tag}\s*>", body, re.I):
                html_end = (re.compile(rf"</{tag}\s*>", re.I), "code")
        elif not blank_line and ind >= 4 and list_col is None and prev in (None, "blank", "code"):
            kind = "code"  # an indented code block: a paragraph cannot be interrupted by one
        elif not blank_line and ind <= 3 and body.startswith(">"):
            kind = "blockquote"
        elif TABLE_ROW.match(line):
            kind = "table"
        elif ind <= 3 and HEADING.match(body):
            kind = "heading"
        elif ind <= 3 and _SETEXT.match(body) and prev == "prose":
            kind = "heading"
            out[-1] = "heading"  # the underlined line is the heading's text
        elif FIELD_LINE.match(line):
            kind = "field"
        elif ind <= 3 + (list_col or 0) and _LIST_MARK.match(body) and not _SETEXT.match(body):
            kind = "list"
            mk = _LIST_MARK.match(body)
            list_col = ind + len(mk.group(1)) + max(1, min(4, len(mk.group(2).expandtabs(4)) or 1))
        elif blank_line:
            kind = "blank"
        elif prev == "blockquote":
            kind = "blockquote"  # lazy continuation of the quoted paragraph
        else:
            kind = "prose"
        out.append(kind)
        prev = kind
    return out


def blank(s: str) -> str:
    """Same-length whitespace: newlines stay, every other character is a space."""
    return re.sub(r"[^\n]", " ", s)


_TAG_OR_AUTOLINK = re.compile(r"<[A-Za-z][A-Za-z0-9+.-]{1,31}:[^\s<>]*>|</?[A-Za-z][^<>]*>|<!--.*?-->", re.S)
_CODE_ELEMENT = re.compile(r"<(code|kbd|samp|tt)\b[^>]*>.*?</\1\s*>", re.I | re.S)


def code_spans(s: str) -> list[tuple[int, int]]:
    """Inline code spans in a paragraph, as CommonMark pairs them (I072, I073):
    a run of backticks opens a span closed by the next run of the same length,
    across line breaks; a backslash-escaped backtick opens nothing; backticks
    inside an autolink or an HTML tag are not code. Plus the contents of
    <code>, <kbd>, <samp> and <tt> (I074)."""
    spans, i, n = [], 0, len(s)
    while i < n:
        ch = s[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "<":
            m = _TAG_OR_AUTOLINK.match(s, i)
            if m:
                i = m.end()
                continue
        if ch == "`":
            j = i
            while j < n and s[j] == "`":
                j += 1
            run = j - i
            close = re.compile(rf"(?<!`)`{{{run}}}(?!`)").search(s, j)
            if close:
                spans.append((i, close.end()))
                i = close.end()
                continue
            i = j
            continue
        i += 1
    spans.extend(m.span() for m in _CODE_ELEMENT.finditer(s))
    return spans


def _blank_spans(s: str, spans) -> str:
    chars = list(s)
    for a, b in spans:
        for k in range(a, b):
            if chars[k] != "\n":
                chars[k] = " "
    return "".join(chars)


def mask(text: str, kinds=("code",), inline_code: bool = True) -> str:
    """``text`` with every line of a kind in ``kinds`` blanked, and (by default)
    inline code blanked in the paragraphs that remain. Length and line
    structure are unchanged, so offsets computed on the result point into the
    original."""
    kinds = set(kinds)
    lines = text.split("\n")
    kind = line_kinds(text)
    out = [blank(ln) if k in kinds else ln for ln, k in zip(lines, kind)]
    if inline_code:
        # a code span may cross a line break inside a paragraph, so spans are paired per paragraph
        i = 0
        while i < len(out):
            if kind[i] in ("code", "blank", "comment") or kind[i] in kinds:
                i += 1
                continue
            j = i
            while j < len(out) and kind[j] not in ("code", "blank", "comment") and kind[j] not in kinds:
                j += 1
            para = "\n".join(out[i:j])
            out[i:j] = _blank_spans(para, code_spans(para)).split("\n")
            i = j
    return "\n".join(out)


def strip_inline_code(text: str) -> str:
    return _blank_spans(text, code_spans(text))


def heading_text(line: str) -> str | None:
    """The text of an ATX heading line, or None. A closing run of '#' goes
    when a space precedes it, so '# C#' stays 'C#' (I071)."""
    m = HEADING.match(line)
    if not m:
        return None
    t = (m.group(1) or "").rstrip()
    stripped = re.sub(r"(?:^|[ \t]+)#+$", "", t)
    return stripped.strip()


def is_list_item(line: str) -> bool:
    return bool(LIST_ITEM.match(line))
