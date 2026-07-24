#!/usr/bin/env python3
"""voicelint: flag configured mechanical writing patterns.

The mechanical layer of Pherkad. A small, dependency-free linter that scans
prose (Markdown, plain text, or HTML) for the stylistic patterns configured in
its rule set: canned phrases, engagement-bait openers, filler intensifiers,
overused soft phrasings, dash overuse, over-used crutch words, and low-trust
source domains. The rules live in an external JSON config (voice_config.json)
so any person or team can tune them; the shipped defaults were built from tells
observed across many AI-assisted documents. No hit proves how a passage was
written; a hit means the configured pattern is present.

What this layer cannot see (antithesis constructions, triplet noun piling,
tone, direct-quote and technical-context judgment, whether prose sounds like
*you*) is the job of the Pherkad skill's judgment pass. The linter masks code
spans before matching, but it does not adjudicate quotations or domain context;
that stays with the model. See references/ai_tells.md.

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

Stdlib only. Runs on Python 3.8+ (exercised in CI across 3.8 through 3.12).
"""
from __future__ import annotations
import argparse
import bisect
import html
import json
import copy
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))

# Built-in rules, used only when no voice_config.json is found (kept in sync
# with that file). voice_config.json is the source of truth for a project.
#
# These defaults are the maintainer's house rules. Each was added after
# recurring across many AI-assisted documents, but the set still reflects one
# writer's conclusions. If a rule contradicts your real style, relax it in
# your own config (see examples/relaxed.json, or generate one from your voice
# profile) and record the override in your voice profile.
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
        "writes itself", "needs no embellishment",
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
    # Warnings, not errors: phrasings that are hard to ban outright but recur
    # far too often in AI-assisted text. [word] matches one token; [verb]
    # matches a gerund. A soft hit that overlaps a stronger banned phrase is
    # dropped as redundant (see check()).
    "soft_phrases": [
        "it's worth [verb]", "it is worth [verb]",
        "i want to be plain", "i want to be clear", "i want to be honest",
        "i want to be upfront", "i want to be direct", "i want to be transparent",
        "gut-check", "gut check",
        "where your [word] lives",
        "names a way",
        "the [word] that never bends",
    ],
    "filler_words": [
        "significant", "crucial", "essential", "robust", "utilize",
        "genuinely", "honestly", "straightforward", "seamless", "seamlessly",
        "leverage", "delve", "delves", "delving", "tapestry", "showcases",
    ],
    "watch_words": {"quietly": 2},
    # Off by default: clause-final position alone cannot tell an insinuating
    # "quietly" from a plain manner adverb ("shut the door quietly"). Kept as an
    # opt-in house rule; overuse is still caught by the "quietly" watch word,
    # and the pre-modifier case lives in the judgment layer (references/ai_tells.md).
    "flag_loaded_quietly": False,
    # Source-quality policy, not a voice tell, so it is not a shipped default.
    # A team that wants it keeps a config like examples/news-brief.json.
    "aggregator_domains": [],
}

# "load-bearing" is handled in two tiers. A regex reading only the next word
# cannot reliably tell the structural term from the metaphor: "load-bearing
# frame of the argument" is figurative though "frame" is physical, and
# "load-bearing case" can be a literal enclosure. So the linter exempts a clear
# physical member and, for anything else, emits a soft context warning that
# asks for a look. Whether an ambiguous use is really figurative is left to the
# judgment layer, which reads the sentence.
_LOAD_BEARING_PHYSICAL = {
    "wall", "walls", "beam", "beams", "column", "columns", "joist", "joists",
    "truss", "trusses", "slab", "slabs", "stud", "studs", "lintel", "lintels",
    "girder", "girders", "rafter", "rafters", "member", "members", "frame",
    "frames", "assembly", "assemblies", "footing", "footings", "pier", "piers",
}

# Config fields whose value is a list of strings, and which support
# add_<field> / remove_<field> override keys in a user config.
_LIST_FIELDS = (
    "banned_phrases", "engagement_bait", "soft_phrases",
    "filler_words", "aggregator_domains",
)

# Boolean fields, type-checked so a stray "false" string (which is truthy in
# Python) cannot silently enable or disable a rule.
_BOOL_FIELDS = ("no_dashes", "load_bearing_literal_only", "flag_loaded_quietly")

# Every recognized top-level key. An unknown non-comment key (a typo like
# "no_dash") is rejected rather than silently ignored. Keys beginning with "_"
# are treated as comments and always allowed.
_KNOWN_KEYS = frozenset(
    _LIST_FIELDS
    + tuple("add_" + f for f in _LIST_FIELDS)
    + tuple("remove_" + f for f in _LIST_FIELDS)
    + _BOOL_FIELDS
    + ("watch_words", "dash_density_cap")
)


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
    list_keys = list(_LIST_FIELDS)
    for field in _LIST_FIELDS:
        list_keys += ["add_" + field, "remove_" + field]
    for key in list_keys:
        if key in cfg:
            v = cfg[key]
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                _fail(f"config field '{key}' must be a list of strings")
            if not all(x.strip() for x in v):
                _fail(f"config field '{key}' must not contain an empty string "
                      "(an empty pattern would match everywhere)")
    if "watch_words" in cfg:
        ww = cfg["watch_words"]
        if not isinstance(ww, dict) or not all(
            isinstance(k, str) and isinstance(n, int) and not isinstance(n, bool)
            for k, n in ww.items()
        ):
            _fail("config field 'watch_words' must be an object of word -> integer")
        if not all(k.strip() for k in ww):
            _fail("config field 'watch_words' must not have an empty word key")
        if not all(n >= 0 for n in ww.values()):
            _fail("config field 'watch_words' caps must be non-negative integers")
    if "dash_density_cap" in cfg:
        cap = cfg["dash_density_cap"]
        if not isinstance(cap, (int, float)) or isinstance(cap, bool) or cap < 0:
            _fail("config field 'dash_density_cap' must be a non-negative number")
    for key in _BOOL_FIELDS:
        if key in cfg and not isinstance(cfg[key], bool):
            _fail(f"config field '{key}' must be true or false")
    for key in cfg:
        if key.startswith("_"):
            continue  # comment/metadata keys
        if key not in _KNOWN_KEYS:
            _fail(f"unknown config key '{key}'; check for a typo "
                  "(comment keys must start with '_')")


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge ``override`` onto ``base`` recursively.

    Nested objects (for example ``watch_words``) merge key by key, so a config
    that sets one watch word does not wipe the other defaults. A non-dict value
    replaces the default outright. List fields replace wholesale here; use the
    ``add_<field>`` / ``remove_<field>`` keys (applied afterward) to amend a
    default list instead of replacing it.
    """
    out = copy.deepcopy(base)  # never hand back a reference into FALLBACK_CONFIG
    for key, val in override.items():
        if isinstance(out.get(key), dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _apply_list_ops(cfg: dict) -> dict:
    """Apply add_<field> / remove_<field> amendments, then drop the helper keys.

    Adds are appended (skipping duplicates); removes are filtered out. This lets
    a config extend or trim a shipped list without restating the whole thing.
    """
    for field in _LIST_FIELDS:
        adds = cfg.pop("add_" + field, [])
        removes = cfg.pop("remove_" + field, [])
        if not adds and not removes:
            continue
        merged = list(cfg.get(field, []))
        for item in adds:
            if item not in merged:
                merged.append(item)
        drop = set(removes)
        cfg[field] = [x for x in merged if x not in drop]
    return cfg


def load_config(path: str | None) -> dict:
    """Load the JSON rule set. Look next to the script, then in the CWD.

    Falls back to the built-in defaults (with a stderr note) if none is found,
    so a copied-away script still runs, just predictably. A user config is
    deep-merged onto the defaults: unlisted top-level fields and unlisted nested
    keys inherit, listed objects merge key by key, and listed arrays replace
    (amend with add_/remove_ keys).
    """
    if path:
        chosen = path
    else:
        here = os.path.join(HERE, "voice_config.json")
        cwd = os.path.join(os.getcwd(), "voice_config.json")
        chosen = here if os.path.exists(here) else (cwd if os.path.exists(cwd) else None)
    if not chosen:
        sys.stderr.write("voicelint: no voice_config.json found; using built-in defaults\n")
        return copy.deepcopy(FALLBACK_CONFIG)
    try:
        with open(chosen, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"cannot read config {chosen}: {exc}")
    _validate(cfg)
    merged = _deep_merge(FALLBACK_CONFIG, cfg)
    return _apply_list_ops(merged)


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


def mask_code(text: str) -> str:
    """Blank Markdown code so a pattern quoted as code is not flagged.

    Fenced blocks (```...```) and inline spans (`...`) become same-height
    whitespace: newlines stay, every other character becomes a space, so line
    and column offsets are unchanged. This is why a doc can name a banned phrase
    inside backticks without tripping the linter. It does not touch prose in
    ordinary quotation marks; adjudicating a direct quote stays with the
    judgment layer (see references/ai_tells.md)."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    text = re.sub(r"(?s)```.*?```", blank, text)
    text = re.sub(r"`[^`\n]*`", blank, text)
    return text


def _is_word_char(ch: str) -> bool:
    """True if ``ch`` is part of a word: an alphanumeric, or a combining mark
    (Unicode category M) that attaches to the preceding letter. The mark test
    makes the guard safe for decomposed text, where an accent is a separate
    character after its base letter (NFD 'e' + U+0301)."""
    return ch.isalnum() or unicodedata.category(ch).startswith("M")


def _iter_phrase(pattern: str, phrase: str, text: str):
    """Yield case-insensitive matches of ``pattern`` in ``text``, rejecting a
    match whose word-forming edge sits against another word character.

    The guard is decided from ``phrase`` (the readable source): if it starts or
    ends with an alphanumeric, that side must not touch a word character, so
    'is the move' does not match inside 'movement' while 'picture this:'
    (punctuation edge) still matches. The neighbor test counts alphanumerics
    and combining marks, so an accented letter, precomposed or decomposed,
    counts as a word character."""
    guard_left = phrase[:1].isalnum()
    guard_right = phrase[-1:].isalnum()
    for m in re.finditer(pattern, text, re.IGNORECASE):
        s, e = m.start(), m.end()
        if guard_left and s > 0 and _is_word_char(text[s - 1]):
            continue
        if guard_right and e < len(text) and _is_word_char(text[e]):
            continue
        yield m


def _linecol_fn(text: str):
    """Return a function mapping a character offset to a 1-based (line, col)."""
    starts = [0] + [m.end() for m in re.finditer(r"\n", text)]

    def fn(idx: int):
        line = bisect.bisect_right(starts, idx)
        return line, idx - starts[line - 1] + 1

    return fn


def _iter(pattern: str, text: str, flags=re.IGNORECASE):
    return re.finditer(pattern, text, flags)


def _soft_to_regex(phrase: str) -> str:
    """Turn a readable soft phrase into a regex. [word] -> one token,
    [verb] -> a gerund (\\w+ing). Everything else is matched literally."""
    parts = re.split(r"(\[word\]|\[verb\])", phrase)
    out = []
    for p in parts:
        if p == "[word]":
            out.append(r"\w+")
        elif p == "[verb]":
            out.append(r"\w+ing")
        elif p:
            out.append(re.escape(p))
    return "".join(out)


def _suppression_map(text: str) -> dict:
    """Map a 1-based line number to the rules suppressed there by an inline
    directive. A directive is recognized only inside an HTML comment:
    ``<!-- voicelint: ignore-line -->`` suppresses the line it sits on;
    ``<!-- voicelint: ignore-next-line -->`` suppresses the following line.
    Rule names after the verb limit it to those rules
    (``<!-- voicelint: ignore-line filler -->``); with none, the whole line is
    suppressed (``*``).

    The comment requirement, plus running this over the code-masked text, is
    deliberate: a directive written in prose or backticked as code must not be
    able to silence a real finding."""
    supp: dict = {}
    for i, line in enumerate(text.split("\n"), start=1):
        for m in re.finditer(
            r"<!--\s*voicelint:\s*ignore(-next-line|-line)?\b(.*?)-->",
            line, re.IGNORECASE):
            target = i + 1 if m.group(1) == "-next-line" else i
            names = set(re.findall(r"[A-Za-z][\w-]*", m.group(2))) or {"*"}
            supp.setdefault(target, set()).update(names)
    return supp


def check(text: str, cfg: dict) -> list[Finding]:
    """Run every enabled rule over ``text`` and return findings in order.

    Findings silenced by an inline ``voicelint: ignore`` directive are removed;
    use :func:`check_counting` to also learn how many were suppressed."""
    return check_counting(text, cfg)[0]


def check_counting(text: str, cfg: dict):
    """Like :func:`check`, but return ``(findings, suppressed_count)``."""
    text = normalize_quotes(text)
    at = _linecol_fn(text)
    # Match against a copy with code spans blanked; offsets are preserved, so
    # findings still point at the real line and column. Suppression directives
    # are read from the masked text, so a backticked directive cannot silence a
    # real finding.
    text = mask_code(text)
    suppress = _suppression_map(text)
    out: list[Finding] = []

    def add(m, severity, rule, message):
        line, col = at(m.start())
        out.append(Finding(line, col, severity, rule, m.group(0).strip(), message))

    dash_hits = list(_iter(r"[—–―]", text, flags=0))  # em / en / horizontal bar
    if cfg.get("no_dashes", True):
        for m in dash_hits:
            add(m, "error", "dash", "em/en dash; use a comma, colon, or full stop")
    else:
        cap = float(cfg.get("dash_density_cap", 0) or 0)
        words = len(re.findall(r"\w+", text))
        # A rate per 100 words is meaningless on a short passage. Match the
        # judgment layer's floor (SKILL.md Step 4): at least 150 words and at
        # least 3 dash hits before a density warning fires.
        if cap > 0 and words >= 150 and len(dash_hits) >= 3:
            allowed = int(cap * words / 100)
            if len(dash_hits) > allowed:
                add(dash_hits[allowed], "warning", "dash-density",
                    f"{len(dash_hits)} dashes in {words} words (cap {cap} per 100); "
                    "heavy dash use is an AI tell")

    if cfg.get("load_bearing_literal_only", True):
        for m in _iter(r"load[-\s]?bearing\b", text):
            nxt = re.match(r"\s+([^\W\d_]+)", text[m.end():])  # next alphabetic word
            word = nxt.group(1).lower() if nxt else ""
            if word in _LOAD_BEARING_PHYSICAL:
                continue  # literal structural use
            add(m, "warning", "load-bearing-context",
                "'load-bearing' with a non-structural object; confirm this is literal, not metaphor")

    for phrase in cfg.get("banned_phrases", []):
        for m in _iter_phrase(re.escape(phrase), phrase, text):
            add(m, "error", "banned-phrase", f"canned phrase: '{phrase}'")

    for phrase in cfg.get("engagement_bait", []):
        for m in _iter_phrase(re.escape(phrase), phrase, text):
            add(m, "error", "engagement-bait", f"manufactured-stance opener: '{phrase}'")

    for phrase in cfg.get("soft_phrases", []):
        for m in _iter_phrase(_soft_to_regex(phrase), phrase, text):
            add(m, "warning", "soft-cliche", f"overused AI phrasing: '{phrase}'")

    if cfg.get("flag_loaded_quietly", True):
        for m in _iter(r"\bquietly\b(?=\s*(?:[.,;:!?)\]]|$))", text, flags=re.IGNORECASE | re.MULTILINE):
            add(m, "warning", "loaded-adverb", "trailing 'quietly'; the insinuating position. Put it before the verb or cut it")

    for word in cfg.get("filler_words", []):
        for m in _iter(rf"\b{re.escape(word)}\b", text):
            add(m, "warning", "filler", f"filler/intensifier: '{word}'")

    for word, limit in cfg.get("watch_words", {}).items():
        hits = list(_iter(rf"\b{re.escape(word)}\b", text))
        if len(hits) > int(limit):
            add(hits[int(limit)], "warning", "overuse",
                f"'{word}' used {len(hits)} times (soft cap {limit}); vary it")

    domains = [d.lower().strip(".") for d in cfg.get("aggregator_domains", []) if d.strip(".")]
    if domains:
        # Only scheme-bearing URLs are scanned; a bare "msn.com/x" with no
        # scheme is left to the judgment layer, since a loose host regex would
        # reintroduce path and prose false positives.
        for m in _iter(r"https?://[^\s)\"'<>]+", text):
            host = (urlsplit(m.group(0)).hostname or "").lower().rstrip(".")
            if not host:
                continue
            labels = host.split(".")
            for domain in domains:
                # A dotted domain matches as a host suffix (msn.com in
                # www.msn.com); a bare label matches a whole label
                # (timesofindia in timesofindia.indiatimes.com). Neither
                # matches the same string sitting in the path or query.
                if "." in domain:
                    hit = host == domain or host.endswith("." + domain)
                else:
                    hit = domain in labels
                if hit:
                    add(m, "error", "source", f"low-trust/aggregator source: {domain}")
                    break

    out.sort(key=lambda f: (f.line, f.col))
    # A soft-cliche that lands exactly where a stronger error already fired
    # (e.g. "it's worth noting that") is redundant; keep the error only.
    err_starts = {(f.line, f.col) for f in out if f.severity == "error"}
    out = [f for f in out if not (f.rule == "soft-cliche" and (f.line, f.col) in err_starts)]

    if suppress:
        kept, dropped = [], 0
        for f in out:
            names = suppress.get(f.line)
            if names and ("*" in names or f.rule in names):
                dropped += 1
                continue
            kept.append(f)
        return kept, dropped
    return out, 0


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
    ap = argparse.ArgumentParser(description="Flag configured mechanical writing patterns.")
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
    errors = warnings = suppressed = 0
    io_failed = False
    for path in files:
        try:
            findings, dropped = check_counting(read_source(path, args.html), cfg)
        except OSError as exc:
            sys.stderr.write(f"voicelint: {exc}\n")
            io_failed = True
            continue
        results.append((path, findings))
        errors += sum(f.severity == "error" for f in findings)
        warnings += sum(f.severity == "warning" for f in findings)
        suppressed += dropped

    if args.json:
        print(json.dumps(
            {"suppressed": suppressed,
             "files": {p: [vars(f) for f in fs] for p, fs in results}},
            indent=2, ensure_ascii=False))
    else:
        if not args.quiet:
            for path, findings in results:
                for f in findings:
                    print(f"{path}:{f.line}:{f.col} [{f.severity}] {f.rule}: "
                          f"{f.message}  ->  {f.match!r}")
        tail = f", {suppressed} suppressed" if suppressed else ""
        print(f"voicelint: {errors} error(s), {warnings} warning(s){tail} "
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
