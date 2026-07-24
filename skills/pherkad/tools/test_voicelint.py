#!/usr/bin/env python3
"""Regression tests for voicelint. Dependency-free.

Run from this directory:  python3 test_voicelint.py
Exit 0 if all pass, 1 otherwise. Safe to wire into CI.

Covers the core rules, CLI behavior, and documented examples: word-boundary
and Unicode-edge false positives, load-bearing literal-versus-figurative
context, code-span masking, dash and density modes with the 150-word / 3-hit
floor, the config deep-merge and add_/remove_ list ops, host-versus-path domain
matching, HTML stripping, JSON output, --strict, exit codes, invalid config,
and line/column accuracy. It is not exhaustive; the judgment layer is not
tested here.
"""
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import voicelint  # noqa: E402

DEFAULT = voicelint.load_config(os.path.join(HERE, "voice_config.json"))

_failures = []


def check(name, cond):
    if not cond:
        _failures.append(name)


def rules(text, cfg=DEFAULT):
    """The set of rule names voicelint fires on a string."""
    return {f.rule for f in voicelint.check(text, cfg)}


def findings(text, cfg=DEFAULT):
    return voicelint.check(text, cfg)


# ---------------------------------------------------------------------------
# 1. Rule firing and word-boundary false positives
# ---------------------------------------------------------------------------
# (description, text, rule, should_fire)
FIRING = [
    ("banned phrase fires", "This is a game-changer for the team.", "banned-phrase", True),
    ("banned phrase mid-word does not fire",
     "The paradigm shifts the debate.", "banned-phrase", False),
    ("banned phrase fires as a whole phrase",
     "That was a paradigm shift.", "banned-phrase", True),
    ("engagement bait fires", "Here's the thing: nobody cares.", "engagement-bait", True),
    ("banned phrase with trailing punct still fires",
     "In conclusion, we won.", "banned-phrase", True),
    ("filler fires on whole word", "A significant result.", "filler", True),
    ("filler does not fire inside a word",
     "The signification of the sign.", "filler", False),
    ("load-bearing + non-structural object is a context warning",
     "The load-bearing assumption fails.", "load-bearing-context", True),
    ("load-bearing never emits a hard error (judgment layer decides figurative)",
     "The load-bearing assumption fails.", "load-bearing", False),
    ("load-bearing + ambiguous noun emits a context warning",
     "This is the load-bearing structure of the argument.", "load-bearing-context", True),
    ("predicate load-bearing is a context warning",
     "That claim is load-bearing.", "load-bearing-context", True),
    ("engineering member is fully exempt (no finding)",
     "The load-bearing member failed inspection.", "load-bearing-context", False),
    ("literal load-bearing wall is exempt",
     "The load-bearing wall held.", "load-bearing-context", False),
    ("literal load-bearing beam is exempt",
     "The load-bearing beam passed inspection.", "load-bearing-context", False),
    ("dash fires by default", "We shipped it — then paused.", "dash", True),
    ("mathematical minus is not a dash", "The result is 5 − 3.", "dash", False),
    ("plain manner quietly is silent by default",
     "She shut the nursery door quietly.", "loaded-adverb", False),
    ("watch-word overuse fires past the cap",
     "quietly quietly quietly it went", "overuse", True),
    ("no aggregator domains in the generic defaults",
     "See https://www.msn.com/story for more.", "source", False),
]
for desc, text, rule, should in FIRING:
    check(desc, (rule in rules(text)) == should)


# ---------------------------------------------------------------------------
# 2. Code-span masking: a pattern quoted as code is not flagged
# ---------------------------------------------------------------------------
check("inline code span is masked",
      "banned-phrase" not in rules("The `game-changer` phrase is an example."))
check("fenced code block is masked",
      "banned-phrase" not in rules("```\ngame-changer\n```\n"))
check("the same phrase in prose still fires",
      "banned-phrase" in rules("that game-changer here"))


# ---------------------------------------------------------------------------
# 3. quietly rule is opt-in, and still works when enabled
# ---------------------------------------------------------------------------
ON = voicelint.load_config(None)  # defaults, then flip the rule on
ON = dict(ON)
ON["flag_loaded_quietly"] = True
check("quietly fires clause-final when enabled",
      "loaded-adverb" in rules("The project was shut down quietly.", ON))
check("quietly pre-modifier stays silent even when enabled",
      "loaded-adverb" not in rules("A quietly skeptical engineer watched.", ON))


# ---------------------------------------------------------------------------
# 4. Dash density (relaxed mode): floor of 150 words and 3 dash hits
# ---------------------------------------------------------------------------
relaxed = dict(DEFAULT)
relaxed["no_dashes"] = False
relaxed["dash_density_cap"] = 1.0


def dash_density(words, dashes):
    text = ("word " * words) + " ".join(["—"] * dashes)
    return "dash-density" in rules(text, relaxed)


check("149 words with 3 dashes: below the word floor, silent", not dash_density(149, 3))
check("150 words with 3 dashes: at the floor, warns", dash_density(150, 3))
check("150 words with 2 dashes: below the hit floor, silent", not dash_density(150, 2))
check("short text raises no dash-density warning", not dash_density(5, 2))


# ---------------------------------------------------------------------------
# 4b. Unicode-safe phrase edges
# ---------------------------------------------------------------------------
import unicodedata as _ud
_nfc = _ud.normalize("NFC", "\u00e9game-changer\u00e9 here")   # precomposed accents
_nfd = _ud.normalize("NFD", "\u00e9game-changer here")          # base + combining mark
check("phrase between precomposed accented letters does not fire",
      "banned-phrase" not in rules(_nfc))
check("phrase after a decomposed accent (base + combining mark) does not fire",
      "banned-phrase" not in rules(_nfd))
check("phrase with an accented word after it still fires",
      "banned-phrase" in rules("that game-changer caf\u00e9"))


# ---------------------------------------------------------------------------
# 4c. Domain matching reads the host, not the whole URL
# ---------------------------------------------------------------------------
NEWS = voicelint.load_config(os.path.join(HERE, "examples", "news-brief.json"))
check("aggregator host fires under the news preset",
      "source" in rules("See https://www.msn.com/story here.", NEWS))
check("bare-label domain fires as a host label",
      "source" in rules("See https://timesofindia.indiatimes.com/x here.", NEWS))
check("aggregator name in the path does not fire",
      "source" not in rules("See https://example.com/path/msn.com/story here.", NEWS))
check("aggregator name in the query does not fire",
      "source" not in rules("See https://example.com/?u=https://msn.com/x here.", NEWS))
check("an unlisted host does not fire",
      "source" not in rules("See https://www.congress.gov/bill here.", NEWS))
check("a fully-qualified host with a trailing dot still fires",
      "source" in rules("See https://www.msn.com./story here.", NEWS))
check("userinfo that looks like the host does not fire",
      "source" not in rules("See https://msn.com@evil.example/x here.", NEWS))


# ---------------------------------------------------------------------------
# 5. Config deep-merge and list ops
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "c.json")
    with open(p, "w") as fh:
        json.dump({
            "watch_words": {"live": 5},
            "add_banned_phrases": ["circle back"],
            "remove_banned_phrases": ["game-changer"],
        }, fh)
    cfg = voicelint.load_config(p)
    check("deep-merge keeps the sibling default watch word", cfg["watch_words"].get("quietly") == 2)
    check("deep-merge adds the named watch word", cfg["watch_words"].get("live") == 5)
    check("add_ extends the default list", "circle back" in cfg["banned_phrases"])
    check("remove_ drops from the default list", "game-changer" not in cfg["banned_phrases"])
    check("add_/remove_ helper keys are consumed",
          "add_banned_phrases" not in cfg and "remove_banned_phrases" not in cfg)


# ---------------------------------------------------------------------------
# 6. HTML stripping keeps line numbers; entities decode
# ---------------------------------------------------------------------------
html_findings = voicelint.check(
    voicelint.strip_html("<p>ok</p>\n<p>This is a game-changer.</p>"), DEFAULT)
check("html strip preserves the line of a finding",
      any(f.rule == "banned-phrase" and f.line == 2 for f in html_findings))


# ---------------------------------------------------------------------------
# 7. Line and column accuracy
# ---------------------------------------------------------------------------
fs = findings("ok ok\nhere game-changer now")
check("line/col points at the real position",
      any(f.rule == "banned-phrase" and f.line == 2 and f.col == 6 for f in fs))


# ---------------------------------------------------------------------------
# 8. CLI contract: exit codes, --strict, --json, invalid config
# ---------------------------------------------------------------------------
SCRIPT = os.path.join(HERE, "voicelint.py")


def run(args, text=None):
    proc = subprocess.run([sys.executable, SCRIPT, *args],
                          input=text, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


with tempfile.TemporaryDirectory() as d:
    clean = os.path.join(d, "clean.md")
    dirty = os.path.join(d, "dirty.md")
    warnonly = os.path.join(d, "warn.md")
    badcfg = os.path.join(d, "bad.json")
    open(clean, "w").write("A short, clean sentence about the weather.\n")
    open(dirty, "w").write("This is a game-changer.\n")
    open(warnonly, "w").write("A significant result.\n")  # filler = warning only
    open(badcfg, "w").write('{"banned_phrases": "not a list"}')

    code, _, _ = run([clean]); check("clean file exits 0", code == 0)
    code, _, _ = run([dirty]); check("error finding exits 1", code == 1)
    code, _, _ = run(["/no/such/file.md"]); check("missing file exits 2", code == 2)
    code, _, _ = run(["--config", badcfg, clean]); check("invalid config exits 2", code == 2)
    code, _, _ = run([warnonly]); check("warning-only exits 0 without --strict", code == 0)
    code, _, _ = run(["--strict", warnonly]); check("warning-only exits 1 with --strict", code == 1)

    code, out, _ = run(["--json", dirty])
    parsed = json.loads(out)
    check("json has a files map and a suppressed count",
          isinstance(parsed, dict) and "files" in parsed and "suppressed" in parsed)
    check("json finding carries line/rule",
          any(x["rule"] == "banned-phrase" for x in parsed["files"][dirty]))

    # bad boolean type and unknown key both exit 2
    boolcfg = os.path.join(d, "boolcfg.json")
    open(boolcfg, "w").write('{"no_dashes": "false"}')
    code, _, _ = run(["--config", boolcfg, clean])
    check("string in a boolean field exits 2", code == 2)
    typocfg = os.path.join(d, "typocfg.json")
    open(typocfg, "w").write('{"no_dash": false}')
    code, _, _ = run(["--config", typocfg, clean])
    check("unknown config key exits 2", code == 2)
    okcfg = os.path.join(d, "okcfg.json")
    open(okcfg, "w").write('{"no_dashes": false, "_note": "fine"}')
    code, _, _ = run(["--config", okcfg, clean])
    check("valid config with a comment key exits 0", code == 0)

    # semantic validation: negative caps and empty patterns are rejected (exit 2),
    # not accepted into a runtime crash or a match-everywhere rule
    negcap = os.path.join(d, "negcap.json")
    open(negcap, "w").write('{"watch_words": {"quietly": -1}}')
    code, _, _ = run(["--config", negcap, clean])
    check("negative watch-word cap exits 2", code == 2)
    emptyphrase = os.path.join(d, "empty.json")
    open(emptyphrase, "w").write('{"add_banned_phrases": [""]}')
    code, _, _ = run(["--config", emptyphrase, clean])
    check("empty configured phrase exits 2", code == 2)


# ---------------------------------------------------------------------------
# 9. Inline suppression
# ---------------------------------------------------------------------------
kept, dropped = voicelint.check_counting(
    "This is a game-changer. <!-- voicelint: ignore-line banned-phrase -->", DEFAULT)
check("ignore-line drops the matching rule", not kept and dropped == 1)
kept, dropped = voicelint.check_counting(
    "<!-- voicelint: ignore-next-line -->\nThis is a game-changer.", DEFAULT)
check("ignore-next-line drops the next line", not kept and dropped == 1)
kept, dropped = voicelint.check_counting(
    "This is a game-changer. <!-- voicelint: ignore-line filler -->", DEFAULT)
check("a rule-specific ignore leaves other rules firing", len(kept) == 1 and dropped == 0)
# a directive must be an HTML comment; backticked or prose text cannot suppress
kept, dropped = voicelint.check_counting(
    "This is a game-changer. `voicelint: ignore-line`", DEFAULT)
check("a backticked directive does not suppress", len(kept) == 1 and dropped == 0)
kept, dropped = voicelint.check_counting(
    "This is a game-changer and the words voicelint: ignore-line appear.", DEFAULT)
check("a directive token in prose does not suppress", len(kept) == 1 and dropped == 0)


# ---------------------------------------------------------------------------
# 10. Fallback config is not shared mutable state
# ---------------------------------------------------------------------------
a = voicelint.load_config(None)
a["banned_phrases"].append("state leak probe")
a["watch_words"]["quietly"] = 99
b = voicelint.load_config(None)
check("a mutated config does not leak into the next load",
      "state leak probe" not in b["banned_phrases"] and b["watch_words"]["quietly"] == 2)


# ---------------------------------------------------------------------------
# 9. Example fixtures behave as shipped
# ---------------------------------------------------------------------------
ex = os.path.join(HERE, "examples")
if os.path.isdir(ex):
    good = os.path.join(ex, "good.md")
    bad = os.path.join(ex, "bad.md")
    if os.path.exists(good):
        code, _, _ = run([good]); check("examples/good.md is clean (exit 0)", code == 0)
    if os.path.exists(bad):
        code, _, _ = run([bad]); check("examples/bad.md has findings (exit 1)", code == 1)


# ---------------------------------------------------------------------------
def main():
    total = "many"
    if _failures:
        print("FAIL ({} case(s)):".format(len(_failures)))
        for f in _failures:
            print("  - " + f)
        return 1
    print("ok: all voicelint cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
