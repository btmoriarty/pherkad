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

    frame         A syntactic template recurring across the document's
                  headings, sentences, or paragraph closers ("X, not Y"
                  on five titles). Document-level; the units are quoted.
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
    structlint.py --config OVERLAY  # thresholds from a "structure" object

Thresholds live in the same JSON file voicelint reads, under a "structure"
object, with the same overlay semantics (a downstream config sets only the
keys it changes):

    "structure": {"short_chars": 46, "two_beat_diff": 14, "staccato_run": 3,
                  "density_per_100": 2.0, "interrogative_pct": 30,
                  "interrogative_min": 10}

Findings carry voicelint's shape (line, col, severity, rule, match, message,
rule_id), so one consumer can read both tools; rule ids are structure.<check>.

Exit codes: 0 clean (or warnings without --strict), 1 warnings under --strict,
2 on a usage or IO problem. Safe in CI.

Suppression, matching voicelint's comment syntax:
    <!-- structlint: ignore-line -->        suppresses the line it sits on
    <!-- structlint: ignore-next-line -->   suppresses the following line
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mdmask  # noqa: E402  (the shared reading of Markdown structure)

# Thresholds. These are the defaults; a "structure" object in the voicelint
# config (shipped or overlay) overrides any of them, see load_thresholds().
DEFAULT_THRESHOLDS = {
    "short_chars": 46,        # a "short" sentence for the run and parallel checks
    "two_beat_diff": 14,      # max length difference between the two beats
    "staccato_run": 3,        # consecutive short sentences before it counts as a run
    "density_per_100": 2.0,   # flagged constructions per 100 words
    "interrogative_pct": 30.0,  # percent of headings before the rate fires
    "interrogative_min": 10,    # headings needed before the rate means anything
    # The repeated-frame check (2026-09-16), three unit kinds, each with a count
    # floor and a share, or an absolute count that fires regardless of share.
    "frame_heading_min": 3,     # matching headings needed
    "frame_heading_share": 0.10,  # ... and this share of eligible headings and subtitles
    "frame_heading_abs": 5,     # or this many matching headings, whatever the share
    "frame_sentence_min": 8,    # matching sentences needed
    "frame_sentence_share": 0.15,  # ... and this share of all sentences
    "frame_closer_min": 3,      # matching paragraph closers needed
    "frame_closer_share": 0.40,  # ... and this share of long paragraphs
}

# A frame is a syntactic template a writer can fall into across a document: no
# single instance is a fault, the recurrence is. Found on two lecture decks
# (five or six titles on one mould) and a paper (one sentence in four, five
# paragraph closers in eleven) on 2026-09-15 and 16, by the judgment pass; the
# phrase layer saw nothing because each instance is a true contrast. This check
# reads the whole document: its headings, its sentences, and the closing
# sentence of each long paragraph, and reports one advisory finding per frame
# per unit kind when the recurrence clears the thresholds above.
FRAMES = {
    # Each frame has a loose pattern for titles (a short unit, where a bare "not"
    # is almost always the foil) and a strict one for running sentences.
    # "X, not Y" / "X rather than Y" / "not X but Y" / "X is not Y": the contrastive foil
    "contrast": {
        "title": re.compile(r",\s*(?:and\s+)?not\b|\brather than\b|\b(?:is|are|was|were)\s+not\b|\bnot\b.*\bbut\b", re.I),
        "sentence": re.compile(
            r",\s*(?:and\s+)?not\s+(?:a|an|the|as|merely|only|about|just|one|some|because|of|to|in|by|that|what|whether)\b"
            r"|\brather than\b"
            r"|;\s*not\s+\w"
            r"|\bnot\s+(?:a|an|the|as|merely|only)\b[^.;:]{2,60}?\bbut\b", re.I),
    },
    # "The one thing that ...", "The thing nobody ..."
    "the-one-thing": {
        "title": re.compile(r"^\s*the\s+(?:one\s+)?(?:thing|part|piece)\s+(?:that|nobody|no one|everyone|most)\b", re.I),
        "sentence": re.compile(r"\bthe\s+(?:one\s+)?(?:thing|part|piece)\s+(?:that|nobody|no one|everyone|most)\b", re.I),
    },
    # "What X gets wrong", "What everyone misses"
    "what-gets-wrong": {
        "title": re.compile(r"^\s*what\s+.{1,40}?\s+(?:gets? wrong|misses|forgets|gets? right)\b", re.I),
        "sentence": re.compile(r"\bwhat\s+.{1,40}?\s+(?:gets? wrong|misses|forgets|gets? right)\b", re.I),
    },
    # "Why X matters"
    "why-matters": {
        "title": re.compile(r"^\s*why\s+.{1,40}?\s+matters?\b", re.I),
        "sentence": re.compile(r"\bwhy\s+.{1,40}?\s+matters?\b", re.I),
    },
}

# Headers that pose rather than name. Deliberately narrow: each is a stance,
# not a subject. Broad patterns here produce noise and get ignored, which is
# worse than missing one.
HEADER_STANCE = [
    r"^(the|a)\s+(one\s+)?(thing|part|piece|bit|one)\s+(that|nobody|no one|everyone|most)\b",
    r"^why\s+(this|that|it)\s+matters\b",
    r"^what\s+(everyone|nobody|no one|most people)\s+(misses|gets wrong|forgets)\b",
    r"^the\s+\w+\s+(nobody|no one)\s+\w+",
    r"^here'?s\s+(the|what|why)\b",
    # "The real problem", "The actual question": a stance noun after the
    # adjective. "The actual results" names its subject and is left alone.
    r"^(the real|the actual)\s+(problem|question|issue|reason|cost|point|story|answer|"
    r"lesson|risk|danger|work|win|fix|test|challenge|trick|secret|lever|tell)\b",
    r"^what\s+.{0,40}\s+is\s+really\b",
    r"\bis\s+the\s+(point|moment|whole|tell)\b",
    # An abstract subject that "carries" an abstract object. Literal and
    # precise uses are common and fine ("how a chart carries a value"), so
    # this fires only in a header, where the construction is doing rhetoric.
    r"^(design|structure|the \w+)\s+that\s+carr(ies|y)\b",
    r"\bcarr(ies|y)\s+(a|the)\s+(decision|argument|weight|meaning|story)\b",
    # Positioning rather than naming: "Where Stage 3 Sits", "Where this sits".
    # "lives" and "goes" are out on purpose. They also mean literal placement,
    # and "Where data lives" over a file path is naming its subject, not posing.
    # The subject has to be an abstraction or a pointer: "Where this sits",
    # "Where Stage 3 Sits", "Where the argument stands". "Where the chair sits"
    # is a chair.
    r"^where\s+(this|that|it|we|you|each|the\s+(?:\w+\s+)?(?:stage|step|phase|work|argument|"
    r"claim|decision|method|tool|course|project|lab|study|paper|idea|risk|value|cost|"
    r"reader|user|field|line)|(?:stage|step|phase|week|round|part|section)\s+\w+)"
    r"\s+(sits|fits|stands|belongs)\b",
    # A header that poses the definition as a question instead of naming the
    # thing: "What Counts as Working", "What Makes a Prompt Analytical". The
    # subject is the definition, so the header can be the term itself.
    r"^what\s+(counts as|makes|qualifies as)\b",
]

# Which lines are code, blockquotes, tables, headings, field lines, and list
# items is decided once, in mdmask.py, for this tool and voicelint alike.
LIST_ITEM = mdmask.LIST_ITEM
BLOCKQUOTE = mdmask.BLOCKQUOTE
# A bold run-in label ("**Null propagation.** The rest...") ends in a period
# that is not a sentence boundary. Strip the label before splitting.
RUNIN_LABEL = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?\*\*[^*]{1,90}?\*\*:?\s*")
HEADER_LINE = mdmask.HEADING
# A period is not always a sentence boundary. Initials ("W. H."), common
# abbreviations, and ordinals in citations all end in one, and treating them as
# boundaries turned bibliographies into staccato runs.
ABBREV = (r"(?<!\b[A-Z])(?<!\bvs)(?<!\bcf)(?<!\bal)(?<!\beds)(?<!\bed)(?<!\bpp)"
          r"(?<!\bno)(?<!\bvol)(?<!\bArt)(?<!\bFig)(?<!\bapprox)(?<!\best)"
          r"(?<!\bDr)(?<!\bMr)(?<!\bMs)(?<!\bSt)(?<!\betc)(?<!\bi\.e)(?<!\be\.g)")
SENT_SPLIT = re.compile(ABBREV + r"(?<=[.!?])\s+")
FIELD_LINE = mdmask.FIELD_LINE
# A bibliographic entry is punctuation-dense by convention: a year in
# parentheses, a DOI, a URL, or a volume-and-article run. Its rhythm is the
# citation style's, not the author's, so it is not theirs to answer for.
CITATION = re.compile(r"\((?:19|20)\d\d\)|\bDOI\b|https?://|\barXiv\b|\bpp\.\s*\d", re.I)
# A quoted span of sixty characters or more carries its speaker's rhythm, not
# the author's; it is masked in place by _MASK_SPANS below, and the rest of the
# line is still the author's prose.
# "Stage 1: ... Stage 2: ..." is an enumeration, not prose rhythm. Two or more
# labeled steps on a line means the periods are separating items in a list that
# happens to be written inline.
# A whole line wrapped in square brackets is a fill-in placeholder in a template
# ("[How are variables encoded? What does it de-emphasize?]"), not the author's
# prose. The questions are prompts for the student to replace. Found 2026-08-21
# across the A1-A5 templates.
BRACKET_PLACEHOLDER = re.compile(r"^\s*\[.*\]\s*$", re.S)

# A heading that opens with a question word is a fragment standing in where a
# name should be: the heading asks and the section immediately answers, so the
# question does no work. One or two is fine and often clearest, so this is a
# RATE check across a document rather than a per-heading rule. Genuine questions
# ending in "?" are correct usage and excluded. Calibrated 2026-08-23 across
# fourteen decks: documents that read well sat at 4-16%, flagged ones at 20-25%.
INTERROGATIVE_HEAD = re.compile(r"^(what|where|why|how|when|which|who)\b", re.I)
# Prose is calibrated separately from slide decks and the numbers differ, which
# is a real difference rather than a fudge. A deck IS its titles, so the rate
# separates cleanly there: 4-16% for decks that read well against 20-25% for
# decks flagged as AI voice. Prose headings are navigation over text that carries
# its own meaning, so "What Week 5 Covered" is fine and house conventions push
# every document up. Measured across 137 documents on 2026-08-23 the prose
# distribution is smooth with no gap: median 12.5%, a long tail to 50%. A
# tail-only threshold is therefore the honest setting.
# (interrogative_pct 30 and interrogative_min 10 live in DEFAULT_THRESHOLDS.)

TABLE_ROW = mdmask.TABLE_ROW

LABELED_STEPS = re.compile(
    r"\b(stage|step|round|question|phase|prompt|slide)\s+\d+\s*:", re.I)

# The manufactured maxim: a comparative weighed against an elliptical negation
# ("a source you find yourself and finish is worth more than one from this page
# that you do not"). The symmetry sits inside one sentence, so the two-beat
# check cannot see it. It reads as earned wisdom and asserts nothing; it is the
# cheapest way to make a paragraph feel finished, which is why it arrives at
# the end of one. Both halves are required, so a plain comparison is safe.
APHORISM_CMP = re.compile(
    r"\b(?:worth\s+(?:more|less)|more|less|better|worse|stronger|weaker|"
    r"cheaper|faster|safer|harder|easier)\s+than\b", re.I)
_NEG = r"(?:do|does|did|is|are|was|were|will|would|can|could|have|has|had)\s*n[o’']t"
APHORISM_TAIL = re.compile(
    r"\b(?:that|than|which|who)\s+"
    r"(?:(?:you|it|they|we|one|he|she|others?|most)\s+)?"
    + _NEG + r"\b\s*[.!?\"]*$", re.I)


@dataclass
class Finding:
    """voicelint's finding shape, so one consumer reads both tools. ``rule``
    is the check (two-beat, staccato, header, aphorism, interrogative-headers,
    density) and ``rule_id`` is structure.<check>. ``col`` is 1 for a paragraph
    or heading finding and 0 for the document-level density."""
    line: int
    col: int
    severity: str
    rule: str
    match: str
    message: str
    rule_id: str = ""

    def __init__(self, line, rule, match, message, col=None, severity="warning", rule_id=None):
        self.line = line
        self.col = (1 if line else 0) if col is None else col
        self.severity = severity
        self.rule = rule
        self.match = match
        self.message = message
        self.rule_id = rule_id or "structure." + rule

    @property
    def excerpt(self):  # the old name, kept for callers that used it
        return self.match


# Masked in place, not dropped with the line: a URL, a DOI, an arXiv id, a
# year in parentheses, a page run, or a long quoted span. The rest of the
# line is still the author's prose and still gets checked. A whole
# bibliographic entry (author-and-initial opener, or two or more markers) is
# the citation style's rhythm and is dropped as before.
_MASK_SPANS = re.compile(
    r'https?://[^\s)\]>"\']+|\bDOI\b:?\s*\S+|\barXiv\b:?\s*\S+'
    r'|\((?:19|20)\d\d[a-z]?\)|\bpp\.\s*\d+(?:\s*[-–]\s*\d+)?|"[^"]{60,}"', re.I)
_BIB_LINE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?[A-Z][\w'’-]+,\s+(?:[A-Z]\.\s*)+")


def _mask_spans(ln: str) -> str:
    """Blank the spans that are not the author's prose; keep the line."""
    return _MASK_SPANS.sub(lambda m: "URL" if m.group(0).lower().startswith("http") else " ", ln)


def _is_bibliographic(ln: str) -> bool:
    return bool(_BIB_LINE.match(ln)) or len(CITATION.findall(ln)) >= 2


_STOP = frozenset("a an the of to in on at for and or but is are was were be it its this that these those".split())
_NEG = re.compile(r"\b(?:not|no|never|none|nothing|nobody|nor)\b|n[o’']t\b", re.I)


def _parallel(a: str, b: str) -> bool:
    """Do two short sentences share a shape, not just a length?

    A two-beat is a construction, and the construction shows in the words:
    the same opener ("None of them wrong. None of them ours."), matched
    negation, the same closing word, or the same token count with a repeated
    content word. Two short sentences that merely sit side by side ("The
    meeting starts at nine. Lunch follows at noon.") share none of that."""
    ta = re.findall(r"[\w'’]+", a.lower())
    tb = re.findall(r"[\w'’]+", b.lower())
    if not ta or not tb:
        return False
    if ta[0] == tb[0]:
        return True
    if ta[-1] == tb[-1]:
        return True
    if _NEG.search(a) and _NEG.search(b):
        return True
    shared = (set(ta) & set(tb)) - _STOP
    return abs(len(ta) - len(tb)) <= 1 and len(shared) >= 1


def load_thresholds(config_path: str | None) -> dict:
    """DEFAULT_THRESHOLDS updated by the "structure" object of the voicelint
    config: the shipped file beside this script, then the overlay given here.
    Uses voicelint's own loader so overlay semantics are identical; when
    voicelint is not beside this script the defaults stand."""
    t = dict(DEFAULT_THRESHOLDS)
    try:
        sys.path.insert(0, HERE)
        import voicelint  # noqa: WPS433
    except ImportError:
        if config_path:
            sys.stderr.write("structlint: voicelint.py not found beside structlint.py; "
                             "--config ignored, default thresholds used\n")
        return t
    cfg = voicelint.load_config(config_path)
    for k, v in (cfg.get("structure") or {}).items():
        if k in t:
            t[k] = v
    return t


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
    """Blank fenced and inline code, keeping line numbers intact (mdmask)."""
    return mdmask.mask("\n".join(lines), ("code",)).split("\n")


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in SENT_SPLIT.split(text) if p.strip()]
    # A clause ending in a colon is a lead-in to what follows, not a sentence
    # standing on its own, so it cannot be half of a two-beat parallel.
    return [p for p in parts if len(p) > 1 and not p.endswith(":")]


def check_frames(lines: list[str], heads: list[tuple[int, str]], paras: list[tuple[int, str]], t: dict) -> list[Finding]:
    """One advisory finding per frame per unit kind, when a frame recurs across
    the document's headings, its sentences, or its paragraph closers past the
    thresholds. The finding's match lists every unit that carries the frame,
    which is what a decision on it hashes: change one of them and the finding
    is new again. Excluded from density by the combined runner."""
    out: list[Finding] = []
    # units: headings, plus the short line right under a heading (a slide's
    # subtitle or section tagline, where the deck frames lived); sentences of
    # every prose paragraph; the last sentence of every long paragraph
    titles: list[tuple[int, str]] = list(heads)
    for i, _h in heads:
        if i < len(lines):
            nxt = lines[i].strip()
            if nxt and len(nxt.split()) <= 14 and not nxt.isupper() and not LIST_ITEM.match(nxt) \
                    and not TABLE_ROW.match(nxt) and not HEADER_LINE.match(nxt):
                titles.append((i + 1, nxt))
    titles.sort()
    sentences: list[tuple[int, str]] = []
    closers: list[tuple[int, str]] = []
    for i, body in paras:
        sents = _sentences(RUNIN_LABEL.sub("", body))
        sentences.extend((i, s_) for s_ in sents)
        if len(body.split()) >= 40 and sents:
            closers.append((i, sents[-1]))
    # The heading share is taken over the headings themselves (the slides, the
    # sections), while hits are counted over headings and subtitles: five of
    # thirty-nine slides carrying the frame in their title text is the case.
    kinds = (
        ("heading", titles, len(heads), int(t["frame_heading_min"]), float(t["frame_heading_share"]), int(t["frame_heading_abs"])),
        ("sentence", sentences, len(sentences), int(t["frame_sentence_min"]), float(t["frame_sentence_share"]), 0),
        ("closer", closers, len(closers), int(t["frame_closer_min"]), float(t["frame_closer_share"]), 0),
    )
    for name, pats in FRAMES.items():
        for kind, units, total, floor, share, absolute in kinds:
            if not units or not total:
                continue
            pat = pats["title"] if kind == "heading" else pats["sentence"]
            hits = [(i, u) for i, u in units if pat.search(u)]
            n = len(hits)
            fires = (n >= floor and n / total >= share) or (absolute and n >= absolute)
            if not fires:
                continue
            quoted = "; ".join(u.strip()[:70] for _, u in hits[:6]) + (" ..." if n > 6 else "")
            out.append(Finding(hits[0][0], "frame",
                               f"{n}/{total} {kind}s: {quoted}",
                               f"the '{name}' frame recurs across {n} of {total} {kind}s; "
                               f"no one is wrong, the repetition is the tell",
                               rule_id=f"structure.frame.{name}.{kind}"))
    return out


def check_text(raw: str, thresholds: dict | None = None) -> list[Finding]:
    t = dict(DEFAULT_THRESHOLDS)
    t.update(thresholds or {})
    SHORT, STACCATO_RUN = int(t["short_chars"]), int(t["staccato_run"])
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
        if (i in skip or not ln.strip() or BLOCKQUOTE.match(ln)
                or HEADER_LINE.match(ln) or FIELD_LINE.match(ln)
                or TABLE_ROW.match(ln) or BRACKET_PLACEHOLDER.match(ln)
                or _is_bibliographic(ln)):
            flush()
        else:
            if not buf:
                start = i
            buf.append(_mask_spans(ln))
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
        if body != ln:
            # A bold run-in label marks a field ("**Mitigation:** do this, do
            # that"), and a field's content is usually instructions, which
            # voice-rules says may be clipped.
            continue

        # two-beat: a clipped balanced parallel standing alone on the line
        if len(sents) == 2 and all(len(s) <= SHORT for s in sents):
            a, b = sents
            if (abs(len(a) - len(b)) <= int(t["two_beat_diff"]) and a[:1].isupper()
                    and b[:1].isupper() and _parallel(a, b)):
                found.append(Finding(i, "two-beat", ln.strip()[:80],
                                     "clipped balanced parallel; the symmetry is the tell"))

        # aphorism: comparative plus an elliptical negation tail, in one sentence
        for s_ in sents:
            if APHORISM_CMP.search(s_) and APHORISM_TAIL.search(s_):
                found.append(Finding(i, "aphorism", s_.strip()[:80],
                                     "manufactured maxim; state the point or cut it"))
                break

        # staccato: a run of consecutive short sentences, prose only
        run = 0
        if is_list or len(LABELED_STEPS.findall(ln)) >= 2:
            continue
        for s in sents:
            run = run + 1 if len(s) <= SHORT else 0
            if run >= STACCATO_RUN:
                found.append(Finding(i, "staccato", ln.strip()[:80],
                                     f"{run} short sentences in a row; merge them"))
                break

    # interrogative headings: a document-level rate, not a per-line judgement
    heads = []
    for i, ln in enumerate(lines, 1):
        if i in skip:
            continue
        hm = HEADER_LINE.match(ln)
        if hm:
            heads.append((i, hm.group(1).strip()))
    if len(heads) >= int(t["interrogative_min"]):
        q = [(i, h) for i, h in heads
             if INTERROGATIVE_HEAD.match(h) and not h.rstrip().endswith("?")]
        pct = 100.0 * len(q) / len(heads)
        if pct > float(t["interrogative_pct"]):
            found.append(Finding(q[0][0], "interrogative-headers",
                                 f"{len(q)}/{len(heads)} headings",
                                 f"{pct:.0f}% of headings open with a question word; "
                                 f"name the sections instead"))

    found.extend(check_frames(lines, heads, paras, t))

    words = len(re.findall(r"\b\w+\b", "\n".join(lines)))
    cap = float(t["density_per_100"])
    if words >= 100:
        per100 = len(found) * 100.0 / words
        if per100 > cap:
            found.append(Finding(0, "density", f"{len(found)} hits / {words} words",
                                 f"{per100:.1f} per 100 words, over the {cap} cap"))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="Flag structural writing tells that phrases cannot match.")
    ap.add_argument("files", nargs="+", help="files to check, or - for stdin")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="warnings cause a non-zero exit")
    ap.add_argument("--config", help="voicelint config (overlay) whose \"structure\" object sets the thresholds")
    args = ap.parse_args()

    thresholds = load_thresholds(args.config)
    total, payload = 0, {}
    for path in args.files:
        try:
            raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
        except OSError as exc:
            sys.stderr.write(f"structlint: cannot read {path}: {exc}\n")
            return 2
        findings = check_text(raw, thresholds)
        payload[path] = [asdict(f) for f in findings]
        for f in findings:
            total += 1
            if not args.json:
                where = f"{path}:{f.line}:{f.col}" if f.line else path
                print(f"{where} [{f.severity}] {f.rule} ({f.rule_id}): {f.message}  ->  {f.match!r}")

    if args.json:
        # The same envelope as voicelint --json, so one consumer reads both.
        print(json.dumps({"suppressed": 0, "files": payload}, indent=2, ensure_ascii=False))
    else:
        print(f"structlint: {total} warning(s) across {len(args.files)} file(s).")
    return 1 if (args.strict and total) else 0


if __name__ == "__main__":
    sys.exit(main())
