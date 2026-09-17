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
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TOOL = os.path.join(HERE, "structlint.py")

import structlint  # noqa: E402


def run(args, text=None):
    return subprocess.run([sys.executable, TOOL, *args], input=text,
                          capture_output=True, text=True)


def rules(text, extra=()):
    """Return the set of rule names structlint reports for a passage."""
    out = set()
    for line in run([*extra, "-"], text).stdout.splitlines():
        if "[warning]" in line:
            out.add(line.split("[warning]")[1].split("(")[0].strip())
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


class TwoBeatIsSyntactic(unittest.TestCase):
    # The regression: two short sentences of matched length were called a
    # parallel on length and capitalisation alone.
    def test_matched_length_alone_is_not_a_parallel(self):
        self.assertNotIn("two-beat", rules("The meeting starts at nine. Lunch follows at noon.\n"))
        self.assertNotIn("two-beat", rules("She opened the window. Rain came in.\n"))

    def test_shared_opener(self):
        self.assertIn("two-beat", rules("None of them wrong. None of them ours.\n"))
        self.assertIn("two-beat", rules("Not a rumour. Not a mistake.\n"))

    def test_matched_negation(self):
        self.assertIn("two-beat", rules("Nobody asked for it. It never came.\n"))

    def test_shared_closing_word(self):
        self.assertIn("two-beat", rules("He had a name. She had a name.\n"))

    def test_repeated_content_word_same_shape(self):
        self.assertIn("two-beat", rules("The count was wrong. The ledger was right.\n"))


class SpansAreMaskedNotLines(unittest.TestCase):
    # The regression: a line with a URL, a citation marker, or a long quotation
    # was dropped whole, so a staccato run beside a link was invisible.
    def test_staccato_beside_a_url(self):
        self.assertIn("staccato", rules("See https://example.com. It failed. It broke. It stopped.\n"))

    def test_staccato_beside_a_year(self):
        self.assertIn("staccato", rules("Smith showed it (2020). It failed. It broke. It stopped.\n"))

    def test_prose_after_a_long_quotation(self):
        text = ('He said "' + "x" * 70 + '" and left. It failed. It broke. It stopped.\n')
        self.assertIn("staccato", rules(text))

    def test_bibliographic_entry_is_still_dropped(self):
        self.assertNotIn("staccato", rules(
            "Smith, J. (2020). A short title. A journal. Vol. 3. pp. 1-10.\n"))
        self.assertNotIn("staccato", rules(
            "- Doe, A. B. Title here. Elsewhere. Again. https://doi.org/x DOI 10.1/x\n"))

    def test_a_url_alone_is_not_a_sentence_run(self):
        self.assertEqual(rules("See https://example.com/a and https://example.com/b for more.\n"), set())


class HeaderTightening(unittest.TestCase):
    # The regression: "The actual results" and "Where the chair sits" fired.
    def test_naming_headers_are_fine(self):
        self.assertNotIn("header", rules("## The actual results\n"))
        self.assertNotIn("header", rules("## The real numbers\n"))
        self.assertNotIn("header", rules("## Where the chair sits\n"))
        self.assertNotIn("header", rules("## Where data lives\n"))

    def test_posing_headers_still_fire(self):
        self.assertIn("header", rules("## The real problem\n"))
        self.assertIn("header", rules("## The actual question\n"))
        self.assertIn("header", rules("## Where Stage 3 Sits\n"))
        self.assertIn("header", rules("## Where this sits\n"))
        self.assertIn("header", rules("## Where the argument stands\n"))


class Thresholds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def cfg(self, body):
        p = os.path.join(self.tmp.name, "c.json")
        with open(p, "w") as fh:
            json.dump(body, fh)
        return p

    def test_defaults_when_no_config(self):
        self.assertEqual(structlint.load_thresholds(None)["short_chars"], 46)

    def test_overlay_sets_one_key_and_keeps_the_rest(self):
        t = structlint.load_thresholds(self.cfg({"structure": {"staccato_run": 4}}))
        self.assertEqual(t["staccato_run"], 4)
        self.assertEqual(t["short_chars"], 46)

    def test_threshold_changes_the_verdict(self):
        text = "It finds the break. It reports the season. It flags the outages.\n"
        self.assertIn("staccato", rules(text))
        self.assertNotIn("staccato", rules(text, ["--config", self.cfg({"structure": {"staccato_run": 4}})]))

    def test_bad_structure_value_is_a_config_error(self):
        p = self.cfg({"structure": {"staccato_run": "three"}})
        self.assertEqual(run(["--config", p, "-"], "x").returncode, 2)
        p = self.cfg({"structure": {"no_such_key": 1}})
        self.assertEqual(run(["--config", p, "-"], "x").returncode, 2)


class FindingShape(unittest.TestCase):
    def test_text_line_carries_rule_id(self):
        out = run(["-"], "None of them wrong. None of them ours.\n").stdout
        self.assertIn("-:1:1 [warning] two-beat (structure.two-beat):", out)

    def test_json_matches_voicelint_envelope(self):
        d = json.loads(run(["--json", "-"], "None of them wrong. None of them ours.\n").stdout)
        self.assertIn("files", d)
        f = d["files"]["-"][0]
        for k in ("line", "col", "severity", "rule", "match", "message", "rule_id"):
            self.assertIn(k, f)
        self.assertEqual((f["rule"], f["rule_id"], f["severity"], f["col"]), ("two-beat", "structure.two-beat", "warning", 1))

    def test_density_finding_has_line_zero(self):
        text = "\n\n".join(["None of them wrong. None of them ours."] * 12) + "\n" + "word " * 60 + "\n"
        d = json.loads(run(["--json", "-"], text).stdout)
        dens = [f for f in d["files"]["-"] if f["rule"] == "density"]
        self.assertEqual(len(dens), 1)
        self.assertEqual((dens[0]["line"], dens[0]["col"], dens[0]["rule_id"]), (0, 0, "structure.density"))


class RepeatedFrame(unittest.TestCase):
    """The document-level check for a syntactic frame recurring across
    headings, sentences, or paragraph closers (2026-09-16)."""

    def deck(self, titles):
        return "# Deck\n\n" + "\n\n".join(f"## {i}. {t}\n\nBody line for slide {i}." for i, t in enumerate(titles, 1)) + "\n"

    def test_titles_on_one_mould_fire(self):
        titles = ["A choice with reasoning, not a default selection", "A recommender you evaluate, not an oracle",
                  "Cheat sheets to get you started, not manuals", "Picking the type is not the last decision"]
        titles += [f"Section {i}" for i in range(30)]
        self.assertIn("frame", rules(self.deck(titles)))

    def test_one_or_two_titles_do_not(self):
        titles = ["A recommender you evaluate, not an oracle", "Prettier is not fixed"] + [f"Section {i}" for i in range(30)]
        self.assertNotIn("frame", rules(self.deck(titles)))

    def test_subtitle_under_a_heading_counts_as_title_text(self):
        text = "# Deck\n\n" + "\n\n".join(
            f"## {i}. Section {i}\nA choice with reasoning, not a default selection.\n\nBody." for i in range(1, 5))
        text += "\n\n" + "\n\n".join(f"## {i}. Section {i}\n\nBody." for i in range(5, 40))
        self.assertIn("frame", rules(text))

    def test_sentences_on_one_mould_fire(self):
        sent = "We take this as a problem statement, not a solved result. "
        plain = "The reviewer reads the record and decides. "
        text = (sent + plain * 3) * 12
        self.assertIn("frame", rules(text + "\n"))
        self.assertNotIn("frame", rules((sent + plain * 9) * 12 + "\n"), "below the share it is a habit, not a frame")

    def test_finding_quotes_the_units_and_names_the_kind(self):
        titles = ["A choice, not a default"] * 5 + [f"Section {i}" for i in range(10)]
        out = run(["--json", "-"], self.deck(titles)).stdout
        f = [x for x in json.loads(out)["files"]["-"] if x["rule"] == "frame"][0]
        self.assertEqual(f["rule_id"], "structure.frame.contrast.heading")
        self.assertIn("5/16 headings", f["match"])  # the # Deck title is a heading too
        self.assertIn("A choice, not a default", f["match"])

    def test_paired_beat_titles_fire(self):
        # FA550, 2026-09-13 to 2026-09-17: three of these across two decks, each fine alone
        titles = ["What you keep, what you change", "Twelve outputs, seven decisions", "One question, four tools",
                  "How it starts, how it ends", "Ten pages, five tools"] + [f"Section {i}" for i in range(20)]
        out = run(["--json", "-"], self.deck(titles)).stdout
        ids = [x["rule_id"] for x in json.loads(out)["files"]["-"] if x["rule"] == "frame"]
        self.assertIn("structure.frame.paired-beat.heading", ids)
        self.assertNotIn("frame", rules(self.deck(["Keeping what worked", "Dana's A1, annotated", "Ten pages, all posted"]
                                                   + [f"Section {i}" for i in range(20)])))

    def test_appositive_tail_subtitles_fire(self):
        subs = ["Three layers, and tonight is the second visit to the second",
                "One chart from start to finish, then your discovery list",
                "The same paragraph about the revenue chart, sent back three ways",
                "The same discipline, pointed at AI charts", "Last week's patterns, now nameable"]
        text = "# Deck\n\n" + "\n\n".join(f"## {i}. Section {i}\n{s_}\n\nBody." for i, s_ in enumerate(subs, 1))
        text += "\n\n" + "\n\n".join(f"## {i}. Section {i}\n\nBody." for i in range(6, 30))
        out = run(["--json", "-"], text + "\n").stdout
        ids = [x["rule_id"] for x in json.loads(out)["files"]["-"] if x["rule"] == "frame"]
        self.assertIn("structure.frame.appositive-tail.heading", ids)

    def test_thresholds_are_configurable(self):
        titles = ["A choice, not a default"] * 3 + [f"Section {i}" for i in range(40)]
        self.assertNotIn("frame", rules(self.deck(titles)))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.json")
            json.dump({"structure": {"frame_heading_share": 0.05}}, open(p, "w"))
            self.assertIn("frame", rules(self.deck(titles), ["--config", p]))


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
