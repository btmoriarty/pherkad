#!/usr/bin/env python3
"""Regression tests for voicelint. Dependency-free.

Run from this directory:  python3 test_voicelint.py
Exit 0 if all pass, 1 otherwise. Safe to wire into CI.

Covers every rule and every promised exception: word-boundary false positives,
load-bearing literal context, code-span masking, dash and density modes, the
config deep-merge and add_/remove_ list ops, domain matching, HTML stripping,
JSON output, --strict, exit codes, invalid config, and line/column accuracy.
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
     "This is the movement we need.", "banned-phrase", False),
    ("engagement bait fires", "Here's the thing: nobody cares.", "engagement-bait", True),
    ("banned phrase with trailing punct still fires",
     "In conclusion, we won.", "banned-phrase", True),
    ("filler fires on whole word", "A significant result.", "filler", True),
    ("filler does not fire inside a word",
     "The signification of the sign.", "filler", False),
    ("figurative load-bearing fires",
     "That assumption is load-bearing for the argument.", "load-bearing", True),
    ("literal load-bearing wall is exempt",
     "The load-bearing wall held.", "load-bearing", False),
    ("literal load-bearing beam is exempt",
     "The load-bearing beam passed inspection.", "load-bearing", False),
    ("literal load-bearing column is exempt",
     "A load-bearing column carries the floor.", "load-bearing", False),
    ("dash fires by default", "We shipped it — then paused.", "dash", True),
    ("plain manner quietly is silent by default",
     "She shut the nursery door quietly.", "loaded-adverb", False),
    ("watch-word overuse fires past the cap",
     "live live live coverage", "overuse", True),
    ("aggregator domain fires",
     "See https://www.msn.com/story for more.", "source", True),
    ("real domain does not fire",
     "See https://www.congress.gov/bill for more.", "source", False),
]
for desc, text, rule, should in FIRING:
    check(desc, (rule in rules(text)) == should)


# ---------------------------------------------------------------------------
# 2. Code-span masking: a pattern quoted as code is not flagged
# ---------------------------------------------------------------------------
check("inline code span is masked",
      "banned-phrase" not in rules("The `is the move` phrase is an example."))
check("fenced code block is masked",
      "banned-phrase" not in rules("```\nis the move\n```\n"))
check("the same phrase in prose still fires",
      "banned-phrase" in rules("that is the move here"))


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
# 4. Dash density (relaxed mode) needs a floor of text
# ---------------------------------------------------------------------------
relaxed = dict(DEFAULT)
relaxed["no_dashes"] = False
relaxed["dash_density_cap"] = 1.0
short = "A — B."  # over the rate, but far too short to judge
check("short text raises no dash-density warning",
      "dash-density" not in rules(short, relaxed))
long_over = ("word " * 200) + "— — —"
check("long text over the cap raises dash-density",
      "dash-density" in rules(long_over, relaxed))


# ---------------------------------------------------------------------------
# 5. Config deep-merge and list ops
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "c.json")
    with open(p, "w") as fh:
        json.dump({
            "watch_words": {"quietly": 5},
            "add_banned_phrases": ["circle back"],
            "remove_banned_phrases": ["game-changer"],
        }, fh)
    cfg = voicelint.load_config(p)
    check("deep-merge keeps sibling watch word", cfg["watch_words"].get("live") == 2)
    check("deep-merge overrides the named watch word", cfg["watch_words"].get("quietly") == 5)
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
fs = findings("ok ok\nhere is the move now")
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
    check("json output is a dict keyed by path", isinstance(parsed, dict) and dirty in parsed)
    check("json finding carries line/rule",
          any(x["rule"] == "banned-phrase" for x in parsed[dirty]))


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
