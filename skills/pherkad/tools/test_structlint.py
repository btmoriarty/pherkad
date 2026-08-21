#!/usr/bin/env python3
"""Regression tests for structlint. Dependency-free.

Run from this directory:  python3 test_structlint.py
Exit 0 if all pass, 1 otherwise. Safe to wire into CI.

Covers the four checks and, more importantly, the false positives that made
the tool unusable before they were fixed: hard-wrapped prose read line by line,
list items and instruction steps, blockquoted prompts, bold run-in labels, and
clauses ending in a colon. A checker that cries wolf gets ignored, so the
negative cases matter more here than the positive ones.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "structlint.py")

_failures = []


def check(name, cond):
    if not cond:
        _failures.append(name)


def rules(text):
    """Return the set of rule names structlint reports for a passage."""
    p = subprocess.run([sys.executable, TOOL, "-"], input=text,
                       capture_output=True, text=True)
    out = set()
    for line in p.stdout.splitlines():
        if "[warning]" in line:
            out.add(line.split("[warning]")[1].split(":")[0].strip())
    return out


def main():
    # --- the four checks fire on what they are for -------------------------
    check("two-beat fires on a clipped balanced parallel",
          "two-beat" in rules("None of them wrong. None of them ours.\n"))
    check("staccato fires on three short sentences",
          "staccato" in rules("It finds the break. It reports the season. It flags the outages.\n"))
    check("header fires on a stance header",
          "header" in rules("## The one thing that sinks it\n"))
    check("header fires on abstract carries in a title",
          "header" in rules("## Design That Carries a Decision\n"))

    # --- the false positives that mattered ---------------------------------
    check("hard-wrapped prose is joined before checking",
          "two-beat" not in rules(
              "Fill in the three bracketed parts. The reader and the decision\n"
              "matter more than the panel list, and without them you get generic\n"
              "advice that would apply to anything at all.\n"))
    check("a list item is not staccato",
          "staccato" not in rules("4. Send the round-two prompt, verbatim. Compare.\n"))
    check("a bold run-in label is not a sentence",
          "two-beat" not in rules(
              "- **Calibration:** What does this tool tend to do? Week 6, and again later.\n"))
    check("a blockquoted prompt is not the author's rhythm",
          rules("> I made this decision. Ask me one question. Do not accept it.\n") == set())
    check("a clause ending in a colon is not half a two-beat",
          "two-beat" not in rules("Stages 1 and 2, three criteria. For each decision:\n"))
    check("a literal carries title is left alone",
          "header" not in rules("## How a chart carries a value\n"))

    # --- CLI ---------------------------------------------------------------
    p = subprocess.run([sys.executable, TOOL, "-"], input="Plain prose, nothing wrong with it.\n",
                       capture_output=True, text=True)
    check("clean text exits 0", p.returncode == 0)
    p = subprocess.run([sys.executable, TOOL, "--strict", "-"],
                       input="None of them wrong. None of them ours.\n",
                       capture_output=True, text=True)
    check("--strict exits 1 on a warning", p.returncode == 1)
    p = subprocess.run([sys.executable, TOOL, "--json", "-"],
                       input="None of them wrong. None of them ours.\n",
                       capture_output=True, text=True)
    check("--json emits a rule field", '"rule"' in p.stdout)
    p = subprocess.run([sys.executable, TOOL, os.path.join(HERE, "no-such-file.md")],
                       capture_output=True, text=True)
    check("a missing file exits 2", p.returncode == 2)

    # --- suppression -------------------------------------------------------
    check("ignore-line suppresses",
          "two-beat" not in rules(
              "None of them wrong. None of them ours. <!-- structlint: ignore-line -->\n"))

    check("a bracketed template placeholder is not prose",
          "staccato" not in rules(
              "[How are variables encoded? What does it emphasize? What does it hide?]\n"))

    # --- tables ---------------------------------------------------------
    check("a markdown table is not prose",
          "staccato" not in rules(
              "| Criterion | Points | What it covers |\n"
              "|-----------|--------|----------------|\n"
              "| **Critical analysis** | 3 | Source docs. |\n"
              "| **Redesign** | 3 | The rebuild. |\n"))

    # --- aphorism ----------------------------------------------------------
    # The shape that slipped both checkers on 2026-08-21: a comparative weighed
    # against an elliptical negation, inside a single sentence, so the two-beat
    # check could not see the symmetry.
    check("manufactured maxim caught",
          "aphorism" in rules(
              "a source you find yourself and finish is worth more than one "
              "from this page that you do not.\n"))
    check("elided-pronoun variant caught",
          "aphorism" in rules(
              "A dashboard that answers one question well is worth more than "
              "one that does not.\n"))
    check("plain comparison is safe",
          "aphorism" not in rules("Position is more accurate than length.\n"))
    check("comparison without a negation tail is safe",
          "aphorism" not in rules("The result is better than we expected.\n"))
    check("negation without a comparative is safe",
          "aphorism" not in rules("Use the source that you did not expect.\n"))

    if _failures:
        print("FAIL ({} case(s)):".format(len(_failures)))
        for f in _failures:
            print("  - " + f)
        return 1
    print("ok: all structlint cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
