#!/usr/bin/env python3
"""Tests for fingerprint.py. Run from anywhere: python3 /path/to/test_fingerprint.py"""
import json
import os
import random
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fingerprint  # noqa: E402
import samples  # noqa: E402

SHORT = ["The dog sat.", "It rained.", "We left early.", "Nobody spoke.", "The road was long.", "I counted three.",
         "She shrugged.", "He kept walking.", "The light went.", "So we waited."]
LONG = ["Because the committee had not yet decided whether the proposal would be funded in the current cycle, the team continued to draft the protocol as if it would be, which meant several long evenings of work for everyone on the team that spring.",
        "Although the results were preliminary and the sample was small, the reviewers were persuaded that the instrument measured what it claimed to measure, at least in the controlled setting described in the second section of the report.",
        "When the second cohort arrived, the onboarding material had been rewritten twice, and the parts that survived were the ones that students had actually asked questions about in the first year of the program, which nobody had predicted."]


def prose(sents, n_paras, per_para, seed):
    rng = random.Random(seed)
    return "\n\n".join(" ".join(rng.choice(sents) for _ in range(per_para)) for _ in range(n_paras)) + "\n"


class Units(unittest.TestCase):
    def test_prose_paragraphs_drop_markup_and_split_lists(self):
        text = "# Heading\n\nA **bold** claim with `code` and a [link](http://x).\n\n- first item\n- second item\n\n> quoted\n\n```\ncode\n```\n"
        paras = fingerprint.prose_paragraphs(text)
        self.assertEqual(paras, ["A bold claim with and a link.", "first item", "second item"])

    def test_features_count_shape_and_constructions(self):
        text = "The plan is simple. But it is not cheap, and it is not fast. Perhaps we try it anyway? We really should."
        fe = fingerprint.features([text])
        f = fe["f"]
        self.assertEqual(f["_sentences"], 4)
        self.assertGreater(f["con_initial_conjunction"], 0)
        self.assertGreater(f["con_hedge"], 0)
        self.assertGreater(f["con_intensifier"], 0)
        self.assertGreater(f["question_rate"], 0)
        self.assertGreater(f["punct_comma"], 0)
        self.assertEqual(f["punct_dash"], 0)
        self.assertIn("fw_the", f)
        self.assertEqual(fe["ev"]["sent_short_share"], ["We really should."])

    def test_chunks_keep_paragraphs_whole(self):
        paras = ["word " * 90] * 5
        runs = fingerprint.chunks(paras, size=200)
        self.assertEqual([len(r) for r in runs], [3, 2])


class BuildCompare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "samples")
        for i in range(4):
            p = os.path.join(self.tmp.name, f"s{i}.md")
            open(p, "w").write(prose(SHORT, 6, 12, i))
            samples.main(["add", p, "--dir", self.dir, "--provenance", "hand", "--surface", "note"])
        self.fp_path = os.path.join(self.tmp.name, "fp.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_records_samples_and_features(self):
        code = fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path])
        self.assertEqual(code, 0)
        fp = json.load(open(self.fp_path))
        self.assertEqual(len(fp["samples"]), 4)
        self.assertIn("note", fp["surfaces"])
        p = fp["pooled"]
        self.assertGreaterEqual(p["chunks"], 3)
        self.assertLess(p["features"]["sent_mean"]["mean"], 5)
        self.assertTrue(p["evidence"]["sent_short_share"][0]["samples"][0].startswith("note-"))
        self.assertIn("fw_the", p["features"])

    def test_approved_samples_are_not_built_from_by_default(self):
        p = os.path.join(self.tmp.name, "ai.md")
        open(p, "w").write(prose(LONG, 6, 6, 9))
        samples.main(["add", p, "--dir", self.dir, "--provenance", "approved", "--surface", "note"])
        fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path])
        fp = json.load(open(self.fp_path))
        self.assertEqual({s["provenance"] for s in fp["samples"]}, {"hand"})

    def test_compare_flags_long_sentences_against_a_short_sentence_author(self):
        fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path])
        fp = json.load(open(self.fp_path))
        same = fingerprint.compare(prose(SHORT, 5, 12, 99), fp)
        other = fingerprint.compare(prose(LONG, 5, 4, 99), fp)
        self.assertLess(same["shape_distance"], other["shape_distance"])
        flagged = {d["feature"]: d for d in other["flagged"]}
        self.assertIn("sent_mean", flagged)
        self.assertGreater(flagged["sent_mean"]["z"], 2)
        self.assertTrue(flagged["sent_long_share"]["quote"].startswith(("Because", "Although", "When")))
        self.assertTrue(flagged["sent_long_share"]["author_quote"])
        text = fingerprint.render(other, "x.md")
        self.assertIn("sent_mean", text)
        self.assertIn("more than the author", text)

    def test_too_few_chunks_is_an_error_not_a_profile(self):
        d = os.path.join(self.tmp.name, "tiny")
        p = os.path.join(self.tmp.name, "t.md")
        open(p, "w").write("One short note. Nothing more.\n")
        samples.main(["add", p, "--dir", d, "--provenance", "hand", "--surface", "note", "--min-words", "1"])
        with self.assertRaises(SystemExit):
            fingerprint.main(["build", "--samples", d, "--out", self.fp_path])


if __name__ == "__main__":
    unittest.main()
