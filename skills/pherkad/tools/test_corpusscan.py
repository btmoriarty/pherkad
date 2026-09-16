#!/usr/bin/env python3
"""Tests for corpusscan. Dependency-free.

Run from anywhere:  python3 /path/to/test_corpusscan.py
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

import corpusscan  # noqa: E402

SCRIPT = os.path.join(HERE, "corpusscan.py")


def run(args, cwd=None):
    proc = subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, cwd=cwd)
    return proc.returncode, proc.stdout, proc.stderr


class Corpus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.d = d
        os.makedirs(os.path.join(d, "sub"))
        self.w("a.md", "This is a game-changer. That is the point of it.\n\nThe one that got out.\n")
        self.w("sub/b.md", "Plain prose about the weather, nothing to flag.\n\nThat is the point.\n")
        self.w("sub/00-rules.md", "This is a game-changer.\n")
        self.w("c.html", "<p>We shipped — then paused.</p>\n")
        self.w("d.py", "print('game-changer')\n")
        self.old = self.w("old.json", json.dumps({"soft_phrases": ["is the point", "the one that"], "banned_phrases": ["game-changer"]}))
        self.new = self.w("new.json", json.dumps({"soft_phrases": [{"id": "soft.point", "pattern": "is the point"}], "banned_phrases": ["game-changer"], "filler_words": ["plain"]}))

    def tearDown(self):
        self.tmp.cleanup()

    def w(self, name, text):
        p = os.path.join(self.d, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return p

    def test_collect_walks_default_extensions_and_excludes(self):
        files = corpusscan.collect_files([self.d])
        names = {os.path.relpath(f, self.d) for f in files}
        self.assertIn("a.md", names)
        self.assertIn("sub/b.md", names)
        self.assertIn("c.html", names)
        self.assertNotIn("d.py", names)
        files = corpusscan.collect_files([self.d], exclude=["[0-9][0-9]-*.md"])
        self.assertNotIn("sub/00-rules.md", {os.path.relpath(f, self.d) for f in files})
        files = corpusscan.collect_files([self.d], exts=(".md",))
        self.assertNotIn("c.html", {os.path.relpath(f, self.d) for f in files})

    def test_scan_counts_per_rule(self):
        code, out, _ = run(["scan", self.d, "--exclude", "[0-9][0-9]-*.md", "--json"])
        self.assertEqual(code, 0)
        s = json.loads(out)
        by = {r["rule_id"]: r for r in s["rules"]}
        self.assertEqual(by["soft.is-the-point"]["hits"], 2)
        self.assertEqual(by["soft.is-the-point"]["files"], 2)
        self.assertEqual(by["banned.game-changer"]["hits"], 1)
        self.assertEqual(s["files"], 3)
        self.assertGreater(s["words"], 0)
        self.assertIn("base_sha256", s)
        self.assertIn("tool_version", s)

    def test_scan_one_rule_with_contexts(self):
        code, out, _ = run(["scan", self.d, "--rule", "soft.is-the-point", "--contexts", "5", "--json"])
        s = json.loads(out)
        self.assertEqual([r["rule_id"] for r in s["rules"]], ["soft.is-the-point"])
        ctx = s["rules"][0]["contexts"]
        self.assertEqual(len(ctx), 2)
        self.assertTrue(all("[is the point]" in c["text"] for c in ctx))
        self.assertTrue(all(not c["file"].startswith("/") for c in ctx), "paths are relative to the corpus root")

    def test_scan_unknown_rule_reports_zero(self):
        code, out, _ = run(["scan", self.d, "--exclude", "[0-9][0-9]-*.md",
                            "--rule", "banned.game-changer", "--rule", "banned.make-no-mistake", "--json"])
        by = {r["rule_id"]: r["hits"] for r in json.loads(out)["rules"]}
        self.assertEqual(by, {"banned.game-changer": 1, "banned.make-no-mistake": 0})

    def test_candidate_rule(self):
        code, out, _ = run(["scan", self.d, "--candidate", "soft_phrases:got out", "--json"])
        self.assertEqual(code, 0)
        s = json.loads(out)
        self.assertEqual([(r["rule_id"], r["hits"]) for r in s["rules"]], [("soft.got-out", 1)])
        code, out, _ = run(["scan", self.d, "--candidate", '{"field":"filler_words","pattern":"weather","id":"filler.weather-probe"}', "--json"])
        self.assertEqual([(r["rule_id"], r["hits"]) for r in json.loads(out)["rules"]], [("filler.weather-probe", 1)])

    def test_candidate_that_already_exists_is_refused(self):
        code, _, err = run(["scan", self.d, "--candidate", "banned_phrases:game-changer"])
        self.assertEqual(code, 2)
        self.assertIn("already the rule banned.game-changer", err)

    def test_bad_candidate_exits_2(self):
        self.assertEqual(run(["scan", self.d, "--candidate", "nocolon"])[0], 2)
        self.assertEqual(run(["scan", self.d, "--candidate", "nosuchfield:x"])[0], 2)

    def test_diff_between_two_bases(self):
        code, out, _ = run(["diff", self.d, "--exclude", "[0-9][0-9]-*.md", "--ext", ".md",
                            "--old", self.old, "--new", self.new, "--json"])
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertEqual(d["rules_renamed"], {"soft.is-the-point": "soft.point"}, "same pattern, new id")
        self.assertIn("filler.plain", d["rules_added"])
        self.assertIn("soft.the-one-that", d["rules_removed"])
        by = {r["rule_id"]: r for r in d["rules"]}
        self.assertEqual((by["soft.the-one-that"]["old"], by["soft.the-one-that"]["new"]), (1, 0))
        self.assertEqual((by["filler.plain"]["old"], by["filler.plain"]["new"]), (0, 1))
        self.assertNotIn("soft.point", by, "a renamed rule with unchanged hits is not a change")
        self.assertEqual(d["appeared"], 1)
        self.assertEqual(d["vanished"], 1)

    def test_diff_with_overlay(self):
        ov = self.w("ov.json", json.dumps({"add_banned_phrases": ["weather"]}))
        code, out, _ = run(["diff", self.d, "--ext", ".md", "--old", self.old, "--new", self.new, "--config", ov, "--json"])
        d = json.loads(out)
        self.assertEqual(d["old"]["errors"], d["new"]["errors"], "the overlay applies to both sides")
        self.assertGreaterEqual(d["old"]["errors"], 2)

    def test_text_output_says_raw(self):
        code, out, _ = run(["scan", self.d])
        self.assertIn("Raw hits, not confirmed violations", out)
        code, out, _ = run(["diff", self.d, "--old", self.old, "--new", self.new])
        self.assertIn("Raw hits, not confirmed violations", out)

    def test_empty_corpus_exits_2(self):
        empty = os.path.join(self.d, "none")
        os.makedirs(empty)
        self.assertEqual(run(["scan", empty])[0], 2)


class LabelledCalibration(Corpus):
    def test_review_exports_hits_and_unflagged_units(self):
        self.w("long.md", ("A plain sentence about the weather with nothing to flag in it at all. " * 8) + "\n")
        out = os.path.join(self.d, "labels.jsonl")
        code, msg, err = run(["review", self.d, "--exclude", "[0-9][0-9]-*.md", "--surface", "post",
                              "--per-rule", "5", "--unflagged", "5", "--out", out])
        self.assertEqual(code, 0, err)
        rows = [json.loads(l) for l in open(out)]
        self.assertEqual(rows[0]["type"], "meta")
        self.assertEqual(rows[0]["surface"], "post")
        hits = [r for r in rows if r["type"] == "hit"]
        un = [r for r in rows if r["type"] == "unflagged"]
        self.assertTrue(any(r["rule_id"] == "banned.game-changer" for r in hits))
        self.assertTrue(all(r["label"] == "" for r in rows[1:]), "the tool never writes a label")
        self.assertTrue(all(k in hits[0] for k in ("path", "line", "source_hash", "span", "context")))
        self.assertEqual(len(un), 1, "the one long clean paragraph")
        self.assertTrue(un[0]["path"].endswith("long.md"))

    def test_score_review(self):
        out = os.path.join(self.d, "labels.jsonl")
        run(["review", self.d, "--surface", "post", "--per-rule", "5", "--unflagged", "5", "--out", out])
        rows = [json.loads(l) for l in open(out)]
        for r in rows:
            if r["type"] == "hit":
                r["label"] = "TP" if r["rule_id"] == "banned.game-changer" else "FP"
        with open(out, "w") as fh:
            fh.write("\n".join(json.dumps(r) for r in rows) + "\n")
        code, msg, _ = run(["score-review", out, "--json"])
        self.assertEqual(code, 0, msg)
        sc = json.loads(msg)
        by = {r["rule_id"]: r for r in sc["rules"]}
        self.assertEqual(by["banned.game-changer"]["precision"], 1.0)
        self.assertEqual(by["soft.is-the-point"]["precision"], 0.0)
        self.assertIsNotNone(by["soft.is-the-point"]["false_flags_per_1k"])
        self.assertEqual(sc["unlabelled"], {})
        code, msg, _ = run(["score-review", out])
        self.assertIn("banned.game-changer", msg)
        self.assertIn("1.00", msg)

    def test_unlabelled_and_misses_are_reported(self):
        out = os.path.join(self.d, "labels.jsonl")
        self.w("long.md", ("A plain sentence about the weather with nothing to flag in it at all. " * 8) + "\n")
        run(["review", self.d, "--surface", "post", "--out", out])
        rows = [json.loads(l) for l in open(out)]
        for r in rows:
            if r["type"] == "unflagged":
                r["label"] = "structure.staccato"
        with open(out, "w") as fh:
            fh.write("\n".join(json.dumps(r) for r in rows) + "\n")
        code, msg, _ = run(["score-review", out, "--json"])
        sc = json.loads(msg)
        self.assertEqual(sc["misses"], [{"surface": "post", "rule_id": "structure.staccato", "count": 1}])
        self.assertGreater(sc["unlabelled"]["hit"], 0)
        self.assertEqual(sc["rules"], [], "no labelled hit, no precision row")


if __name__ == "__main__":
    unittest.main()
