#!/usr/bin/env python3
"""Tests for fingerprint.py. Run from anywhere: python3 /path/to/test_fingerprint.py"""
import json
import math
import os
import random
import statistics
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

    def test_curly_quotes_count_as_straight_and_evidence_keeps_them(self):
        """I119: a mail client's curly apostrophes and quotes are counted, and quoted as written."""
        straight = fingerprint.features(["I don't think it's done. She said \"wait\" and we'll see."])
        curly = fingerprint.features(["I don’t think it’s done. She said “wait” and we’ll see."])
        for k in ("con_contraction", "punct_quote", "open_first_person", "fw_i", "_sentences"):
            self.assertEqual(curly["f"][k], straight["f"][k], k)
        self.assertGreater(curly["f"]["con_contraction"], 0)
        self.assertIn("’", curly["ev"]["con_contraction"][0])
        # a sentence opening on a curly quote still splits off
        self.assertEqual(fingerprint.features(["It ended. “Go,” he said."])["f"]["_sentences"], 2)
        self.assertEqual(fingerprint.containment("we don’t know what it’s for", "we don't know what it's for"), 1.0)

    def test_abbreviations_do_not_split_a_measured_sentence(self):
        """I080 in the measured profile: fingerprint and corrections share structlint's guards."""
        import corrections
        f = fingerprint.features(["Dr. Smith met Mr. Jones at No. 5 Main St. Downtown. They talked."])["f"]
        self.assertEqual(f["_sentences"], 2)
        self.assertEqual(corrections._sentences("Dr. Smith left. Then we went."), ["Dr. Smith left.", "Then we went."])

    def test_quartiles_stay_inside_the_observed_lengths(self):
        """statistics.quantiles' default (exclusive) method put Q1 of a 5- and a
        30-word sentence at -1.25 words; the inclusive method interpolates."""
        f = fingerprint.features(["One two three four five. Then " + " ".join(["word"] * 28) + " end."])["f"]
        self.assertEqual(f["_sentences"], 2)
        self.assertEqual((f["sent_q1"], f["sent_median"], f["sent_q3"]), (11.25, 17.5, 23.75))

    def test_chunks_keep_paragraphs_whole(self):
        paras = ["word " * 90] * 5
        runs = fingerprint.chunks(paras, size=200)
        self.assertEqual([len(r) for r in runs], [3, 2])


class BuildCompare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "samples")
        for i in range(60):
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
        self.assertEqual(len(fp["samples"]), 60)
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
        self.assertFalse(fp["allow_approved"])

    def test_approved_is_refused_unless_allowed_and_then_recorded(self):
        """I149: asking for approved text is an error without --allow-approved."""
        p = os.path.join(self.tmp.name, "ai.md")
        open(p, "w").write(prose(LONG, 6, 6, 9))
        samples.main(["add", p, "--dir", self.dir, "--provenance", "approved", "--surface", "note"])
        for prov in ("hand,approved", "hand,typo"):
            with self.assertRaises(SystemExit) as cm:
                fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path, "--provenance", prov])
            self.assertEqual(cm.exception.code, 2)
        self.assertFalse(os.path.exists(self.fp_path))
        fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path, "--provenance", "hand,approved", "--allow-approved"])
        fp = json.load(open(self.fp_path))
        self.assertTrue(fp["allow_approved"])
        self.assertIn("approved", {s["provenance"] for s in fp["samples"]})

    def test_an_unknown_exclude_id_is_an_error(self):
        """I149: a mistyped held-out id would hold nothing out."""
        with self.assertRaises(SystemExit) as cm:
            fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path, "--exclude", "note-00000000"])
        self.assertEqual(cm.exception.code, 2)
        self.assertFalse(os.path.exists(self.fp_path))

    def test_compare_flags_long_sentences_against_a_short_sentence_author(self):
        fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path])
        fp = json.load(open(self.fp_path))
        same = fingerprint.compare(prose(SHORT, 5, 12, 99), fp)
        other = fingerprint.compare(prose(LONG, 5, 4, 99), fp)
        self.assertLess(same["shape_distance"], other["shape_distance"])
        self.assertEqual(same["flagged"], [], "the author's own kind of text flags no family")
        # one flag per family: sentence length is one property, not five deviations (I187)
        fams = {d["family"]: d for d in other["flagged"]}
        self.assertEqual(len(fams), len(other["flagged"]))
        lead = fams["sentence length"]
        self.assertIn("sent_mean", [lead["feature"]] + lead["also"])
        self.assertGreater(lead["z"], 2)
        self.assertLess(lead["p_family"], 0.05)
        self.assertTrue(lead["quote"])
        self.assertTrue(lead["author_quote"])
        # each text is compared at the available size nearest its length (I188)
        prof = {"scales": {"100": {}, "200": {}, "800": {}}}
        self.assertEqual([fingerprint._scale_for(prof, w)[0] for w in (120, 300, 600, 5000)], [100, 200, 800, 800])
        self.assertEqual(same["scale"], 200)
        text = fingerprint.render(other, "x.md")
        self.assertIn("sentence length", text)
        self.assertIn("more than the author", text)

    def test_spread_is_the_sample_sd_and_never_zero(self):
        """I189: sample SD, floored at one occurrence, and a t with n - 1 df."""
        fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path])
        fp = json.load(open(self.fp_path))
        sc = fp["pooled"]["scales"]["200"]
        self.assertGreaterEqual(sc["n"], fingerprint.MIN_CHUNKS)
        # the SHORT pool never hedges: sd 0 in the profile, yet one hedge is not a certain deviation
        self.assertEqual(sc["features"]["con_hedge"]["sd"], 0.0)
        res = fingerprint.compare(prose(SHORT, 5, 12, 99) + "\nPerhaps it rained.\n", fp)
        hedge = [d for d in res["flagged"] if d["feature"] == "con_hedge" or "con_hedge" in d["also"]]
        self.assertEqual(hedge, [])
        with self.assertRaises(ValueError):
            fingerprint.compare("x", fp, fdr=2.0)  # a caller still passing the old 2.0 threshold fails loudly
        short = fingerprint.compare("The dog sat. It rained.", fp)
        self.assertIn("at least", short["error"])

    def test_a_surface_without_a_profile_says_so(self):
        """I192: no silent fallback to the pooled profile."""
        fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path])
        fp = json.load(open(self.fp_path))
        res = fingerprint.compare(prose(SHORT, 5, 12, 99), fp, surface="paper")
        self.assertEqual(res["basis"], "pooled")
        self.assertIn("no paper profile", res["basis_note"])
        self.assertIn("note 100%", res["basis_note"])
        self.assertNotIn("basis_note", fingerprint.compare(prose(SHORT, 5, 12, 99), fp, surface="note"))

    def test_every_measured_number_has_a_passage(self):
        """I037: each shape feature the author shows is quoted, and so is each flagged family and function word."""
        fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path])
        fp = json.load(open(self.fp_path))
        p = fp["pooled"]
        for k, st in p["features"].items():
            if st["mean"] > 0 and not k.startswith("fw_"):
                self.assertTrue(p["evidence"].get(k), f"{k} has no passage")
        self.assertTrue(p["evidence"].get("fw_the"))
        res = fingerprint.compare(prose(LONG, 5, 4, 99), fp)
        self.assertTrue(res["flagged"])
        for d in res["flagged"] + res["function_words_flagged"]:
            # a word the text never uses has no passage in the text; the author's use of it stands for the gap
            self.assertTrue(d["quote"] or (d["z"] < 0 and d["author_quote"]), d["feature"])

    def test_type_token_is_steady_with_length(self):
        """I188: the plain ratio fell with length; the moving average does not."""
        rng = random.Random(3)
        vocab = [f"w{i}" for i in range(300)]
        ws = [rng.choice(vocab) for _ in range(2000)]
        self.assertAlmostEqual(fingerprint._mattr(ws[:200]), fingerprint._mattr(ws), delta=0.03)
        self.assertLess(len(set(ws)) / len(ws), len(set(ws[:200])) / 200 - 0.2)

    def test_function_words_are_closed_class(self):
        """I191: no content words in the list."""
        for w in ("word", "people", "water", "animal", "picture", "sentence", "very", "really"):
            self.assertNotIn(w, fingerprint.FUNCTION_WORDS)
        for w in ("the", "of", "and", "would", "whom", "although"):
            self.assertIn(w, fingerprint.FUNCTION_WORDS)

    def test_reference_and_discriminant_take_sides(self):
        fingerprint.main(["build", "--samples", self.dir, "--out", self.fp_path])
        fp = json.load(open(self.fp_path))
        rdir = os.path.join(self.tmp.name, "ref")
        os.makedirs(rdir)
        for i in range(4):
            open(os.path.join(rdir, f"r{i}.md"), "w").write(prose(LONG, 6, 4, 50 + i))
        rp = os.path.join(self.tmp.name, "ref.json")
        self.assertEqual(fingerprint.main(["build-reference", rdir, "--out", rp, "--name", "long"]), 0)
        small = json.load(open(rp))
        # I190: a reference under MIN_REFERENCE_CHUNKS is refused, with the reason, not fit on
        d = fingerprint.compare(prose(SHORT, 5, 12, 99), fp, reference=small)["discriminant"]
        self.assertIsNone(d["score"])
        self.assertIn("needs 50", d["error"])
        self.assertIn("not computed", fingerprint.render(fingerprint.compare(prose(SHORT, 5, 12, 99), fp, reference=small)))
        for i in range(4, 30):
            open(os.path.join(rdir, f"r{i}.md"), "w").write(prose(LONG, 6, 4, 50 + i))
        self.assertEqual(fingerprint.main(["build-reference", rdir, "--out", rp, "--name", "long"]), 0)
        ref = json.load(open(rp))
        self.assertEqual(ref["name"], "long")
        self.assertIn("sent_mean", ref["features"])
        self.assertEqual(len(ref["vectors"]["rows"]), ref["chunks"])
        self.assertGreaterEqual(ref["chunks"], fingerprint.MIN_REFERENCE_CHUNKS)
        mine = fingerprint.compare(prose(SHORT, 5, 12, 99), fp, reference=ref)["discriminant"]
        theirs = fingerprint.compare(prose(LONG, 5, 4, 99), fp, reference=ref)["discriminant"]
        self.assertGreater(mine["score"], 0)
        self.assertLess(theirs["score"], 0)
        self.assertGreater(mine["p_author"], 0.5)
        self.assertGreater(mine["cv_auc"], 0.9, "two pools this different separate under cross-validation")
        self.assertGreater(mine["features_used"], 0)
        self.assertEqual(mine["reference"], "long")
        text = fingerprint.render(fingerprint.compare(prose(LONG, 5, 4, 99), fp, reference=ref), "x.md")
        self.assertIn("nearer the reference", text)
        self.assertIn("cross-validated AUC", text)

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
        self.assertEqual(len(fp["samples"]), 60)
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
        self.assertIn("averaged over every 50-word window", text, "the ratio is a moving average, not one chunk's")
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
        refsrc = [self.write(f"r{i}.md", body + "\n") for i in range(5)] + [flat]
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


def _pool(rng, prefix, docs, per_doc, shift=0.0, p=12):
    """Synthetic chunk vectors: a document-level effect under piece-level noise."""
    groups, rows = [], []
    for d in range(docs):
        eff = [rng.gauss(0, 0.5) for _ in range(p)]
        for _ in range(per_doc):
            groups.append(f"{prefix}{d}")
            rows.append([shift + eff[j] + rng.gauss(0, 1) for j in range(p)])
    return {"vectors": {"keys": [f"k{j}" for j in range(p)], "groups": groups, "rows": rows}}


class DiscriminantCache(unittest.TestCase):
    def setUp(self):
        fingerprint._MODELS.clear()

    def test_a_profile_built_in_a_loop_gets_its_own_model(self):
        """Review finding 1: the cache was keyed on id(), which CPython reuses once
        a dict is freed, so profiles built in a loop got a stale, sign-flipped model."""
        for seed in range(20):
            rng = random.Random(seed)
            a = _pool(rng, "a", 15, 2, shift=1.0 if seed % 2 else -1.0)
            r = _pool(rng, "r", 30, 1)
            got = fingerprint.fit_discriminant(a, r, min_reference_chunks=10)
            want = fingerprint._fit(a["vectors"], r["vectors"])
            self.assertEqual(got["active"], want["active"], f"seed {seed}")
            del a, r, got

    def test_equal_content_shares_a_model_and_the_cache_is_bounded(self):
        rng = random.Random(7)
        a, r = _pool(rng, "a", 15, 2, shift=1.0), _pool(rng, "r", 30, 1)
        first = fingerprint.fit_discriminant(a, r, min_reference_chunks=10)
        copy = json.loads(json.dumps(a))
        self.assertTrue(fingerprint.fit_discriminant(copy, r, min_reference_chunks=10) is first)
        for seed in range(fingerprint.MAX_MODELS + 3):
            fingerprint.fit_discriminant(_pool(random.Random(seed), "a", 8, 2), r, min_reference_chunks=10)
        self.assertLessEqual(len(fingerprint._MODELS), fingerprint.MAX_MODELS)


class NestedCrossValidation(unittest.TestCase):
    def test_the_reported_auc_never_sees_the_fold_that_chose_the_shrinkage(self):
        """Review finding 3: the shrinkage behind each outer fold's scores is chosen
        by an inner cross-validation on the other folds only, and the deployed
        model's shrinkage by a cross-validation on everything."""
        rng = random.Random(3)
        a, r = _pool(rng, "a", 20, 2), _pool(rng, "r", 40, 1)
        calls, real = [], fingerprint._tune

        def spy(rows, ys, folds, idx):
            calls.append(frozenset(folds[i] for i in idx))
            return real(rows, ys, folds, idx)

        fingerprint._tune = spy
        try:
            model = fingerprint._fit(a["vectors"], r["vectors"])
        finally:
            fingerprint._tune = real
        everything = frozenset(range(fingerprint.FOLDS))
        self.assertEqual(calls[0], everything)
        self.assertEqual(sorted(everything - c for c in calls[1:]), [frozenset([f]) for f in range(fingerprint.FOLDS)])
        self.assertEqual(model["cv"], "nested")
        self.assertTrue(0.0 <= model["cv_auc"] <= 1.0)


class Statistics(unittest.TestCase):
    """The measured profile's statistical pieces, each against a hand-worked
    case or an independent computation (review finding 5)."""

    def test_auc_is_mann_whitney_with_ties_shared(self):
        self.assertEqual(fingerprint._auc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]), 0.75)
        self.assertEqual(fingerprint._auc([1, 2, 3, 4], [0, 0, 1, 1]), 1.0)
        self.assertEqual(fingerprint._auc([4, 3, 2, 1], [0, 0, 1, 1]), 0.0)
        self.assertEqual(fingerprint._auc([1, 1, 2], [0, 1, 1]), 0.75)  # a tie counts half
        self.assertEqual(fingerprint._auc([5, 5, 5, 5], [0, 1, 0, 1]), 0.5)
        self.assertEqual(fingerprint._auc([1, 2], [1, 1]), 0.5)  # one class: no ranking to score

    def test_bh_is_the_step_up_procedure(self):
        # thresholds at q = 0.05, m = 4: 0.0125, 0.025, 0.0375, 0.05
        self.assertEqual(fingerprint._bh([0.01, 0.04, 0.03, 0.2], 0.05), ({0}, 0.01))
        # step-up: ranks 1 and 2 miss their thresholds, rank 4 meets its own, so all four go
        self.assertEqual(fingerprint._bh([0.04, 0.02, 0.035, 0.03], 0.05), ({0, 1, 2, 3}, 0.04))
        self.assertEqual(fingerprint._bh([0.5, 0.9], 0.05), (set(), 0.0))
        self.assertEqual(fingerprint._bh([], 0.05), (set(), 0.0))

    def test_conformal_p_counts_the_pieces_at_least_as_extreme(self):
        null = [1.0, 2.0, 3.0, 4.0]
        self.assertEqual(fingerprint._conformal_p(5.0, null), 1 / 5)
        self.assertEqual(fingerprint._conformal_p(3.0, null), 3 / 5)  # 3 and 4 tie or beat it
        self.assertEqual(fingerprint._conformal_p(2.9996, null), 3 / 5)  # rounded as the null was
        self.assertEqual(fingerprint._conformal_p(0.0, null), 1.0)

    def test_null_is_the_leave_one_out_family_maximum(self):
        rng = random.Random(11)
        per = [{"sent_mean": rng.gauss(18, 4), "sent_sd": rng.expovariate(1 / 8), "para_sents": rng.choice([1, 2, 3, 4, 6])}
               for _ in range(12)]
        sc = {"n": 12, "words": 200, "sentences": 10, "paragraphs": 3, "features": fingerprint._stats(per)}
        got = fingerprint._null(per, sc)
        want = {"sentence length": [], "paragraphs": []}
        for i, f in enumerate(per):
            rest = per[:i] + per[i + 1:]
            for fam, keys in (("sentence length", ("sent_mean", "sent_sd")), ("paragraphs", ("para_sents",))):
                ts = [abs(fingerprint._t(f[k], statistics.fmean(r[k] for r in rest), statistics.stdev([r[k] for r in rest]),
                                         fingerprint._sd_floor(k, sc), len(rest))) for k in keys]
                want[fam].append(round(max(ts), 3))
        self.assertEqual(set(got), set(want))
        for fam in want:
            for g, w in zip(got[fam], sorted(want[fam])):
                self.assertAlmostEqual(g, w, places=3, msg=fam)

    def test_platt_recovers_a_known_log_odds_and_stays_finite_when_separated(self):
        # scores N(+1, 1) for the author and N(-1, 1) for the reference: the true log-odds is 2 * score
        rng = random.Random(5)
        scores = [rng.gauss(1, 1) for _ in range(3000)] + [rng.gauss(-1, 1) for _ in range(3000)]
        ys = [1] * 3000 + [0] * 3000
        a, b = fingerprint._platt(scores, ys)
        self.assertAlmostEqual(a, 2.0, delta=0.15)
        self.assertAlmostEqual(b, 0.0, delta=0.1)
        a, b = fingerprint._platt([-2.0, -1.0, 1.0, 2.0], [0, 0, 1, 1])
        self.assertTrue(math.isfinite(a) and math.isfinite(b) and a > 0)

    def test_nsc_fit_matches_a_hand_worked_case(self):
        # one feature, 0 2 | 4 6: z = (x - 3) / sqrt(5), centroids -+2/sqrt(5), pooled
        # within-class sd sqrt(0.4), s0 the same, m = sqrt(1/2 - 1/4) = 0.5, so d = +-sqrt(2)
        fit = fingerprint._nsc_fit([[0.0, 7.0], [2.0, 7.0], [4.0, 7.0], [6.0, 7.0]], [0, 0, 1, 1])
        self.assertAlmostEqual(fit["mu"][0], 3.0)
        self.assertAlmostEqual(fit["sig"][0], math.sqrt(5))
        self.assertAlmostEqual(fit["sk"][0], 2 * math.sqrt(0.4))
        self.assertAlmostEqual(fit["m"][1], 0.5)
        self.assertAlmostEqual(fit["d"][1][0], math.sqrt(2))
        self.assertAlmostEqual(fit["d"][0][0], -math.sqrt(2))
        self.assertEqual((fit["d"][0][1], fit["d"][1][1]), (0.0, 0.0))  # a constant feature carries nothing
        self.assertAlmostEqual(fit["dmax"], math.sqrt(2))
        # no shrinkage keeps the live feature only; shrinkage to dmax keeps none
        self.assertEqual([j for j, _, _ in fingerprint._nsc_shrink(fit, 0.0)], [0])
        self.assertEqual(fingerprint._nsc_shrink(fit, fit["dmax"]), [])
        # the author's side scores positive, the reference's negative
        active = fingerprint._nsc_shrink(fit, 0.0)
        self.assertGreater(sum(t for t, _ in fingerprint._nsc_terms(fit, active, [6.0, 7.0])), 0)
        self.assertLess(sum(t for t, _ in fingerprint._nsc_terms(fit, active, [0.0, 7.0])), 0)

    def test_the_authors_own_pieces_are_flagged_near_the_nominal_rate(self):
        """A new piece from the author's own distribution is flagged (any family
        surviving BH at 5%) at or a little under 5% of the time (2.9% here, since
        rank p-values and discrete features are conservative), with skewed and discrete
        features and a per-document shift, the way compare() tests a text. With
        five families a rank among n pieces can only reach p <= 0.01 once n >= 99
        (compare's resolution_note), so the profiles here have 200 pieces."""
        rng = random.Random(2026)

        def piece(doc):
            return {"sent_mean": doc + rng.gauss(18, 4), "sent_sd": rng.expovariate(1 / 8),
                    "para_sents": float(rng.choice([1, 1, 2, 3, 3, 4, 6])),
                    "punct_colon": sum(rng.random() < 0.05 for _ in range(10)) / 10.0,
                    "punct_comma": rng.gammavariate(2, 0.6), "con_hedge": 5.0 * sum(rng.random() < 0.3 for _ in range(4)),
                    "fw_the": rng.gauss(55, 12)}

        trials = flagged = 0
        for _ in range(30):
            per = [piece(rng.gauss(0, 2)) for _ in range(200)]
            sc = {"n": len(per), "words": 200, "sentences": 10, "paragraphs": 3, "features": fingerprint._stats(per)}
            null = fingerprint._null(per, sc)
            for _ in range(40):
                new = piece(rng.gauss(0, 2))
                fams = {}
                for k, st in sc["features"].items():
                    t = fingerprint._t(new[k], st["mean"], st["sd"], fingerprint._sd_floor(k, sc), sc["n"])
                    fams.setdefault(fingerprint.family(k), []).append(abs(t))
                ps = [fingerprint._conformal_p(max(ts), null[name]) for name, ts in fams.items()]
                hit, _ = fingerprint._bh(ps, 0.05)
                trials += 1
                flagged += bool(hit)
        rate = flagged / trials
        self.assertLessEqual(rate, 0.07, f"{flagged} of {trials} of the author's own pieces flagged")
        self.assertGreaterEqual(rate, 0.02, f"{flagged} of {trials}: far below nominal, the test has lost its power")


if __name__ == "__main__":
    unittest.main()
