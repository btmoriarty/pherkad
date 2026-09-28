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

# The implementation revision of each structural check. A decision on a
# structural finding is hashed with the rule's thresholds AND this number, so
# changing how a check works (a regex, the parallelism test) wakes up every
# decision made under the old version. Bump the number when the behaviour of a
# check changes; leave it when only its thresholds move (those are hashed too).
STRUCT_REVISION = {
    "two-beat": 3,               # 2: the syntactic parallel test (0.5.6); 3: shape, closing pair (0.5.42)
    "staccato": 3,               # 2: spans masked rather than lines dropped (0.5.6); 3: abbreviations, list units (0.5.42)
    "header": 3,                 # 2: the real/actual and where-sits patterns tightened (0.5.6); 3: setext, numbering, narrower stance (0.5.42)
    "aphorism": 1,
    "interrogative-headers": 3,  # 2: document-scoped, all headings quoted (0.5.22); 3: setext headings (0.5.42)
    "frame": 2,                  # 2: advisory, medial "not", one unit per heading (0.5.42)
    "density": 2,                # 2: frames never count (0.5.42)
}

# The thresholds each check reads. A decision is hashed with these only, so a change to
# an unrelated threshold, or to a _comment, no longer wakes every structural decision (I134).
STRUCT_KEYS = {
    "two-beat": ("short_chars", "two_beat_diff"),
    "staccato": ("short_chars", "staccato_run"),
    "header": (),
    "aphorism": (),
    "interrogative-headers": ("interrogative_pct", "interrogative_min"),
    "frame": ("frame_heading_min", "frame_heading_share", "frame_heading_abs", "frame_sentence_min",
              "frame_sentence_share", "frame_closer_min", "frame_closer_share"),
    "density": ("density_per_100",),
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
        # a medial bare "not" in a title is the foil too: "Clarity not cleverness" (I049)
        "title": re.compile(r",\s*(?:and\s+)?not\b|\brather than\b|\b(?:is|are|was|were)\s+not\b|\bnot\b.*\bbut\b"
                            r"|^\S.{0,40}\bnot\s+\w", re.I),
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
    # "What you keep, what you change", "Twelve outputs, seven decisions",
    # "One question, four tools": two comma-joined halves with the same
    # opener or a count on each side, and no verb. A title that scans instead
    # of naming. Brian flagged three of these on FA550 decks between
    # 2026-09-13 and 2026-09-17; each was fine alone and the habit was the tell.
    "paired-beat": {
        "title": re.compile(
            r"^\s*(?:\d+[.)]\s*)?(?:(what|how|where|the|your|no|every|same)\s[^,]{1,30},\s*\1\s[^,]{1,30}"
            r"|(?:one|two|three|four|five|six|seven|eight|nine|ten|twelve|twenty|\d+)\s+\w+(?:\s\w+)?,"
            r"\s*(?:one|two|three|four|five|six|seven|eight|nine|ten|twelve|twenty|\d+)\s+\w+(?:\s\w+)?)\s*[.!]?\s*$", re.I),
        "sentence": re.compile(
            r"^\s*(?:(what|how|where)\s[^,]{1,30},\s*\1\s[^,]{1,30}"
            r"|(?:one|two|three|four|five|six|seven|eight|nine|ten|twelve|twenty|\d+)\s+\w+(?:\s\w+)?,"
            r"\s*(?:one|two|three|four|five|six|seven|eight|nine|ten|twelve|twenty|\d+)\s+\w+(?:\s\w+)?)\s*[.!]?\s*$", re.I),
    },
    # "Three layers, and tonight is the second visit", "One chart from start
    # to finish, then your discovery list", "The same paragraph, sent back
    # three ways", "Last week's patterns, now nameable": a noun phrase, a
    # comma, and a tail that gestures. Subtitles and section taglines are
    # where it lives; Brian called them useless (2026-09-17).
    "appositive-tail": {
        "title": re.compile(
            r"^\s*(?:\d+[.)]\s*)?[^,.:;]{3,70},\s*(?:and\s+(?:tonight|now|this|that|each|none|no)\b|then\s+\w|now\s+\w"
            r"|(?:sent|pointed|turned|seen|read|applied|named|built|run|taken)\s+\w)", re.I),
        "sentence": re.compile(
            r"^[^,.:;]{3,70},\s*(?:then\s+your\b|now\s+\w+able\b|(?:sent|pointed|turned)\s+(?:back|at)\b)", re.I),
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
    # The stance noun ends the heading or opens a clause ("The Real Problem", "The
    # actual question is scope"); "The actual cost of the project" names a subject (I050).
    r"^(the real|the actual)\s+(problem|question|issue|reason|cost|point|story|answer|"
    r"lesson|risk|danger|work|win|fix|test|challenge|trick|secret|lever|tell)"
    r"\s*(?:$|[:?!.,;]|\s+(?:is|was|isn't|wasn't|here|lies|remains)\b)",
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
    # Abstract subjects only: a tool, a course or a paper has a real place to sit (I050).
    r"^where\s+(this|that|it|we|you|each|the\s+(?:\w+\s+)?(?:stage|step|phase|work|argument|"
    r"claim|decision|method|idea|risk|value|cost)|(?:stage|step|phase|week|round|part|section)\s+\w+)"
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
# Each lookbehind holds its own period and has a fixed width; before 0.5.42 they
# sat after the period and tested the wrong characters, so none of them fired and
# "Dr. Smith" split into two sentences (I080). A number marker (no., vol., pp.,
# art., fig.) is an abbreviation only when a digit follows it, since "The answer
# was no." ends a sentence.
ABBREV = (r"(?<!\b[A-Z]\.)(?<!\bvs\.)(?<!\bcf\.)(?<!\bal\.)(?<!\beds\.)(?<!\bed\.)(?<!\bapprox\.)"
          r"(?<!\best\.)(?<!\bDr\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bMrs\.)(?<!\bSt\.)(?<!\betc\.)"
          r"(?<!\bi\.e\.)(?<!\be\.g\.)")
NUMBER_MARK = r"(?:(?<!\b[Nn]o\.)(?<!\b[Vv]ol\.)(?<!\bpp\.)(?<!\b[Aa]rt\.)(?<!\b[Ff]ig\.)|(?!\s+\d))"
SENT_SPLIT = re.compile(r"(?<=[.!?])" + ABBREV + NUMBER_MARK + r"\s+")
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

    def __init__(self, line, rule, match, message, col=None, severity="warning", rule_id=None, key=""):
        self.key = key  # an untruncated identity for a document-level finding's decision (I145)
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
    # a link's destination is where the link goes, not a citation in the line (I084)
    return bool(_BIB_LINE.match(ln)) or len(CITATION.findall(re.sub(r"\]\([^)\n]*\)", "]", ln))) >= 2


# function words, the personal pronouns among them: "He left. He came back." shares
# a pronoun, not a shape (I051)
_STOP = frozenset(("a an the of to in on at for and or but is are was were be it its this that these those "
                   "i me my we us our you your he him his she her they them their that's it's there").split())
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
    # a shared function word ("It rained. It stopped.") is not a shared shape (I051)
    if ta[0] == tb[0] and ta[0] not in _STOP:
        return True
    if ta[-1] == tb[-1] and ta[-1] not in _STOP:
        return True
    if _NEG.search(a) and _NEG.search(b):
        return True
    # the same skeleton: function words in the same slots, content words anywhere
    # ("The count was wrong. The ledger was right." is "the _ was _" twice)
    skel = lambda ts: [w if w in _STOP else "_" for w in ts]  # noqa: E731
    if len(ta) >= 3 and skel(ta) == skel(tb) and sum(w in _STOP for w in ta) >= 2:  # one shared pronoun is not a shape
        return True
    # a content word in the same slot of both ("Rain fell on the roof. Snow fell on the
    # car."); the same word in another slot is a repetition, not a parallel
    same_slot = any(x == y and x not in _STOP for x, y in zip(ta, tb))
    return abs(len(ta) - len(tb)) <= 1 and same_slot


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


_SETEXT_RULE = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")


def _headings(lines: list[str]) -> dict[int, str]:
    """1-indexed line -> heading text, for ATX and setext headings alike, with a
    leading number ("2.", "Part 3:") and emphasis stripped, so "## 2. **Where
    This Sits**" is read as its words (I079). The underline of a setext
    heading is marked with empty text: a heading line, but no second heading."""
    kinds = mdmask.line_kinds("\n".join(lines))
    out: dict[int, str] = {}
    for i, (ln, k) in enumerate(zip(lines, kinds), 1):
        if k != "heading":
            continue
        text = mdmask.heading_text(ln)
        if text is None:
            text = "" if _SETEXT_RULE.match(ln) else ln.strip()
        text = re.sub(r"^(?:(?:part|section|chapter|step)\s+)?\d+(?:\.\d+)*[.):]?\s+", "", text, flags=re.I)
        out[i] = text.strip("*_ ").strip()
    return out


def _suppressed(lines: list[str]) -> dict[int, set[str]]:
    """1-indexed line number -> the rules the file silences there ("*" for all).
    Read from the code-masked text, so a directive quoted in code silences
    nothing, and like voicelint's, a directive may name the rules it silences:
    ``<!-- structlint: ignore-line staccato -->`` (I082)."""
    out: dict[int, set[str]] = {}
    masked = mdmask.mask("\n".join(lines), ("code",)).split("\n")
    for i, ln in enumerate(masked, 1):
        for m in re.finditer(r"<!--\s*structlint:\s*ignore(-next-line|-line)\b(.*?)-->", ln):
            target = i + 1 if m.group(1) == "-next-line" else i
            out.setdefault(target, set()).update(re.findall(r"[A-Za-z][\w.-]*", m.group(2)) or {"*"})
    return out


def _strip_code(lines: list[str]) -> list[str]:
    """Blank fenced and inline code and HTML comments, keeping line numbers
    intact (mdmask). A comment, a suppression directive included, is not prose
    and was being counted as a sentence (I082)."""
    text = mdmask.mask("\n".join(lines), ("code", "comment"))
    text = re.sub(r"<!--(?:(?!\n[ \t]*\n).)*?-->", lambda m: mdmask.blank(m.group(0)), text, flags=re.S)
    return text.split("\n")


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
    # A subtitle is one short line standing alone under its heading (a blank line or
    # the end after it), not the first line of a body paragraph; a heading and its
    # subtitle are one unit, so a frame in both counts once (I079).
    titles: list[tuple[int, str]] = []
    for i, h in heads:
        unit = h
        if i < len(lines):
            nxt = lines[i].strip()
            alone = i + 1 >= len(lines) or not lines[i + 1].strip()
            if nxt and alone and len(nxt.split()) <= 14 and not nxt.isupper() and not LIST_ITEM.match(nxt) \
                    and not TABLE_ROW.match(nxt) and not HEADER_LINE.match(nxt) and not _SETEXT_RULE.match(nxt):
                unit = h + " / " + nxt
        titles.append((i, unit))
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
            key = "\n".join(f"{i}:{' '.join(u.split())}" for i, u in hits)
            out.append(Finding(hits[0][0], "frame",
                               f"{n}/{total} {kind}s: {quoted}",
                               f"the '{name}' frame recurs across {n} of {total} {kind}s; "
                               f"no one is wrong, the repetition is the tell",
                               severity="advisory", rule_id=f"structure.frame.{name}.{kind}", key=key))
    return out


def check_text(raw: str, thresholds: dict | None = None) -> list[Finding]:
    t = dict(DEFAULT_THRESHOLDS)
    t.update(thresholds or {})
    SHORT, STACCATO_RUN = int(t["short_chars"]), int(t["staccato_run"])
    # the same one-for-one fold voicelint reads, so a curly quote or a no-break space
    # does not hide a quoted span or a "here's" header from the checks below (I096)
    # newline only, as voicelint and pherkad number lines; splitlines() also broke on
    # U+2028, form feeds and lone CRs, and the line numbers disagreed (I083)
    lines = [ln[:-1] if ln.endswith("\r") else ln for ln in mdmask.fold(raw).split("\n")]
    heading = _headings(lines)
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
        if (not ln.strip() or BLOCKQUOTE.match(ln)
                or i in heading or FIELD_LINE.match(ln)
                or TABLE_ROW.match(ln) or BRACKET_PLACEHOLDER.match(ln)
                or _is_bibliographic(ln)):
            flush()
        else:
            if LIST_ITEM.match(ln):
                flush()  # each item is its own unit; a lead-in and its list are not one paragraph (I084)
            if not buf:
                start = i
            buf.append(_mask_spans(ln))
            continue
        if not ln.strip() or BLOCKQUOTE.match(ln):
            continue

        if heading.get(i):
            h = heading[i]
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

        # two-beat: a clipped balanced parallel pair of short sentences. A paragraph of
        # exactly two, or the closing pair of a longer one, which is where the tell sits
        # (I085). Every pair anywhere took the saga from 12 two-beats to 131, most of them
        # deliberate pairs in its plain narrative register. The pair must stand alone: a
        # pair inside a longer run of short sentences is the staccato check's.
        short = [len(s_) <= SHORT for s_ in sents]
        for k in range(max(0, len(sents) - 2), len(sents) - 1):
            a, b = sents[k], sents[k + 1]
            if not (short[k] and short[k + 1]) or (k > 0 and short[k - 1]) or (k + 2 < len(sents) and short[k + 2]):
                continue
            if (abs(len(a) - len(b)) <= int(t["two_beat_diff"]) and a[:1].isupper()
                    and b[:1].isupper() and _parallel(a, b)):
                found.append(Finding(i, "two-beat", (a + " " + b).strip()[:80],
                                     "clipped balanced parallel; the symmetry is the tell"))
                break

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
        if heading.get(i):
            heads.append((i, heading[i]))
    if len(heads) >= int(t["interrogative_min"]):
        q = [(i, h) for i, h in heads
             if INTERROGATIVE_HEAD.match(h) and not h.rstrip().endswith("?")]
        pct = 100.0 * len(q) / len(heads)
        if pct > float(t["interrogative_pct"]):
            # Document-scoped: the match lists every heading in the rate, question
            # ones and not, so a decision on this finding is invalidated by any
            # heading change that moves the rate, not only by the first one.
            listed = "; ".join(("? " if INTERROGATIVE_HEAD.match(h) and not h.rstrip().endswith("?") else "") + h[:60]
                               for _, h in heads)
            found.append(Finding(q[0][0], "interrogative-headers",
                                 f"{len(q)}/{len(heads)} headings: {listed}",
                                 f"{pct:.0f}% of headings open with a question word; "
                                 f"name the sections instead",
                                 key="\n".join(f"{i}:{h}" for i, h in heads)))

    frames = check_frames(lines, heads, paras, t)

    # A suppressed line keeps its place in its paragraph, so the sentences around it read
    # as written; what it silences is a finding reported on it (I082).
    frames = [f for f in frames if not (skip.get(f.line) and ("*" in skip[f.line] or f.rule in skip[f.line]))]
    found = [f for f in found if not (skip.get(f.line) and ("*" in skip[f.line] or f.rule in skip[f.line]))]
    words = len(re.findall(r"\b\w+\b", "\n".join(lines)))
    cap = float(t["density_per_100"])
    if words >= 150 and len(found) >= 3:  # the floor references/full_mode.md states (I039)
        per100 = len(found) * 100.0 / words
        if per100 > cap:
            found.append(Finding(0, "density", f"{len(found)} hits / {words} words",
                                 f"{per100:.1f} per 100 words, over the {cap} cap"))
    # a frame is a document-level recurrence, reported at advisory level and never a
    # per-100-words construction (I049)
    return found + frames


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
            raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8", errors="replace").read()
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
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # never exit 1 (looks like findings) on a crash (I086)
        sys.stderr.write(f"structlint: unexpected error: {exc}\n")
        sys.exit(2)
