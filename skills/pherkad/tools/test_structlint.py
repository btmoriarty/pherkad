#!/usr/bin/env python3
"""Regression tests for structlint. Dependency-free.

Run from anywhere:  python3 /path/to/test_structlint.py
Also collected by ``python3 -m unittest`` and by pytest. Exit 0 if all pass.

Covers the checks and, more importantly, the false positives that made the
tool unusable before they were fixed: hard-wrapped prose read line by line,
list items and instruction steps, blockquoted prompts, bold run-in labels, and
clauses ending in a colon. A checker that cries wolf gets ignored, so the
negative cases matter more here than the positive ones.
"""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "structlint.py")


def run(args, text=None):
    return subprocess.run([sys.executable, TOOL, *args], input=text,
                          capture_output=True, text=True)


def rules(text):
    """Return the set of rule names structlint reports for a passage."""
    out = set()
    for line in run(["-"], text).stdout.splitlines():
        if "[warning]" in line:
            out.add(line.split("[warning]")[1].split(":")[0].strip())
    return out


class Fires(unittest.TestCase):
    def test_two_beat(self):
        self.assertIn("two-beat", rules("None of them wrong. None of them ours.\n"))

    def test_staccato(self):
        self.assertIn("staccato", rules("It finds the break. It reports the season. It flags the outages.\n"))

    def test_stance_header(self):
        self.assertIn("header", rules("## The one thing that sinks it\n"))

    def test_abstract_carries_in_a_title(self):
        self.assertIn("header", rules("## Design That Carries a Decision\n"))

    def test_aphorism(self):
        # The shape that slipped both checkers on 2026-08-21: a comparative
        # weighed against an elliptical negation inside a single sentence.
        self.assertIn("aphorism", rules(
            "a source you find yourself and finish is worth more than one "
            "from this page that you do not.\n"))
        self.assertIn("aphorism", rules(
            "A dashboard that answers one question well is worth more than "
            "one that does not.\n"))


class FalsePositives(unittest.TestCase):
    def test_hard_wrapped_prose_is_joined(self):
        self.assertNotIn("two-beat", rules(
            "Fill in the three bracketed parts. The reader and the decision\n"
            "matter more than the panel list, and without them you get generic\n"
            "advice that would apply to anything at all.\n"))

    def test_list_item_is_not_staccato(self):
        self.assertNotIn("staccato", rules("4. Send the round-two prompt, verbatim. Compare.\n"))

    def test_bold_run_in_label_is_not_a_sentence(self):
        self.assertNotIn("two-beat", rules(
            "- **Calibration:** What does this tool tend to do? Week 6, and again later.\n"))

    def test_blockquote_is_not_the_authors_rhythm(self):
        self.assertEqual(rules("> I made this decision. Ask me one question. Do not accept it.\n"), set())

    def test_clause_ending_in_a_colon(self):
        self.assertNotIn("two-beat", rules("Stages 1 and 2, three criteria. For each decision:\n"))

    def test_literal_carries_title(self):
        self.assertNotIn("header", rules("## How a chart carries a value\n"))

    def test_bracketed_template_placeholder(self):
        self.assertNotIn("staccato", rules(
            "[How are variables encoded? What does it emphasize? What does it hide?]\n"))

    def test_markdown_table_is_not_prose(self):
        self.assertNotIn("staccato", rules(
            "| Criterion | Points | What it covers |\n"
            "|-----------|--------|----------------|\n"
            "| **Critical analysis** | 3 | Source docs. |\n"
            "| **Redesign** | 3 | The rebuild. |\n"))

    def test_plain_comparisons_are_not_aphorisms(self):
        self.assertNotIn("aphorism", rules("Position is more accurate than length.\n"))
        self.assertNotIn("aphorism", rules("The result is better than we expected.\n"))
        self.assertNotIn("aphorism", rules("Use the source that you did not expect.\n"))


class InterrogativeHeadings(unittest.TestCase):
    # A rate check, added 2026-08-23. Brian flagged the habit in FA550 slide
    # titles and judged it a universal issue rather than a personal preference.
    def test_flagged_above_the_rate(self):
        many = "\n\n".join(["# D"] + [f"## What thing {i} does" for i in range(6)]
                           + [f"## Section {i}" for i in range(6)])
        self.assertIn("interrogative-headers", rules(many))

    def test_house_convention_is_fine(self):
        few = "\n\n".join(["# D"] + [f"## Section {i}" for i in range(10)]
                          + ["## What a filter does", "## What Week 5 Covered"])
        self.assertNotIn("interrogative-headers", rules(few))

    def test_genuine_questions_are_not_flagged(self):
        real = "\n\n".join(["# D"] + ["## Which one was yours?"] * 6
                           + [f"## Section {i}" for i in range(6)])
        self.assertNotIn("interrogative-headers", rules(real))

    def test_too_few_headings_to_judge(self):
        self.assertNotIn("interrogative-headers", rules("# D\n\n## What it does\n\n## Section\n"))


class Cli(unittest.TestCase):
    def test_clean_exits_0(self):
        self.assertEqual(run(["-"], "Plain prose, nothing wrong with it.\n").returncode, 0)

    def test_strict_exits_1_on_a_warning(self):
        self.assertEqual(run(["--strict", "-"], "None of them wrong. None of them ours.\n").returncode, 1)

    def test_json_emits_a_rule_field(self):
        self.assertIn('"rule"', run(["--json", "-"], "None of them wrong. None of them ours.\n").stdout)

    def test_missing_file_exits_2(self):
        self.assertEqual(run([os.path.join(HERE, "no-such-file.md")]).returncode, 2)

    def test_ignore_line_suppresses(self):
        self.assertNotIn("two-beat", rules(
            "None of them wrong. None of them ours. <!-- structlint: ignore-line -->\n"))


if __name__ == "__main__":
    unittest.main()
