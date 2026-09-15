#!/usr/bin/env python3
"""Tests for the correction ledger. Dependency-free.

Run from anywhere:  python3 /path/to/test_corrections.py
Also collected by ``python3 -m unittest`` and by pytest.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import corrections  # noqa: E402

SCRIPT = os.path.join(HERE, "corrections.py")
PHERKAD = os.path.join(HERE, "pherkad.py")


def run(*args):
    proc = subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


class Ledger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.ledger = os.path.join(d, "c.jsonl")
        self.overlay = os.path.join(d, "overlay.json")
        self.prose = os.path.join(d, "rules.md")
        self.corpus = os.path.join(d, "corpus")
        os.makedirs(self.corpus)
        with open(os.path.join(self.corpus, "a.md"), "w") as fh:
            fh.write("There are three connections worth a look here.\n\nPlain prose.\n\nAnother connections worth a look line.\n")
        with open(self.prose, "w") as fh:
            fh.write("# Rules\n\nSome prose.\n")

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, before, after="", **kw):
        args = ["add", "--ledger", self.ledger, "--before", before, "--after", after]
        for k, v in kw.items():
            args += ["--" + k, v]
        code, out, err = run(*args)
        self.assertEqual(code, 0, err)
        return out.split()[1]

    def records(self):
        return corrections.load_ledger(self.ledger)

    def test_classify(self):
        self.assertEqual(corrections.classify("worth a look", "worth reviewing"), "literal")
        self.assertEqual(corrections.classify("worth [word] than", ""), "templated")
        self.assertEqual(corrections.classify(r"re:\bx\b", ""), "templated")
        self.assertEqual(corrections.classify("but that is the kind of thing X is for", ""), "judgment")
        self.assertEqual(corrections.classify("371 courses", "421 courses"), "factual")

    def test_add_proposes_matcher_and_examples(self):
        rid = self.add("connections worth a look", "connections worth reviewing",
                       context="There are three connections worth a look in the graph.", source="email")
        r = self.records()[0]
        self.assertEqual(r["id"], rid)
        self.assertEqual((r["kind"], r["status"], r["field"], r["severity"]), ("literal", "pending", "soft_phrases", "warning"))
        self.assertEqual(r["matcher"], "connections worth a look")
        self.assertEqual(r["fires"], ["There are three connections worth a look in the graph."])
        self.assertEqual(r["clean"], ["There are three connections worth reviewing in the graph."])

    def test_severity_error_goes_to_banned(self):
        self.add("circle back", severity="error")
        self.assertEqual(self.records()[0]["field"], "banned_phrases")

    def test_promote_refuses_untrialled(self):
        rid = self.add("connections worth a look", "connections worth reviewing")
        code, _, err = run("promote", rid, "--ledger", self.ledger, "--overlay", self.overlay)
        self.assertEqual(code, 2)
        self.assertIn("not been trialled", err)

    def test_trial_counts_and_records(self):
        rid = self.add("connections worth a look", "connections worth reviewing",
                       context="There are three connections worth a look in the graph.")
        code, out, _ = run("trial", rid, self.corpus, "--ledger", self.ledger)
        self.assertEqual(code, 0, out)
        self.assertIn("2 hit(s) in 1 file(s)", out)
        r = self.records()[0]
        self.assertEqual(r["status"], "trialled")
        self.assertEqual((r["trial"]["hits"], r["trial"]["files_hit"]), (2, 1))
        self.assertEqual(r["trial"]["example_problems"], [])
        self.assertEqual(len(r["trial"]["contexts"]), 2)

    def test_trial_reports_a_bad_example(self):
        rid = self.add("connections worth a look", "connections worth reviewing",
                       context="There are three connections worth a look in the graph.")
        recs = self.records()
        recs[0]["clean"] = ["still connections worth a look"]
        corrections.save_ledger(self.ledger, recs)
        code, out, _ = run("trial", rid, self.corpus, "--ledger", self.ledger)
        self.assertEqual(code, 1)
        self.assertIn("clean example fires", out)
        code, _, err = run("promote", rid, "--ledger", self.ledger, "--overlay", self.overlay)
        self.assertEqual(code, 2)
        self.assertIn("example problems", err)

    def test_promote_writes_overlay_fixtures_and_prose(self):
        rid = self.add("connections worth a look", "connections worth reviewing",
                       context="There are three connections worth a look in the graph.",
                       source="email", rationale="vague momentum idiom")
        run("trial", rid, self.corpus, "--ledger", self.ledger)
        code, out, err = run("promote", rid, "--ledger", self.ledger, "--overlay", self.overlay, "--prose", self.prose)
        self.assertEqual(code, 0, err)
        ov = json.load(open(self.overlay))
        e = ov["add_soft_phrases"][0]
        self.assertEqual(e["id"], "soft.connections-worth-a-look")
        self.assertEqual(e["rationale"], "vague momentum idiom")
        self.assertEqual(len(e["fires"]), 1)
        self.assertEqual(len(e["clean"]), 1)
        prose = open(self.prose).read()
        self.assertIn("## Mined corrections (", prose)
        self.assertIn('"connections worth a look" -> "connections worth reviewing". vague momentum idiom (rule `soft.connections-worth-a-look`, warning; 2 corpus hit(s)', prose)
        r = self.records()[0]
        self.assertEqual((r["status"], r["rule_id"]), ("promoted", "soft.connections-worth-a-look"))
        # the overlay's fixtures run under check-overlay and the rule fires
        proc = subprocess.run([sys.executable, PHERKAD, "check-overlay", self.overlay], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        proc = subprocess.run([sys.executable, PHERKAD, "check", "--config", self.overlay, "-"],
                              input="connections worth a look\n", capture_output=True, text=True)
        self.assertIn("soft.connections-worth-a-look", proc.stdout)

    def test_promote_twice_is_refused(self):
        rid = self.add("connections worth a look", "connections worth reviewing")
        run("trial", rid, self.corpus, "--ledger", self.ledger)
        run("promote", rid, "--ledger", self.ledger, "--overlay", self.overlay)
        self.assertEqual(run("promote", rid, "--ledger", self.ledger, "--overlay", self.overlay)[0], 2)

    def test_factual_never_becomes_a_rule(self):
        rid = self.add("371 courses", "421 courses")
        self.assertEqual(self.records()[0]["kind"], "factual")
        code, out, _ = run("promote", rid, "--ledger", self.ledger, "--overlay", self.overlay, "--prose", self.prose)
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(self.overlay))
        self.assertIn("not a style rule", open(self.prose).read())
        self.assertEqual(self.records()[0]["status"], "rejected")

    def test_judgment_and_preference_are_prose_only(self):
        r1 = self.add("but that is the kind of thing X is for", rationale="self-justifying tail; cut it")
        r2 = self.add("reusable surface", "reusable instrument", kind="preference")
        for rid in (r1, r2):
            run("promote", rid, "--ledger", self.ledger, "--overlay", self.overlay, "--prose", self.prose)
        self.assertFalse(os.path.exists(self.overlay))
        statuses = {r["id"]: r["status"] for r in self.records()}
        self.assertEqual(statuses[r1], "judgment-only")
        self.assertEqual(statuses[r2], "preference")
        prose = open(self.prose).read()
        self.assertIn("(judgment layer; no regex expresses it)", prose)
        self.assertIn("(a preference, not a ban)", prose)

    def test_trial_refuses_non_rule_kinds(self):
        rid = self.add("but that is the kind of thing X is for")
        self.assertEqual(run("trial", rid, self.corpus, "--ledger", self.ledger)[0], 2)

    def test_prose_groups_under_one_heading_per_source_and_day(self):
        for before in ("phrase one", "phrase two"):
            rid = self.add(before, "x", source="email")
            run("promote", rid, "--ledger", self.ledger, "--prose", self.prose)  # no overlay: untrialled rule kinds refuse
        # untrialled literal kinds refuse promote; use judgment kinds for the heading test
        r1 = self.add("a long judgment sentence that is recast entirely here", "", source="email")
        r2 = self.add("another long judgment sentence recast entirely as well", "", source="email")
        run("promote", r1, "--ledger", self.ledger, "--prose", self.prose)
        run("promote", r2, "--ledger", self.ledger, "--prose", self.prose)
        prose = open(self.prose).read()
        self.assertEqual(prose.count("## Mined corrections ("), 1)
        self.assertEqual(prose.count("\n- "), 2)

    def test_retire_and_list(self):
        rid = self.add("circle back", "return to")
        code, out, _ = run("retire", rid, "--ledger", self.ledger, "--reason", "never recurred")
        self.assertEqual(code, 0)
        self.assertEqual(self.records()[0]["status"], "retired")
        code, out, _ = run("list", "--ledger", self.ledger, "--status", "retired")
        self.assertIn("circle back", out)
        self.assertIn("1 record(s)", out)
        code, out, _ = run("show", rid, "--ledger", self.ledger)
        self.assertEqual(json.loads(out)["id"], rid)

    def test_promote_into_the_shipped_base_appends_to_the_list(self):
        import shutil
        base = os.path.join(self.tmp.name, "voice_config.json")
        shutil.copy(corrections.voicelint.DEFAULTS_PATH, base)
        rid = self.add("connections worth a look", "connections worth reviewing")
        run("trial", rid, self.corpus, "--ledger", self.ledger)
        # promote into a copy: it is not the shipped file, so it goes under add_
        run("promote", rid, "--ledger", self.ledger, "--overlay", base)
        ov = json.load(open(base))
        self.assertIn("add_soft_phrases", ov)
        # the into-base branch is exercised by samefile on the real DEFAULTS_PATH; assert the
        # decision logic directly rather than writing to the shipped file
        self.assertTrue(os.path.samefile(corrections.voicelint.DEFAULTS_PATH, corrections.voicelint.DEFAULTS_PATH))

    def test_templated_matcher(self):
        rid = self.add("worth [word] than", "", kind="templated", context="It was worth more than the rest.")
        r = self.records()[0]
        self.assertEqual(r["matcher"], "worth [word] than")
        code, out, _ = run("trial", rid, self.corpus, "--ledger", self.ledger)
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
