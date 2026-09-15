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
    voicelint.py --print-config    # the effective rule set as JSON
    voicelint.py --list-rules      # every rule with its stable id

Rules: the shipped voice_config.json beside this script is the base; --config
(or ./voice_config.json in the working directory) is one overlay merged onto it.

Exit status: 0 if clean; 1 if any error-level finding (or any warning with
--strict); 2 on a usage, IO, or config problem. That makes it safe in CI, where
a crash must not look like "findings found".

Stdlib only. Runs on Python 3.8+ (exercised in CI across 3.8 through 3.12).
"""
from __future__ import annotations
import argparse
import bisect
import hashlib
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

# The shipped rule set lives beside this script as voice_config.json and is the
# only base. There is no second copy of the defaults in Python: an earlier
# fallback dictionary drifted from the JSON (13 soft phrases against 115) and,
# because user configs were merged onto it, any --config silently dropped most
# of the shipped rules. Now a missing base is a config error (exit 2), never a
# quietly smaller rule set.
DEFAULTS_PATH = os.path.join(HERE, "voice_config.json")

# "load-bearing" is handled in two tiers. A regex reading only the next word
# cannot reliably tell the structural term from the metaphor: "load-bearing
# frame of the argument" is figurative though "frame" is physical, and
# "load-bearing case" can be a literal enclosure. So the linter exempts a clear
# physical member and, for anything else, emits a soft context warning that
# asks for a look. Whether an ambiguous use is really figurative is left to the
# judgment layer, which reads the sentence. "frame" is deliberately not in the
# exempt set: it is the one physical noun that shows up in the figurative use.
_LOAD_BEARING_PHYSICAL = {
    "wall", "walls", "beam", "beams", "column", "columns", "joist", "joists",
    "truss", "trusses", "slab", "slabs", "stud", "studs", "lintel", "lintels",
    "girder", "girders", "rafter", "rafters", "member", "members",
    "assembly", "assemblies", "footing", "footings", "pier", "piers",
}

# Config fields whose value is a list of strings, and which support
# add_<field> / remove_<field> override keys in a user config.
_LIST_FIELDS = (
    "banned_phrases", "engagement_bait", "soft_phrases",
    "filler_words", "aggregator_domains",
)

# Boolean fields, type-checked so a stray "false" string (which is truthy in
# Python) cannot silently enable or disable a rule.
_BOOL_FIELDS = ("no_dashes", "load_bearing_literal_only", "flag_loaded_quietly",
                "no_honest_framing")

# Every recognized top-level key. An unknown non-comment key (a typo like
# "no_dash") is rejected rather than silently ignored. Keys beginning with "_"
# are treated as comments and always allowed.
# structlint's thresholds ride in the same file under "structure", with the same
# overlay semantics, so a downstream config tunes both tools in one place.
_STRUCTURE_KEYS = frozenset({"short_chars", "two_beat_diff", "staccato_run",
                             "density_per_100", "interrogative_pct", "interrogative_min"})

_KNOWN_KEYS = frozenset(
    _LIST_FIELDS
    + tuple("add_" + f for f in _LIST_FIELDS)
    + tuple("remove_" + f for f in _LIST_FIELDS)
    + _BOOL_FIELDS
    + ("watch_words", "dash_density_cap", "structure")
)


@dataclass
class Finding:
    line: int
    col: int
    severity: str  # "error" | "warning"
    rule: str      # the family: banned-phrase, soft-cliche, filler, dash, ...
    match: str
    message: str
    rule_id: str = ""  # the stable id of the one rule that fired: soft.is-the-point, dash, overuse.quietly


# STABLE RULE IDS (2026-09-15). A list entry is either a plain string (the pattern) or an
# object {"id", "pattern", "rationale", "since", "fires", "clean"}. A string gets its id
# derived from the pattern (soft.is-the-point; a regex gets soft.re-<8 hex>), so every rule
# has an id whether or not anyone wrote one, and the shipped lists stay strings where they
# always were. The id is what a finding reports, what a downstream overlay names in
# remove_<field> (it no longer has to paste a regex character for character), and what a
# later decision file or corpus scan keys on. "fires" and "clean" are example sentences the
# test suite runs, so a rule with examples is a tested rule.
_RULE_PREFIX = {
    "banned_phrases": "banned", "engagement_bait": "bait", "soft_phrases": "soft",
    "filler_words": "filler", "aggregator_domains": "source",
}
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
_ENTRY_KEYS = frozenset({"id", "pattern", "rationale", "since", "fires", "clean"})


def _slug(text: str, limit: int = 48) -> str:
    text = re.sub(r"\[(word|verb|det|adj)\]", r"\1", text.lower())
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:limit].rstrip("-") or "x"


def _derive_id(field: str, pattern: str) -> str:
    prefix = _RULE_PREFIX.get(field, field)
    if pattern.startswith("re:"):
        return f"{prefix}.re-{hashlib.sha1(pattern.encode('utf-8')).hexdigest()[:8]}"
    return f"{prefix}.{_slug(pattern)}"


def _norm_entry(field: str, item) -> dict:
    """A list item as an entry dict. Strings become {id, pattern}; objects keep their keys."""
    if isinstance(item, str):
        return {"id": _derive_id(field, item), "pattern": item}
    entry = dict(item)
    if not entry.get("id"):
        entry["id"] = _derive_id(field, entry["pattern"])
    return entry


def rule_entries(cfg: dict, field: str) -> list[dict]:
    """Every rule in ``field`` as an entry dict with a unique id.

    Two plain strings that slug to the same id (``gut-check`` and ``gut check``)
    keep the first id and give the second a short hash suffix, so derived ids
    are unique and stable for a given list."""
    out, seen = [], set()
    for item in cfg.get(field, []):
        entry = _norm_entry(field, item)
        if entry["id"] in seen:
            if isinstance(item, str):
                entry["id"] += "-" + hashlib.sha1(item.encode("utf-8")).hexdigest()[:4]
            else:
                _fail(f"config field '{field}' has two rules with id '{entry['id']}'")
        seen.add(entry["id"])
        out.append(entry)
    return out


def all_rules(cfg: dict) -> list[dict]:
    """Every rule the effective config would run, list rules and fixed rules alike,
    as {id, family, severity, pattern, rationale}. What ``--list-rules`` prints."""
    fam = {"banned_phrases": ("banned-phrase", "error"), "engagement_bait": ("engagement-bait", "error"),
           "soft_phrases": ("soft-cliche", "warning"), "filler_words": ("filler", "warning"),
           "aggregator_domains": ("source", "error")}
    rows = []
    for field, (family, sev) in fam.items():
        for e in rule_entries(cfg, field):
            rows.append({"id": e["id"], "family": family, "severity": sev,
                         "pattern": e["pattern"], "rationale": e.get("rationale", "")})
    if cfg.get("no_dashes", True):
        rows.append({"id": "dash", "family": "dash", "severity": "error", "pattern": "[—–―]",
                     "rationale": "em/en dash; use a comma, colon, or full stop"})
    elif float(cfg.get("dash_density_cap", 0) or 0) > 0:
        rows.append({"id": "dash-density", "family": "dash-density", "severity": "warning",
                     "pattern": f"> {cfg['dash_density_cap']} per 100 words", "rationale": ""})
    if cfg.get("load_bearing_literal_only", True):
        rows.append({"id": "load-bearing-context", "family": "load-bearing-context", "severity": "warning",
                     "pattern": "load-bearing + non-structural noun", "rationale": ""})
    if cfg.get("no_honest_framing", True):
        rows.append({"id": "honest-framing", "family": "honest-framing", "severity": "error",
                     "pattern": "[det] honest [adj] NOUN", "rationale": ""})
    if cfg.get("flag_loaded_quietly", True):
        rows.append({"id": "loaded-adverb", "family": "loaded-adverb", "severity": "warning",
                     "pattern": "clause-final quietly", "rationale": ""})
    for word, cap in cfg.get("watch_words", {}).items():
        rows.append({"id": "overuse." + _slug(word), "family": "overuse", "severity": "warning",
                     "pattern": f"{word} > {cap} per 600 words", "rationale": ""})
    return rows


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
            if not isinstance(v, list):
                _fail(f"config field '{key}' must be a list")
            for x in v:
                if isinstance(x, str):
                    if not x.strip():
                        _fail(f"config field '{key}' must not contain an empty string "
                              "(an empty pattern would match everywhere)")
                    continue
                if not isinstance(x, dict):
                    _fail(f"config field '{key}' entries must be strings or rule objects")
                unknown = set(x) - _ENTRY_KEYS
                if unknown:
                    _fail(f"config field '{key}' rule object has unknown key(s) {sorted(unknown)}")
                if key.startswith("remove_"):
                    if not (isinstance(x.get("id"), str) or isinstance(x.get("pattern"), str)):
                        _fail(f"config field '{key}' rule object needs an 'id' or a 'pattern'")
                elif not isinstance(x.get("pattern"), str) or not x["pattern"].strip():
                    _fail(f"config field '{key}' rule object needs a non-empty 'pattern'")
                if "id" in x and (not isinstance(x["id"], str) or not _ID_RE.match(x["id"])):
                    _fail(f"config field '{key}' rule id {x.get('id')!r} must match [a-z0-9][a-z0-9.-]*")
                for lk in ("fires", "clean"):
                    if lk in x and not (isinstance(x[lk], list) and all(isinstance(t, str) for t in x[lk])):
                        _fail(f"config field '{key}' rule '{x.get('id') or x.get('pattern')}' "
                              f"'{lk}' must be a list of strings")
                for sk in ("rationale", "since"):
                    if sk in x and not isinstance(x[sk], str):
                        _fail(f"config field '{key}' rule '{sk}' must be a string")
            if not key.startswith("remove_"):
                rule_entries({key: v}, key if key in _LIST_FIELDS else key[4:])  # duplicate-id check
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
    if "structure" in cfg:
        st = cfg["structure"]
        if not isinstance(st, dict):
            _fail("config field 'structure' must be an object of threshold -> number")
        for k, v in st.items():
            if k.startswith("_"):
                continue
            if k not in _STRUCTURE_KEYS:
                _fail(f"config field 'structure' has unknown threshold '{k}'; "
                      f"known: {', '.join(sorted(_STRUCTURE_KEYS))}")
            if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
                _fail(f"config field 'structure.{k}' must be a non-negative number")
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
    out = copy.deepcopy(base)  # the caller may mutate the result freely
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
        present = {(e["id"], e["pattern"]) for e in rule_entries({field: merged}, field)}
        ids = {i for i, _ in present}
        pats = {p for _, p in present}
        for item in adds:
            e = _norm_entry(field, item)
            if e["id"] in ids or e["pattern"] in pats:
                continue
            merged.append(item)
            ids.add(e["id"]); pats.add(e["pattern"])
        # A remove entry names a rule by id or by pattern; either form works for
        # either kind of entry, so an overlay can drop a shipped regex by its id.
        drop_ids, drop_pats = set(), set()
        for r in removes:
            if isinstance(r, str):
                drop_ids.add(r); drop_pats.add(r)
            else:
                if r.get("id"): drop_ids.add(r["id"])
                if r.get("pattern"): drop_pats.add(r["pattern"])
        kept = []
        for item, e in zip(merged, rule_entries({field: merged}, field)):
            if e["id"] in drop_ids or e["pattern"] in drop_pats:
                continue
            kept.append(item)
        cfg[field] = kept
    return cfg


def _read_json(path: str, what: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"cannot read {what} {path}: {exc}")
    _validate(cfg)
    return cfg


def load_config(path: str | None, base: str | None = None) -> dict:
    """Load the effective rule set: the shipped defaults, then one user overlay.

    The base is always ``voice_config.json`` beside this script. If it is
    missing the run stops with exit 2; a linter that quietly runs with fewer
    rules is worse than one that refuses to run. The overlay is ``--config``
    when given, otherwise ``./voice_config.json`` in the working directory when
    that is a different file from the base. The overlay is deep-merged onto the
    base: unlisted top-level fields and unlisted nested keys inherit, listed
    objects merge key by key, listed arrays replace, and add_/remove_ keys amend
    a shipped list without restating it. ``--print-config`` shows the result.

    ``base`` names another file to use as the base instead of the shipped one;
    the corpus tools use it to run an older release's rule set under the same
    overlay. It is not a CLI option: the linter itself always runs the shipped
    base, so a vendored copy cannot be pointed at a stale one by accident.
    """
    base_path = base or DEFAULTS_PATH
    if not os.path.exists(base_path):
        if base:
            _fail(f"base rule set not found at {base_path}")
        _fail(f"shipped rule set not found at {DEFAULTS_PATH}; "
              "voice_config.json must sit beside voicelint.py")
    base_cfg = _apply_list_ops(_read_json(base_path, "shipped rule set"))

    overlay = path
    if not overlay:
        cwd_cfg = os.path.join(os.getcwd(), "voice_config.json")
        if os.path.exists(cwd_cfg) and not os.path.samefile(cwd_cfg, DEFAULTS_PATH):
            overlay = cwd_cfg
    if not overlay or (os.path.exists(overlay) and os.path.samefile(overlay, base_path)):
        return base_cfg
    merged = _deep_merge(base_cfg, _read_json(overlay, "config"))
    return _apply_list_ops(merged)


def strip_html(text: str) -> str:
    """Reduce HTML to visible text, preserving line breaks so line numbers stay
    correct (tags become same-height whitespace). Entities are decoded, which
    can shift columns slightly within a line but never changes the line."""
    def blank(m):  # keep newlines, blank everything else in the match
        return re.sub(r"[^\n]", " ", m.group(0))
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", blank, text)
    # Every tag goes, except a voicelint directive: it is an HTML comment, and
    # stripping it here would make ignore-line and voicelint-allow dead in HTML.
    text = re.sub(r"(?s)<(?!!--\s*voicelint)[^>]+>", blank, text)
    return html.unescape(text)


def normalize_quotes(text: str) -> str:
    """Fold typographic quotes to ASCII so phrase rules match AI/Word output.
    One-to-one, so character offsets are preserved."""
    return text.translate({0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"'})


def mask_code(text: str) -> str:
    """Blank Markdown code so a pattern quoted as code is not flagged.

    Fenced blocks (three or more backticks or tildes, closed by a matching fence
    or by the end of the file) and inline spans (`...`) become same-height
    whitespace: newlines stay, every other character becomes a space, so line
    and column offsets are unchanged. This is why a doc can name a banned phrase
    inside backticks without tripping the linter. An unclosed fence masks to the
    end of the file, which is how Markdown renders it. It does not touch prose
    in ordinary quotation marks; adjudicating a direct quote stays with the
    judgment layer (see references/ai_tells.md)."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    text = re.sub(
        r"(?ms)^[ \t]{0,3}(?P<c>[`~])(?P=c){2,}[^\n]*\n.*?(?:^[ \t]{0,3}(?P=c){3,}[ \t]*$|\Z)",
        blank, text)
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


# A determiner slot. The honest-framing family was twelve literals all beginning
# "the", so "One Honest First Look" walked past it. Same failure the land rule
# and the comparative-worth rule each had: the ban covered the shapes that were
# in front of whoever wrote it.
_DET = r"(?:the|a|an|one|another|my|our|your|their|his|her|its|this|that|some)"

def _soft_to_regex(phrase: str) -> str:
    """Turn a readable soft phrase into a regex. [word] -> one token,
    [verb] -> a gerund (\\w+ing), [det] -> a determiner, [adj] -> an optional
    adjective and its space. Everything else is matched literally."""
    if phrase.startswith("re:"):
        # A raw regex, for the rare rule that needs a negative lookahead. The
        # honest-adjective ban needs one: it covers every noun except the term
        # of art, and a noun list cannot express "everything but broker".
        return phrase[3:]
    parts = re.split(r"(\[word\]|\[verb\]|\[det\]|\[adj\])", phrase)
    out = []
    for p in parts:
        if p == "[word]":
            out.append(r"\w+")
        elif p == "[verb]":
            # A gerund, not any word ending in -ing: "worth nothing" is not "worth [verb]".
            out.append(r"(?!(?:nothing|something|anything|everything|things?|during|morning|evening)\b)\w+ing")
        elif p == "[det]":
            out.append(_DET)
        elif p == "[adj]":
            out.append(r"(?:\w+ )?")
        elif p:
            out.append(re.escape(p))
    return "".join(out)


def _allow_phrases(text: str) -> set:
    """Phrases exempted for a whole file by a declared marker, with the reason in it:

        <!-- voicelint-allow: lean in (literal: leaning into a car window) -->

    THIS COMPLEMENTS ``voicelint: ignore-line`` RATHER THAN DUPLICATING IT, and the two
    answer different questions. The line directive says *not here*, which is right for a
    one-off and wrong for a phrase a document uses correctly throughout. This says *not
    this phrase, in this file, and here is why*, which survives edits that move lines and
    puts the reason in the diff instead of in tool config.

    Adopted upstream 2026-09-01 from a downstream project that had implemented it
    locally. Some bans cannot be decided by regex. A phrase banned as a figure of speech
    still has a literal sense: a person can lean into a car window, and two proper nouns
    can genuinely rhyme. Guessing is worse than not checking, so the exemption is
    declared and visible.

    Scope is the whole file, which is coarse on purpose. A file that uses a phrase
    literally in one place and figuratively in another should split the entry or rewrite
    the figurative one.
    """
    return {
        m.group(1).strip().lower()
        for m in re.finditer(r"<!--\s*voicelint-allow:\s*([^(\-][^(\n]*?)\s*(?:\(|-->)", text)
    }


def _phrase_within(needle: str, hay: str) -> bool:
    """True if ``needle`` occurs in ``hay`` as whole words."""
    return re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", hay) is not None


def _suppression_map(text: str) -> dict:
    """Map a 1-based line number to the rules suppressed there by an inline
    directive. A directive is recognized only inside an HTML comment:
    ``<!-- voicelint: ignore-line -->`` suppresses the line it sits on;
    ``<!-- voicelint: ignore-next-line -->`` suppresses the following line.
    Rule names after the verb limit it to those rules, by family
    (``<!-- voicelint: ignore-line filler -->``) or by rule id
    (``<!-- voicelint: ignore-line soft.is-the-point -->``); with none, the
    whole line is suppressed (``*``).

    The comment requirement, plus running this over the code-masked text, is
    deliberate: a directive written in prose or backticked as code must not be
    able to silence a real finding."""
    supp: dict = {}
    for i, line in enumerate(text.split("\n"), start=1):
        for m in re.finditer(
            r"<!--\s*voicelint:\s*ignore(-next-line|-line)?\b(.*?)-->",
            line, re.IGNORECASE):
            target = i + 1 if m.group(1) == "-next-line" else i
            names = set(re.findall(r"[A-Za-z][\w.-]*", m.group(2))) or {"*"}
            supp.setdefault(target, set()).update(names)
    return supp


_RULES_FILE_MARKER = re.compile(r"(?m)^[ \t]*<!--\s*voicelint:\s*rules-file\s*-->[ \t]*$")


def check(text: str, cfg: dict) -> list[Finding]:
    """Run every enabled rule over ``text`` and return findings in order.

    Findings silenced by an inline ``voicelint: ignore`` directive are removed;
    use :func:`check_counting` to also learn how many were suppressed."""
    return check_counting(text, cfg)[0]


def check_counting(text: str, cfg: dict):
    """Like :func:`check`, but return ``(findings, suppressed_count)``."""
    # A FILE THAT DEFINES THE PROHIBITIONS HAS TO BE ABLE TO NAME THEM. Without this,
    # a rules document reports an error for every phrase it bans, which trains a reader
    # to ignore the linter on the one file that must stay exact. `voice-rules.md` here has
    # the problem in its own right, and so does any downstream rule set: an error for every
    # phrase it quotes. Adopted upstream 2026-09-01 from a project that had it locally.
    #
    # Opt in per file, visible in the source, rather than hardcoded to a path. It is the
    # bluntest instrument in this file and it is meant to be rare: it silences everything,
    # so it belongs on rule sets and nothing else.
    text = normalize_quotes(text)
    at = _linecol_fn(text)
    # Match against a copy with code spans blanked; offsets are preserved, so
    # findings still point at the real line and column. Suppression directives
    # are read from the masked text, so a backticked directive cannot silence a
    # real finding. The rules-file marker is read the same way and must stand
    # as an HTML comment on its own line: mentioned in prose or quoted as code,
    # it is text, not a directive.
    text = mask_code(text)
    if _RULES_FILE_MARKER.search(text):
        return [], 0
    suppress = _suppression_map(text)
    allow = _allow_phrases(text)
    # Once read, a directive comment is blanked so its own words are not linted:
    # "ignore-line banned.game-changer" names the phrase it silences.
    text = re.sub(r"<!--\s*voicelint(?:-allow)?:.*?-->",
                  lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)
    out: list[Finding] = []

    spans: list[tuple[int, int]] = []  # parallel to out: character offsets of each match

    def add(m, severity, rule, message, rule_id=None):
        line, col = at(m.start())
        out.append(Finding(line, col, severity, rule, m.group(0).strip(), message, rule_id or rule))
        spans.append((m.start(), m.end()))

    # em / en / horizontal bar. An en dash between digits is a range (pages 10–12,
    # 1914–18), which the prose rules allow, so it is not a hit.
    dash_hits = [m for m in _iter(r"[—–―]", text, flags=0)
                 if not (m.group(0) == "–" and m.start() > 0 and text[m.start() - 1].isdigit()
                         and m.end() < len(text) and text[m.end()].isdigit())]
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

    # THE HONEST X, PROMOTED FROM WARNING TO ERROR AND MOVED UPSTREAM 2026-09-01.
    #
    # Brian's standing rule is absolute: never write "the honest answer / version / limit / truth /
    # read / case / part / thing". It announces candour instead of exercising it, it reads as a
    # finding when it is a throat-clear, and it is nearly always deletable, because the sentence
    # after it is the thing.
    #
    # Widened 2026-09-15 to the family voice-rules.md actually states: any determiner, an optional
    # adjective, and a noun that names the utterance (answer, take, look, note, framing...). It had
    # been twelve literals beginning "the", so "One Honest First Look" walked past it and, in a
    # downstream corpus, "the honest obstacle is that" only warned. The nouns that name a real
    # object (broker, axis, accounting, assessment) are subject matter and do not fire; the copular
    # form "[det] honest NOUN is that" fires whatever the noun, because the shape is the tic.
    if cfg.get("no_honest_framing", True):
        nouns = (r"(?:answer|answers|version|limit|limits|truth|read|reading|take|look|note|notes|"
                 r"framing|thing|part|case|move|position|summary|one|assessment\s+is\s+that)")
        pat = (rf"\b{_DET}\s+honest\s+(?:\w+\s+)?{nouns}\b"
               rf"|\b{_DET}\s+honest\s+(?:\w+\s+)?\w+\s+is\s+(?:that|this)\b")
        for m in _iter(pat, text):
            add(m, "error", "honest-framing",
                "'the honest X' performs candour instead of exercising it; cut it and say the thing")

    # A banned or bait entry is a literal phrase, or a raw regex under "re:" (no
    # word-edge guard then; the regex says where it ends). The message shows the
    # rationale when the entry has one, since a regex is not a readable label.
    def literal_or_regex(phrase):
        if phrase.startswith("re:"):
            return phrase[3:], ""
        return re.escape(phrase), phrase

    for e in rule_entries(cfg, "banned_phrases"):
        pat, guard = literal_or_regex(e["pattern"])
        label = e.get("rationale") or e["pattern"]
        for m in _iter_phrase(pat, guard, text):
            add(m, "error", "banned-phrase", f"canned phrase: '{label}'", e["id"])

    for e in rule_entries(cfg, "engagement_bait"):
        pat, guard = literal_or_regex(e["pattern"])
        label = e.get("rationale") or e["pattern"]
        for m in _iter_phrase(pat, guard, text):
            add(m, "error", "engagement-bait", f"manufactured-stance opener: '{label}'", e["id"])

    for e in rule_entries(cfg, "soft_phrases"):
        phrase = e["pattern"]
        label = e.get("rationale") or phrase
        for m in _iter_phrase(_soft_to_regex(phrase), phrase, text):
            add(m, "warning", "soft-cliche", f"overused AI phrasing: '{label}'", e["id"])

    if cfg.get("flag_loaded_quietly", True):
        for m in _iter(r"\bquietly\b(?=\s*(?:[.,;:!?)\]]|$))", text, flags=re.IGNORECASE | re.MULTILINE):
            add(m, "warning", "loaded-adverb", "trailing 'quietly'; the insinuating position. Put it before the verb or cut it")

    for e in rule_entries(cfg, "filler_words"):
        word = e["pattern"]
        for m in _iter(rf"\b{re.escape(word)}\b", text):
            add(m, "warning", "filler", f"filler/intensifier: '{word}'", e["id"])

    # Watch-word overuse scales with length, like dash_density_cap above. The configured cap applies
    # at a baseline piece length; longer texts (a long entry, an assembled work) get proportional
    # headroom, floored at the cap so short pieces stay strict. Without this, a word used three times
    # across a multi-scene whole trips a cap meant for a single vignette.
    _ww_words = len(re.findall(r"\w+", text))
    _WW_BASELEN = 600
    for word, limit in cfg.get("watch_words", {}).items():
        hits = list(_iter(rf"\b{re.escape(word)}\b", text))
        cap = max(int(limit), round(int(limit) * _ww_words / _WW_BASELEN))
        if len(hits) > cap:
            add(hits[cap], "warning", "overuse",
                f"'{word}' used {len(hits)} times (cap {cap} for {_ww_words} words); vary it",
                "overuse." + _slug(word))

    domains = [(e["pattern"].lower().strip("."), e["id"])
               for e in rule_entries(cfg, "aggregator_domains") if e["pattern"].strip(".")]
    if domains:
        # Only scheme-bearing URLs are scanned; a bare "msn.com/x" with no
        # scheme is left to the judgment layer, since a loose host regex would
        # reintroduce path and prose false positives.
        for m in _iter(r"https?://[^\s)\"'<>]+", text):
            host = (urlsplit(m.group(0)).hostname or "").lower().rstrip(".")
            if not host:
                continue
            labels = host.split(".")
            for domain, rule_id in domains:
                # A dotted domain matches as a host suffix (msn.com in
                # www.msn.com); a bare label matches a whole label
                # (timesofindia in timesofindia.indiatimes.com). Neither
                # matches the same string sitting in the path or query.
                if "." in domain:
                    hit = host == domain or host.endswith("." + domain)
                else:
                    hit = domain in labels
                if hit:
                    add(m, "error", "source", f"low-trust/aggregator source: {domain}", rule_id)
                    break

    out = _collapse_overlaps(out, spans)

    if suppress or allow:
        kept, dropped = [], 0
        for f in out:
            names = suppress.get(f.line)
            if names and ("*" in names or f.rule in names or f.rule_id in names):
                dropped += 1
                continue
            # A marker declares the PHRASE ("it is worth") while a rule fires on the
            # realised text ("it is worth nothing"), so equality would never suppress
            # one. Containment either way, on collapsed whitespace and at word
            # boundaries, covers the forms a rule actually matches without letting
            # an allowance for "land" swallow a "landscape" finding.
            hit = " ".join(f.match.split()).strip().lower()
            if any(e and _phrase_within(e, hit) or _phrase_within(hit, e) for e in allow if e):
                dropped += 1
                continue
            kept.append(f)
        return kept, dropped
    return out, 0


# Rules that match a stretch of text and can pile up on one another. Overlapping hits
# among these collapse to one finding; the counting and context rules (overuse, dash
# density, load-bearing-context, source) are left alone, because losing "quietly used
# four times" to a soft phrase that happens to contain "quietly" would hide a real count.
_PHRASE_RULES = frozenset({"banned-phrase", "engagement-bait", "soft-cliche", "honest-framing", "filler"})
_SEVERITY_RANK = {"error": 0, "warning": 1}


def _collapse_overlaps(out: list[Finding], spans: list[tuple[int, int]]) -> list[Finding]:
    """Keep one finding per stretch of text among the phrase rules.

    "This is what it buys you" used to produce four warnings for one tic, and the
    honest-framing error came with the broad honest warning on the same words.
    Errors beat warnings; at equal severity the longer match wins; ties keep the
    earlier-registered rule. Non-phrase rules pass through untouched."""
    order = sorted(range(len(out)), key=lambda i: (
        _SEVERITY_RANK.get(out[i].severity, 9), -(spans[i][1] - spans[i][0]), spans[i][0], i))
    kept_spans: list[tuple[int, int]] = []
    keep = set()
    for i in order:
        if out[i].rule not in _PHRASE_RULES:
            keep.add(i)
            continue
        s0, e0 = spans[i]
        if any(s0 < e1 and e0 > s1 for s1, e1 in kept_spans):
            continue
        kept_spans.append((s0, e0))
        keep.add(i)
    result = [out[i] for i in sorted(keep, key=lambda i: (spans[i][0], i))]
    result.sort(key=lambda f: (f.line, f.col))
    return result


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
    ap.add_argument("files", nargs="*", help="files to lint, or - for stdin")
    ap.add_argument("--config", help="path to a JSON rule set")
    ap.add_argument("--html", action="store_true", help="treat input as HTML (also auto-detected by extension)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--strict", action="store_true", help="warnings fail too")
    ap.add_argument("--quiet", action="store_true", help="only print the summary")
    ap.add_argument("--print-config", action="store_true",
                    help="print the effective rule set (defaults plus overlay) as JSON and exit")
    ap.add_argument("--list-rules", action="store_true",
                    help="print every rule the effective config runs (id, family, severity, pattern, rationale) and exit")
    args = ap.parse_args(argv)

    cfg = load_config(args.config or None)
    if args.print_config:
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
        return 0
    if args.list_rules:
        rows = all_rules(cfg)
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            for r in rows:
                tail = f"\t{r['rationale']}" if r["rationale"] else ""
                print(f"{r['id']}\t{r['family']}\t{r['severity']}\t{r['pattern']}{tail}")
        return 0
    if not args.files:
        ap.error("no files given (or - for stdin)")

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
                    print(f"{path}:{f.line}:{f.col} [{f.severity}] {f.rule} ({f.rule_id}): "
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
