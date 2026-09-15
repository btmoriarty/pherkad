#!/usr/bin/env python3
"""Tests for the eval harness scorer. Dependency-free.

Run from anywhere:  python3 /path/to/test_study.py
Also collected by ``python3 -m unittest`` and by pytest.
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import study  # noqa: E402


def row(bid, writer, candidate, rating="", flag="", pick=""):
    return {"blind_id": bid, "writer": writer, "candidate": candidate,
            "rating": rating, "fidelity_flag": flag, "forced_choice_pick": pick}


class ReadRatings(unittest.TestCase):
    ROWS = [row("item-a", "brian", "a"), row("item-b", "brian", "b"), row("item-c", "brian", "c")]

    def test_pick_resolves_to_the_named_letter_not_the_row(self):
        # The regression: entering "b" on row "a" used to count as picking "a".
        rows = [row("item-a", "brian", "a", pick="b"), row("item-b", "brian", "b"), row("item-c", "brian", "c")]
        _, picks = study._read_ratings(rows)
        self.assertEqual(picks, {"brian": ["item-b"]})

    def test_pick_on_its_own_row_still_works(self):
        rows = [row("item-a", "brian", "a"), row("item-b", "brian", "b", pick="B"), row("item-c", "brian", "c")]
        _, picks = study._read_ratings(rows)
        self.assertEqual(picks, {"brian": ["item-b"]})

    def test_unknown_letter_stops_the_run(self):
        rows = [row("item-a", "brian", "a", pick="z"), row("item-b", "brian", "b")]
        with self.assertRaises(SystemExit):
            study._read_ratings(rows)

    def test_conflicting_picks_stop_the_run(self):
        rows = [row("item-a", "brian", "a", pick="a"), row("item-b", "brian", "b", pick="b")]
        with self.assertRaises(SystemExit):
            study._read_ratings(rows)

    def test_same_pick_on_two_rows_is_one_pick(self):
        rows = [row("item-a", "brian", "a", pick="b"), row("item-b", "brian", "b", pick="b")]
        _, picks = study._read_ratings(rows)
        self.assertEqual(picks, {"brian": ["item-b"]})

    def test_picks_are_per_writer(self):
        rows = [row("item-a", "brian", "a", pick="b"), row("item-b", "brian", "b"),
                row("item-x", "rosa", "a"), row("item-y", "rosa", "b", pick="a")]
        _, picks = study._read_ratings(rows)
        self.assertEqual(picks, {"brian": ["item-b"], "rosa": ["item-x"]})

    def test_ratings_parse_with_flag(self):
        rows = [row("item-a", "brian", "a", rating="4", flag="f"), row("item-b", "brian", "b")]
        ratings, _ = study._read_ratings(rows)
        self.assertEqual(ratings, {"item-a": (4.0, "F")})

    def test_rating_out_of_range_stops_the_run(self):
        with self.assertRaises(SystemExit):
            study._read_ratings([row("item-a", "brian", "a", rating="7")])

    def test_rating_not_a_number_stops_the_run(self):
        with self.assertRaises(SystemExit):
            study._read_ratings([row("item-a", "brian", "a", rating="four")])


class ReviseTask(unittest.TestCase):
    """The revision experiment end to end in a temporary data directory."""

    def setUp(self):
        import tempfile, io, contextlib
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.saved = {k: getattr(study, k) for k in ("DATA", "WRITERS", "BRIEFS", "RUNS")}
        study.DATA = d
        study.WRITERS = os.path.join(d, "writers")
        study.BRIEFS = os.path.join(d, "briefs")
        study.RUNS = os.path.join(d, "runs")
        self.quiet = lambda argv: self._run(argv)

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(study, k, v)
        self.tmp.cleanup()

    def _run(self, argv):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = study.main(argv)
        return code, buf.getvalue()

    def _setup_writer(self):
        self._run(["add-writer", "brian"])
        with open(os.path.join(study.WRITERS, "brian", "profile.md"), "w") as fh:
            fh.write("# profile\n\nShort sentences. Concrete detail.\n")
        with open(os.path.join(study.WRITERS, "brian", "samples", "s1.md"), "w") as fh:
            fh.write("A real sample by the writer.\n")
        self._run(["add-brief", "weeding"])

    def test_plan_prompts_sheet_score(self):
        self._setup_writer()
        code, out = self._run(["plan", "r1", "--task", "revise", "--brief", "weeding", "--writers", "brian",
                               "--repeats", "2", "--surface", "post"])
        self.assertEqual(code, 0, out)
        run_dir = os.path.join(study.RUNS, "r1")
        m = json.load(open(os.path.join(run_dir, "manifest.json")))
        self.assertEqual(m["task"], "revise")
        self.assertEqual(len(m["items"]), 5 * 2)
        self.assertEqual({it["arm"] for it in m["items"]}, set(study.ARMS))
        for it in m["items"]:
            for k in ("tool_version", "config_sha256", "profile_sha256", "surface", "repeat", "source"):
                self.assertIn(k, it)
        # no source yet: prompts reports it
        code, out = self._run(["prompts", "r1"])
        self.assertIn("no source draft for brian", out)
        with open(os.path.join(run_dir, "sources", "brian.md"), "w") as fh:
            fh.write("This is a game-changer. The honest answer is that it works.\n")
        code, out = self._run(["prompts", "r1", "--model", "test-model"])
        self.assertEqual(code, 0, out)
        m = json.load(open(os.path.join(run_dir, "manifest.json")))
        by_arm = {}
        for it in m["items"]:
            by_arm.setdefault(it["arm"], []).append(it)
        # untouched is copied, others get prompts with the right blocks and the model recorded
        untouched = by_arm["untouched"][0]
        self.assertEqual(open(os.path.join(run_dir, untouched["draft"])).read().strip(),
                         "This is a game-changer. The honest answer is that it works.")
        self.assertEqual(untouched["model"], "none (untouched)")
        for arm in ("generic", "mechanical", "judgment", "both"):
            it = by_arm[arm][0]
            self.assertEqual(it["model"], "test-model")
            self.assertTrue(it.get("prompt_sha256"))
            prompt = open(os.path.join(run_dir, "prompts", it["blind_id"] + ".txt")).read()
            self.assertIn("=== DRAFT ===", prompt)
            self.assertEqual("=== MECHANICAL FINDINGS ===" in prompt, arm in ("mechanical", "both"))
            self.assertEqual("=== VOICE PROFILE ===" in prompt, arm in ("judgment", "both"))
            if arm in ("mechanical", "both"):
                self.assertIn("banned.game-changer", prompt)
                self.assertIn("honest-framing", prompt)
            if arm == "judgment":
                self.assertIn("Do NOT run any linter", prompt)
        # fake the editing model: every arm returns a draft
        for it in m["items"]:
            p = os.path.join(run_dir, it["draft"])
            if not os.path.exists(p):
                with open(p, "w") as fh:
                    fh.write(f"Revised by {it['arm']}.\n")
        code, out = self._run(["sheet", "r1"])
        self.assertEqual(code, 0, out)
        self.assertIn("revision task", open(os.path.join(run_dir, "rating-sheet.md")).read())
        import csv
        rows = list(csv.DictReader(open(os.path.join(run_dir, "ratings.csv"))))
        self.assertEqual(len(rows), 10)
        self.assertIn("useful_edits", rows[0])
        # rate: generic 3, mechanical 4, judgment 5 (one flagged), both 4, untouched 2
        key = {it["blind_id"]: it for it in m["items"]}
        score = {"untouched": 2, "generic": 3, "mechanical": 4, "judgment": 5, "both": 4}
        for r in rows:
            it = key[r["blind_id"]]
            r["rating"] = str(score[it["arm"]])
            r["useful_edits"] = "2"
            r["unnecessary_edits"] = "0" if it["arm"] != "judgment" else "3"
            r["minutes"] = "1"
            if it["arm"] == "judgment" and it["repeat"] == 2:
                r["fidelity_flag"] = "F"
        with open(os.path.join(run_dir, "ratings.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        code, out = self._run(["score", "r1"])
        self.assertEqual(code, 0, out)
        res = open(os.path.join(run_dir, "results.md")).read()
        self.assertIn("revision task", res)
        self.assertIn("| generic | 2 | 3.00 (3 to 3) | 0/2 |", res)
        self.assertIn("| mechanical | 2 | 4.00 (4 to 4) | 0/2 | 2.0 | 0.0 | 1.0 | +1.00 |", res)
        self.assertIn("| judgment | 2 | 5.00 | 1/2 |", res, "the flagged repeat is excluded from the mean and counted")
        self.assertIn("| untouched | 2 | 2.00 (2 to 2) | 0/2 | 2.0 | 0.0 | 1.0 | -1.00 |", res)
        self.assertIn("**mechanical**: mean +1.00 over 1 writer(s)", res)

    def test_generic_arm_is_required(self):
        self._setup_writer()
        with self.assertRaises(SystemExit):
            self._run(["plan", "r2", "--task", "revise", "--brief", "weeding", "--writers", "brian",
                       "--arms", "untouched,mechanical"])

    def test_authoring_items_carry_provenance(self):
        self._setup_writer()
        self._run(["plan", "r3", "--brief", "weeding", "--writers", "brian", "--conditions", "correct,none"])
        self._run(["prompts", "r3", "--model", "m1"])
        m = json.load(open(os.path.join(study.RUNS, "r3", "manifest.json")))
        self.assertEqual(m["task"], "author")
        for it in m["items"]:
            self.assertEqual(it["model"], "m1")
            self.assertTrue(it["prompt_sha256"])
            self.assertIn("tool_version", it)


if __name__ == "__main__":
    unittest.main()
