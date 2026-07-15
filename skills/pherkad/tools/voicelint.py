#!/usr/bin/env python3
"""voicelint - flag writing that reads as AI-generated.

The mechanical layer of Pherkad. A small, dependency-free linter that scans
prose (Markdown, plain text, or HTML) for the stylistic tells that make writing
sound machine-generated: canned phrases, engagement-bait openers, filler
intensifiers, dash overuse, over-used crutch words, and low-trust
source domains. The rules live in an external JSON config (voice_config.json)
so any person or team can tune them; the shipped defaults were built from
tells observed across many AI-assisted documents.

What this layer cannot see (antithesis constructions, triplet noun piling,
tone, whether prose sounds like *you*) is the job of the Pherkad skill's
judgment pass. See references/ai_tells.md.

Usage:
    voicelint.py FILE [FILE ...]
    voicelint.py -                 # read from stdin (treated as text)
    voicelint.py --html -          # treat stdin as HTML
    voicelint.py --config my.json FILE
    voicelint.py --json FILE       # machine-readable output
    voicelint.py --strict FILE     # warnings fail too (non-zero exit)

Exit status: 0 if clean; 1 if any error-level finding (or any warning with
--strict); 2 on a usage, IO, or config problem. That makes it safe in CI, where
a crash must not look like "findings found".

Stdlib only. Tested on Python 3.8+.
"""
from __future__ import annotations
import argparse
import bisect
import html
import json
import os
import re
import sys
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))

# Built-in rules, used only when no voice_config.json is found (kept in sync
# with that file). voice_config.json is the source of truth for a project.
#
# Every default here was built from tells observed across many AI-assisted
# documents, not one writer's taste. If a rule contradicts your real style
# (you use dashes deliberately, "robust" is your field's vocabulary), relax it
# in your own config; see examples/relaxed.json, and the Pherkad profile
# builder for generating a personal config from your voice profile.
FALLBACK_CONFIG = {
    "no_dashes": True,
    "dash_density_cap": 1.0,
    "load_bearing_literal_only": True,
    "banned_phrases": [
        "it's worth noting that", "it is worth noting that",
        "make no mistake", "at the end of the day", "the bottom line is",
        "a testament to", "game-changer", "paradigm shift",
        "unlock the potential", "double-edged sword", "moved the needle",
        "closed the loop", "the mirror image of", "rhymes with",
        "the flip side of", "in the realm of", "navigating the complexities",
        "in the rapidly evolving landscape", "in a world where",
        "picture this:", "as we navigate", "today, more than ever",
        "in conclusion,", "to summarize,",
        "writes itself", "needs no embellishment", "that's the news",
        "watch the move", "note the framing", "read this under",
        "is the move",
    ],
    "engagement_bait": [
        "nobody's talking about", "everybody's talking about",
        "no one is talking about", "the conversation nobody's having",
        "what I keep coming back to", "the thing I keep coming back to",
        "where I keep landing", "here's the thing", "here's what's wild",
        "here's the real question", "here's what they don't tell you",
        "let that sink in", "what most people miss", "few people realise",
        "few people realize", "the uncomfortable truth",
        "the inconvenient truth", "let's be honest", "i'll be blunt",
        "let me tell you why", "and here's why that matters", "plot twist:",
    ],
    "filler_words": [
        "significant", "crucial", "essential", "robust", "utilize",
        "genuinely", "honestly", "straightforward", "seamless", "seamlessly",
        "leverage", "delve", "delves", "delving", "tapestry", "showcases",
    ],
    "watch_words": {"live": 2, "quietly": 2},
    "flag_loaded_quietly": True,
    "aggregator_domains": [
        "msn.com", "news.yahoo.com", "timesofindia", "lawyermonthly.com",
        "techtimes.com", "933thedrive.com",
    ],
}

# Words that can follow "quietly" without it being a loaded adverb+verb tell.
_QUIETLY_STOP = r"(?:in|on|at|and|but|the|a|an|to|as|with|for|by|of|from|into|over|under|behind|before|after)"


@dataclass
class Finding:
    line: int
    col: int
    severity: str  # "error" | "warning"
    rule: str
    match: str
    message: str


def _fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    sys.stderr.write(f"voicelint: {msg}\n")
    sys.exit(2)


def _validate(cfg: dict) -> None:
    """Reject a structurally invalid rule set with a clear message (exit 2)."""
    if not isinstance(cfg, dict):
        _fail("config must be a JSON object")
    for key in ("banned_phrases", "engagement_bait", "filler_words", "aggregator_domains"):
        if key in cfg:
            v = cfg[key]
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                _fail(f"config field '{key}' must be a list of strings")
    if "watch_words" in cfg:
        ww = cfg["watch_words"]
        if not isinstance(ww, dict) or not all(
            isinstance(k, str) and isinstance(n, int) and not isinstance(n, bool)
            for k, n in ww.items()
        ):
            _fail("config field 'watch_words' must be an object of word -> integer")
    if "dash_density_cap" in cfg:
        cap = cfg["dash_density_cap"]
        if not isinstance(cap, (int, float)) or isinstance(cap, bool) or cap < 0:
            _fail("config field 'dash_density_cap' must be a non-negative number")


def load_config(path: str | None) -> dict:
    """Load the JSON rule set. Look next to the script, then in the CWD.

    Falls back to the built-in defaults (with a stderr note) if none is found,
    so a copied-away script still runs, just predictably.
    """
    if path:
        chosen = path
    else:
        here = os.path.join(HERE, "voice_config.json")
        cwd = os.path.join(os.getcwd(), "voice_config.json")
        chosen = here if os.path.exists(here) else (cwd if os.path.exists(cwd) else None)
    if not chosen:
        sys.stderr.write("voicelint: no voice_config.json found; using built-in defaults\n")
        return dict(FALLBACK_CONFIG)
    try:
        with open(chosen, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"cannot read config {chosen}: {exc}")
    _validate(cfg)
    merged = dict(FALLBACK_CONFIG)
    merged.update(cfg)
    return merged


def strip_html(text: str) -> str:
    """Reduce HTML to visible text, preserving line breaks so line numbers stay
    correct (tags become same-height whitespace). Entities are decoded, which
    can shift columns slightly within a line but never changes the line."""
    def blank(m):  # keep newlines, blank everything else in the match
        return re.sub(r"[^\n]", " ", m.group(0))
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", blank, text)
    text = re.sub(r"(?s)<[^>]+>", blank, text)
    return html.unescape(text)


def normalize_quotes(text: str) -> str:
    """Fold typographic quotes to ASCII so phrase rules match AI/Word output.
    One-to-one, so character offsets are preserved."""
    return text.translate({0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"'})


def _linecol_fn(text: str):
    """Return a function mapping a character offset to a 1-based (line, col)."""
    starts = [0] + [m.end() for m in re.finditer(r"\n", text)]

    def fn(idx: int):
        line = bisect.bisect_right(starts, idx)
        return line, idx - starts[line - 1] + 1

    return fn


def _iter(pattern: str, text: str, flags=re.IGNORECASE):
    return re.finditer(pattern, text, flags)


def check(text: str, cfg: dict) -> list[Finding]:
    """Run every enabled rule over ``text`` and return findings in order."""
    text = normalize_quotes(text)
    at = _linecol_fn(text)
    out: list[Finding] = []

    def add(m, severity, rule, message):
        line, col = at(m.start())
        out.append(Finding(line, col, severity, rule, m.group(0).strip(), message))

    dash_hits = list(_iter(r"[—–―−]", text, flags=0))  # em/en/horiz-bar/minus
    if cfg.get("no_dashes", True):
        for m in dash_hits:
            add(m, "error", "dash", "em/en dash; use a comma, colon, or full stop")
    else:
        cap = float(cfg.get("dash_density_cap", 0) or 0)
        if cap > 0 and dash_hits:
            words = len(re.findall(r"\w+", text))
            allowed = int(cap * words / 100)
            if len(dash_hits) > allowed:
                add(dash_hits[allowed], "warning", "dash-density",
                    f"{len(dash_hits)} dashes in {words} words (cap {cap} per 100); "
                    "heavy dash use is an AI tell")

    if cfg.get("load_bearing_literal_only", True):
        for m in _iter(r"load[-\s]?bearing(?!\s+walls?\b)", text):
            add(m, "error", "load-bearing", "figurative 'load-bearing'; earn the weight instead")

    for phrase in cfg.get("banned_phrases", []):
        for m in _iter(re.escape(phrase), text):
            add(m, "error", "banned-phrase", f"canned phrase: '{phrase}'")

    for phrase in cfg.get("engagement_bait", []):
        for m in _iter(re.escape(phrase), text):
            add(m, "error", "engagement-bait", f"manufactured-stance opener: '{phrase}'")

    if cfg.get("flag_loaded_quietly", True):
        for m in _iter(rf"\bquietly\s+(?!{_QUIETLY_STOP}\b)[a-z]+", text):
            add(m, "warning", "loaded-adverb", "loaded 'quietly + verb'; state what happened")

    for word in cfg.get("filler_words", []):
        for m in _iter(rf"\b{re.escape(word)}\b", text):
            add(m, "warning", "filler", f"filler/intensifier: '{word}'")

    for word, limit in cfg.get("watch_words", {}).items():
        hits = list(_iter(rf"\b{re.escape(word)}\b", text))
        if len(hits) > int(limit):
            add(hits[int(limit)], "warning", "overuse",
                f"'{word}' used {len(hits)} times (soft cap {limit}); vary it")

    for domain in cfg.get("aggregator_domains", []):
        # match the domain as a host label, not an arbitrary substring
        pat = rf"https?://[^\s)\"']*(?<![A-Za-z0-9-]){re.escape(domain)}(?![A-Za-z0-9-])[^\s)\"']*"
        for m in _iter(pat, text):
            add(m, "error", "source", f"low-trust/aggregator source: {domain}")

    out.sort(key=lambda f: (f.line, f.col))
    return out


def read_source(path: str, as_html: bool) -> str:
    if path == "-":
        data = sys.stdin.read()
    else:
        with open(path, encoding="utf-8", errors="replace") as fh:
            data = fh.read()
    if as_html or (path != "-" and path.lower().endswith((".html", ".htm"))):
        data = strip_html(data)
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Flag AI-generated writing tells.")
    ap.add_argument("files", nargs="+", help="files to lint, or - for stdin")
    ap.add_argument("--config", help="path to a JSON rule set")
    ap.add_argument("--html", action="store_true", help="treat input as HTML (also auto-detected by extension)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="warnings fail too")
    ap.add_argument("--quiet", action="store_true", help="only print the summary")
    args = ap.parse_args(argv)

    cfg = load_config(args.config or None)

    seen = set()
    files = [f for f in args.files if not (f in seen or seen.add(f))]  # dedupe, keep order

    results = []  # list of (path, findings)
    errors = warnings = 0
    io_failed = False
    for path in files:
        try:
            findings = check(read_source(path, args.html), cfg)
        except OSError as exc:
            sys.stderr.write(f"voicelint: {exc}\n")
            io_failed = True
            continue
        results.append((path, findings))
        errors += sum(f.severity == "error" for f in findings)
        warnings += sum(f.severity == "warning" for f in findings)

    if args.json:
        print(json.dumps(
            {p: [vars(f) for f in fs] for p, fs in results},
            indent=2, ensure_ascii=False))
    else:
        if not args.quiet:
            for path, findings in results:
                for f in findings:
                    print(f"{path}:{f.line}:{f.col} [{f.severity}] {f.rule}: "
                          f"{f.message}  ->  {f.match!r}")
        print(f"voicelint: {errors} error(s), {warnings} warning(s) "
              f"across {len(results)} file(s).")

    if io_failed:
        return 2
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # never exit 1 (looks like findings) on a crash
        sys.stderr.write(f"voicelint: unexpected error: {exc}\n")
        sys.exit(2)
