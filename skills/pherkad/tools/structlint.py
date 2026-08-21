#!/usr/bin/env python3
"""structlint.py - the structural half of the mechanical voice layer.

Companion to voicelint.py, not a replacement and not a fork. voicelint matches
phrases; this matches sentence and header SHAPE, which is what phrases cannot
reach. Between them they cover the families named in voice-authoring.md under
"The linter is the last check, not the check" (2026-08-15):

    dramatic stance headers, the empty-emphasis frame, compressed antithesis,
    forward pointers, over-compressed allusive phrasing

The phrase-shaped half of that list lives in voice_config.json as soft_phrases.
The four checks here are the ones with no string to match:

    two-beat      A clipped balanced parallel. Two short sentences side by
                  side, similar length. The neat symmetry is the tell, and
                  voice-rules Bucket 2 flags it even as a single instance.
    staccato      Three or more consecutive short sentences. RULING C1: one
                  emphatic short sentence after a longer one is the voice; a
                  run of them is the tell.
    header        A header or slide title that strikes a pose instead of
                  naming its subject.
    density       More than two flagged constructions per 100 words, which
                  voice-rules calls a warning even when no single hit forces
                  a revision.

Everything here is a WARNING. These are judgment calls that over-fire by
design, in the same way voice-authoring.md says the empty-emphasis rule
over-fires on bare strings. The output is a list for a human glance, never a
verdict, and never an automated rewrite.

Usage:
    structlint.py FILE [FILE ...]
    structlint.py --json FILE
    structlint.py --strict FILE     # warnings become a non-zero exit

Exit codes: 0 clean (or warnings without --strict), 1 warnings under --strict,
2 on a usage or IO problem. Safe in CI.

Suppression, matching voicelint's comment syntax:
    <!-- structlint: ignore-line -->        suppresses the line it sits on
    <!-- structlint: ignore-next-line -->   suppresses the following line
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict

SHORT = 46          # chars; a "short" sentence for the run and parallel checks
STACCATO_RUN = 3    # consecutive short sentences before it counts as a run
DENSITY_PER_100 = 2.0

# Headers that pose rather than name. Deliberately narrow: each is a stance,
# not a subject. Broad patterns here produce noise and get ignored, which is
# worse than missing one.
HEADER_STANCE = [
    r"^(the|a)\s+(one\s+)?(thing|part|piece|bit|one)\s+(that|nobody|no one|everyone|most)\b",
    r"^why\s+(this|that|it)\s+matters\b",
    r"^what\s+(everyone|nobody|no one|most people)\s+(misses|gets wrong|forgets)\b",
    r"^the\s+\w+\s+(nobody|no one)\s+\w+",
    r"^here'?s\s+(the|what|why)\b",
    r"^(the real|the actual)\s+\w+",
    r"^what\s+.{0,40}\s+is\s+really\b",
    r"\bis\s+the\s+(point|moment|whole|tell)\b",
    # An abstract subject that "carries" an abstract object. Literal and
    # precise uses are common and fine ("how a chart carries a value"), so
    # this fires only in a header, where the construction is doing rhetoric.
    r"^(design|structure|the \w+)\s+that\s+carr(ies|y)\b",
    r"\bcarr(ies|y)\s+(a|the)\s+(decision|argument|weight|meaning|story)\b",
]

CODE_FENCE = re.compile(r"^\s*(```|~~~)")
# A list item or a numbered step is a format, not prose rhythm. RULING C1 is
# about consecutive short sentences in running prose; clipped instructions are
# correct, and voice-rules says so explicitly for slide closers.
LIST_ITEM = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
# A blockquote is usually a quoted prompt or a transcript, not the author's
# prose, so its rhythm is not theirs to answer for.
BLOCKQUOTE = re.compile(r"^\s*>")
# A bold run-in label ("**Null propagation.** The rest...") ends in a period
# that is not a sentence boundary. Strip the label before splitting.
RUNIN_LABEL = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?\*\*[^*]{1,90}?\*\*:?\s*")
HEADER_LINE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Finding:
    line: int
    rule: str
    excerpt: str
    message: str


def _suppressed(lines: list[str]) -> set[int]:
    """1-indexed line numbers the file asks us to skip."""
    out: set[int] = set()
    for i, ln in enumerate(lines, 1):
        if re.search(r"<!--\s*structlint:\s*ignore-line\s*-->", ln):
            out.add(i)
        if re.search(r"<!--\s*structlint:\s*ignore-next-line\s*-->", ln):
            out.add(i + 1)
    return out


def _strip_code(lines: list[str]) -> list[str]:
    """Blank out fenced code and inline code, keeping line numbers intact."""
    out, in_fence = [], False
    for ln in lines:
        if CODE_FENCE.match(ln):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else re.sub(r"`[^`]*`", " ", ln))
    return out


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in SENT_SPLIT.split(text) if p.strip()]
    # A clause ending in a colon is a lead-in to what follows, not a sentence
    # standing on its own, so it cannot be half of a two-beat parallel.
    return [p for p in parts if len(p) > 1 and not p.endswith(":")]


def check_text(raw: str) -> list[Finding]:
    lines = raw.splitlines()
    skip = _suppressed(lines)
    lines = _strip_code(lines)
    found: list[Finding] = []

    # Hard-wrapped markdown puts one sentence across several lines, so a
    # line-by-line read sees a sentence ending mid-line as a two-beat that is
    # not there. Group consecutive non-blank prose lines into a paragraph and
    # check that, reporting against the paragraph's first line.
    paras: list[tuple[int, str]] = []
    buf: list[str] = []
    start = 0
    def flush():
        if buf:
            paras.append((start, " ".join(x.strip() for x in buf)))
            buf.clear()

    for i, ln in enumerate(lines, 1):
        if i in skip or not ln.strip() or BLOCKQUOTE.match(ln) or HEADER_LINE.match(ln):
            flush()
        else:
            if not buf:
                start = i
            buf.append(ln)
            continue
        if i in skip or not ln.strip() or BLOCKQUOTE.match(ln):
            continue

        hm = HEADER_LINE.match(ln)
        if hm:
            h = hm.group(1).strip()
            for pat in HEADER_STANCE:
                if re.search(pat, h, re.I):
                    found.append(Finding(i, "header", h[:70],
                                         "header strikes a pose; name the subject instead"))
                    break
            continue

        continue

    flush()
    for i, ln in paras:
        body = RUNIN_LABEL.sub("", ln)
        sents = _sentences(body)
        is_list = bool(LIST_ITEM.match(ln))
        # A definition bullet ("- **Term:** gloss. More gloss.") naturally
        # falls into two beats without being the construction. Skip both
        # checks there; a real two-beat in running prose is still caught.
        if is_list and body != ln:
            continue

        # two-beat: a clipped balanced parallel standing alone on the line
        if len(sents) == 2 and all(len(s) <= SHORT for s in sents):
            a, b = sents
            if abs(len(a) - len(b)) <= 14 and a[:1].isupper() and b[:1].isupper():
                found.append(Finding(i, "two-beat", ln.strip()[:80],
                                     "clipped balanced parallel; the symmetry is the tell"))

        # staccato: a run of consecutive short sentences, prose only
        run = 0
        if is_list:
            continue
        for s in sents:
            run = run + 1 if len(s) <= SHORT else 0
            if run >= STACCATO_RUN:
                found.append(Finding(i, "staccato", ln.strip()[:80],
                                     f"{run} short sentences in a row; merge them"))
                break

    words = len(re.findall(r"\b\w+\b", "\n".join(lines)))
    if words >= 100:
        per100 = len(found) * 100.0 / words
        if per100 > DENSITY_PER_100:
            found.append(Finding(0, "density", f"{len(found)} hits / {words} words",
                                 f"{per100:.1f} per 100 words, over the {DENSITY_PER_100} cap"))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="Flag structural writing tells that phrases cannot match.")
    ap.add_argument("files", nargs="+", help="files to check, or - for stdin")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="warnings cause a non-zero exit")
    args = ap.parse_args()

    total, payload = 0, []
    for path in args.files:
        try:
            raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
        except OSError as exc:
            sys.stderr.write(f"structlint: cannot read {path}: {exc}\n")
            return 2
        for f in check_text(raw):
            total += 1
            if args.json:
                payload.append({"file": path, **asdict(f)})
            else:
                where = f"{path}:{f.line}" if f.line else path
                print(f"{where} [warning] {f.rule}: {f.message}  ->  {f.excerpt!r}")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"structlint: {total} warning(s) across {len(args.files)} file(s).")
    return 1 if (args.strict and total) else 0


if __name__ == "__main__":
    sys.exit(main())
