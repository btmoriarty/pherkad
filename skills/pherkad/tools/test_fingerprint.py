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

    def test_reference_and_discriminant_take_sides(self):
        fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path])
        fp = json.load(open(self.fp_path))
        rdir = os.path.join(self.tmp.name, "ref")
        os.makedirs(rdir)
        for i in range(4):
            open(os.path.join(rdir, f"r{i}.md"), "w").write(prose(LONG, 6, 4, 50 + i))
        rp = os.path.join(self.tmp.name, "ref.json")
        self.assertEqual(fingerprint.main(["build-reference", rdir, "--out", rp, "--name", "long"]), 0)
        ref = json.load(open(rp))
        self.assertEqual(ref["name"], "long")
        self.assertIn("sent_mean", ref["features"])
        mine = fingerprint.compare(prose(SHORT, 5, 12, 99), fp, reference=ref)["discriminant"]
        theirs = fingerprint.compare(prose(LONG, 5, 4, 99), fp, reference=ref)["discriminant"]
        self.assertGreater(mine["score"], 0)
        self.assertLess(theirs["score"], 0)
        self.assertGreater(mine["features_used"], 5)
        self.assertEqual(mine["reference"], "long")
        self.assertIn("sent_short_share", theirs["for_reference"] + mine["for_author"])
        text = fingerprint.render(fingerprint.compare(prose(LONG, 5, 4, 99), fp, reference=ref), "x.md")
        self.assertIn("nearer the reference", text)

    def test_exclude_holds_samples_out(self):
        # a held-out piece with its own content: excluded by id, and nothing else goes with it
        p = os.path.join(self.tmp.name, "own.md")
        own = ("Quarterly harbour dredging resumed after the storm season, according to the port office. "
               "Two barges worked the eastern channel while a survey launch logged depths near the old ferry ramp. "
               "Fishermen moved their moorings twice. The council posted notices at the chandlery and the bakery. "
               "By October the channel held nine metres at low water, and the pilots stopped asking for escorts. ")
        open(p, "w").write((own * 2) + "\n")
        samples.main(["add", p, "--dir", self.dir, "--provenance", "hand", "--surface", "note"])
        fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path])
        fp = json.load(open(self.fp_path))
        own = next(s["id"] for s in fp["samples"] if s["words"] < 150)
        fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path, "--exclude", own])
        fp = json.load(open(self.fp_path))
        self.assertEqual(len(fp["samples"]), 4)
        self.assertEqual(fp["excluded"], [own])
        self.assertEqual(fp["excluded_near_duplicates"], [])

    def test_exclude_takes_near_duplicates_with_it(self):
        # these samples are shuffles of one sentence pool, so each carries the others' text (I159)
        fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path])
        ids = [s["id"] for s in json.load(open(self.fp_path))["samples"]]
        with self.assertRaises(SystemExit):
            fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path, "--exclude", ids[0]])

    def test_prose_is_a_view_of_the_numbers(self):
        fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path])
        fp = json.load(open(self.fp_path))
        text = fingerprint.prose(fp)
        p = fp["surfaces"]["note"]
        self.assertIn("## note", text)
        self.assertIn(f"{p['features']['sent_mean']['mean']:.1f} words on average", text)
        self.assertIn("(note-", text, "a quoted sentence carries its sample id")
        self.assertIn("Never in", text, "constructions that never occur are named as absent")
        self.assertIn("Most frequent first words", text)
        # evidence is credited to the sample that holds the sentence
        for e in p["evidence"]["sent_short_share"]:
            sid = e["samples"][0]
            path = next(s["file"] for s in json.load(open(os.path.join(self.dir, "samples.json")))["samples"] if s["id"] == sid)
            self.assertIn(e["quote"], open(os.path.join(self.dir, path)).read())
        rdir = os.path.join(self.tmp.name, "ref")
        os.makedirs(rdir)
        for i in range(4):
            open(os.path.join(rdir, f"r{i}.md"), "w").write(prose(LONG, 6, 4, 50 + i))
        rp = os.path.join(self.tmp.name, "ref.json")
        fingerprint.main(["build-reference", rdir, "--out", rp, "--name", "long"])
        out = os.path.join(self.tmp.name, "profile.md")
        self.assertEqual(fingerprint.main(["prose", self.fp_path, "--reference", rp, "--out", out]), 0)
        self.assertIn("Function words, against long", open(out).read())
        with self.assertRaises(SystemExit):
            fingerprint.main(["prose", self.fp_path, "--surface", "nope"])

    def test_too_few_chunks_is_an_error_not_a_profile(self):
        d = os.path.join(self.tmp.name, "tiny")
        p = os.path.join(self.tmp.name, "t.md")
        open(p, "w").write("One short note. Nothing more.\n")
        samples.main(["add", p, "--dir", d, "--provenance", "hand", "--surface", "note", "--min-words", "1"])
        with self.assertRaises(SystemExit):
            fingerprint.main(["build", "--samples", d, "--out", self.fp_path])


class Leakage(unittest.TestCase):
    """I158, I159, I160: the measure must not be scored against its own inputs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        p = os.path.join(self.d, name)
        with open(p, "w") as fh:
            fh.write(text)
        return p

    def test_a_reference_built_from_a_case_is_leakage(self):
        held = self.write("email-aaaa1111.md", "The shed leaked on Tuesday and forty bags were wet by noon.\n")
        flat = self.write("email-aaaa1111.2.md", "There was a leak in the shed and the bags got wet.\n")
        other = self.write("email-bbbb2222.md", "An unrelated note about the budget meeting next week.\n")
        body = " ".join(["The storage facility had not been inspected in several months, so the bags were damaged."] * 60)
        refsrc = [self.write(f"r{i}.md", body + "\n") for i in range(3)] + [flat]
        ref = fingerprint.build_reference(refsrc, "test")
        self.assertIn("email-aaaa1111", ref["stems"])
        problems = fingerprint.leakage([held, other], None, ref)
        self.assertEqual(len(problems), 1)
        self.assertIn("email-aaaa1111.md", problems[0])

    def test_a_case_that_is_a_fingerprint_sample_is_leakage(self):
        held = self.write("note-1.md", "Forty bags, all wet.\n")
        import hashlib
        fp = {"samples": [{"id": "note-1", "sha256": hashlib.sha256(b"Forty bags, all wet.\n").hexdigest()}]}
        self.assertTrue(fingerprint.leakage([held], fp, None))

    def test_near_duplicates_are_found_either_way_round(self):
        held = "The committee met on Tuesday and agreed to fund the pilot for one more term, with a review in March."
        reply = "Thanks. > The committee met on Tuesday and agreed to fund the pilot for one more term, with a review in March. Great news."
        unrelated = "The weather held for the whole trip and we saw the coast from the ridge at dawn on the third day."
        samples_ = [{"id": "reply", "text": reply}, {"id": "other", "text": unrelated}]
        self.assertEqual(fingerprint.near_duplicates(samples_, [held]), {"reply"})

    def test_shared_run_finds_a_quoted_sentence(self):
        profile = 'Exemplar: "the system architect, who worked through a bottle of wine while the three of us talked"'
        case = "Later the system architect, who worked through a bottle of wine while the three of us talked, left."
        self.assertTrue(fingerprint.shared_run(profile, case))
        self.assertEqual(fingerprint.shared_run(profile, "A different text entirely, about something else."), "")


if __name__ == "__main__":
    unittest.main()
