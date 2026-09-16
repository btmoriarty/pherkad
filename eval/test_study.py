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
        self.assertIn("| generic | 2 | 3.00 (3 to 3) | 0/2 | 3.00 |", res)
        self.assertIn("| mechanical | 2 | 4.00 (4 to 4) | 0/2 | 4.00 | 2.0 | 0.0 | 1.0 | +1.00 |", res)
        # judgment rated 5 and 5, one flagged: unflagged mean 5.00, penalised (5 + 1) / 2 = 3.00, so no lift
        self.assertIn("| judgment | 2 | 5.00 | 1/2 | 3.00 | 2.0 | 3.0 | 1.0 | +0.00 |", res,
                      "a flagged draft is scored 1 in the primary contrast")
        self.assertIn("| untouched | 2 | 2.00 (2 to 2) | 0/2 | 2.00 | 2.0 | 0.0 | 1.0 | -1.00 |", res)
        self.assertIn("**mechanical**: mean +1.00 over 1 writer(s)", res)
        self.assertIn("**judgment**: mean +0.00 over 1 writer(s)", res)

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


class RunItems(ReviseTask):
    """study.py run with a fake runner script: validation, retries, resume, status."""

    def _runner(self, body):
        p = os.path.join(self.tmp.name, "runner.py")
        with open(p, "w") as fh:
            fh.write(body)
        return f"{sys.executable} {p}"

    def _detect_run(self):
        DetectTask._setup_detect(self)
        self._run(["plan", "d1", "--task", "detect", "--writers", "brian,rosa", "--repeats", "1",
                   "--conditions", "correct,none"])
        self._run(["prompts", "d1"])
        return os.path.join(study.RUNS, "d1")

    def test_runs_validates_and_resumes(self):
        run_dir = self._detect_run()
        good = self._runner("import sys; p=sys.stdin.read(); print('Here you go: {\"rating\": 4, \"verdict\": \"PASS\", \"positive_register\": true, \"markers\": [\"m\"], \"evidence\": [\"e\"]}')")
        code, out = self._run(["run", "d1", "--runner", good, "--jobs", "3", "--model", "fake-1", "--dry-run"])
        self.assertIn("would run", out)
        code, out = self._run(["run", "d1", "--runner", good, "--jobs", "3", "--model", "fake-1", "--limit", "2"])
        self.assertEqual(code, 0, out)
        status = json.load(open(os.path.join(run_dir, "status.json")))
        self.assertEqual(sum(1 for v in status.values() if v["state"] == "done"), 2)
        code, out = self._run(["run", "d1", "--runner", good, "--jobs", "3", "--model", "fake-1"])
        self.assertEqual(code, 0, out)
        m = json.load(open(os.path.join(run_dir, "manifest.json")))
        judged = [it for it in m["items"] if it["condition"] != "linter"]
        self.assertTrue(all(os.path.exists(os.path.join(run_dir, it["verdict"])) for it in judged))
        self.assertTrue(all(it["model"] == "fake-1" for it in judged))
        v = json.load(open(os.path.join(run_dir, judged[0]["verdict"])))
        self.assertEqual(v["verdict"], "PASS", "only the JSON object is saved, not the chatter around it")
        st = status[judged[0]["blind_id"]]
        for k in ("reply_sha256", "prompt_sha256", "runner", "finished"):
            self.assertIn(k, st)
        code, out = self._run(["run", "d1", "--runner", good])
        self.assertIn("nothing to run", out)

    def test_invalid_replies_are_retried_then_failed(self):
        run_dir = self._detect_run()
        bad = self._runner("print('no json here at all')")
        code, out = self._run(["run", "d1", "--runner", bad, "--retries", "1", "--limit", "1"])
        self.assertEqual(code, 1)
        status = json.load(open(os.path.join(run_dir, "status.json")))
        st = list(status.values())[0]
        self.assertEqual((st["state"], st["attempts"]), ("failed", 2))
        self.assertIn("no JSON object", st["error"])
        # a failed item is not retried again without --force
        code, out = self._run(["run", "d1", "--runner", bad, "--retries", "1", "--limit", "1"])
        self.assertNotIn("attempts", out)
        good = self._runner("print('{\"rating\": 2, \"verdict\": \"REVISE\"}')")
        code, out = self._run(["run", "d1", "--runner", good, "--force", "--limit", "1"])
        self.assertEqual(code, 0, out)

    def test_bad_rating_is_invalid(self):
        self.assertFalse(study._validate_reply("detect", '{"rating": 9, "verdict": "PASS"}')[0])
        self.assertFalse(study._validate_reply("detect", '{"rating": 3, "verdict": "MAYBE"}')[0])
        self.assertTrue(study._validate_reply("detect", 'ok {"rating": 3, "verdict": "light REVISE"} done')[0])
        self.assertFalse(study._validate_reply("revise", "short")[0])

    def test_runner_failure_is_reported_not_hidden(self):
        self._detect_run()
        broken = self._runner("import sys; sys.exit(3)")
        code, out = self._run(["run", "d1", "--runner", broken, "--retries", "0", "--limit", "1"])
        self.assertEqual(code, 1)
        self.assertIn("runner exit 3", out)

    def test_plan_prompts_sheet_score(self):
        pass  # covered by DetectTask


class DetectTask(ReviseTask):
    """The detection experiment end to end with synthetic verdicts."""

    def _setup_detect(self):
        self._run(["add-writer", "brian"])
        self._run(["add-writer", "rosa"])
        w = os.path.join(study.WRITERS, "brian")
        with open(os.path.join(w, "profile.md"), "w") as fh:
            fh.write("# profile\n\n- marker one: short sentences\n- marker two: the shed\n- marker three: numbers\n")
        with open(os.path.join(study.WRITERS, "rosa", "profile.md"), "w") as fh:
            fh.write("# rosa\n\n- lush clauses\n")
        for d in ("holdout", "flattened", "impostors", "override"):
            os.makedirs(os.path.join(w, d), exist_ok=True)
        open(os.path.join(w, "holdout", "shed.md"), "w").write("The shed leaked. Forty bags, all wet.\n")
        open(os.path.join(w, "holdout", "atypical-poem.md"), "w").write("A poem, unusual for him.\n")
        open(os.path.join(w, "flattened", "shed.1.md"), "w").write("The storage shed had a leak, and the bags got wet.\n")
        open(os.path.join(w, "flattened", "shed.2.md"), "w").write("There was water damage to the stored bags. This is a game-changer.\n")
        open(os.path.join(w, "impostors", "rosa-shed.md"), "w").write("In the long light the shed gave up its water.\n")
        open(os.path.join(w, "override", "rhymes.md"), "w").write("Cat rhymes with hat, he said.\n")

    def test_plan_prompts_sheet_score(self):
        self._setup_detect()
        code, out = self._run(["plan", "d1", "--task", "detect", "--writers", "brian,rosa", "--repeats", "2"])
        self.assertEqual(code, 0, out)
        self.assertIn("missing: rosa: no authentic case", out)
        run_dir = os.path.join(study.RUNS, "d1")
        m = json.load(open(os.path.join(run_dir, "manifest.json")))
        self.assertEqual(m["task"], "detect")
        brian = [it for it in m["items"] if it["target"] == "brian"]
        # 6 cases x 5 conditions x 2 repeats
        self.assertEqual(len(brian), 6 * 5 * 2)
        self.assertEqual({it["case_type"] for it in brian}, {"authentic", "atypical", "flattened", "impostor", "override"})
        self.assertTrue(os.path.exists(os.path.join(run_dir, "profiles", "brian-shuffled.md")))
        self.assertIn("TODO", open(os.path.join(run_dir, "prereg.md")).read())
        wrong = [it for it in brian if it["condition"] == "wrong"][0]
        self.assertEqual(wrong["profile"], "rosa")

        code, out = self._run(["prompts", "d1", "--model", "judge-1"])
        self.assertEqual(code, 0, out)
        m = json.load(open(os.path.join(run_dir, "manifest.json")))
        brian = [it for it in m["items"] if it["target"] == "brian"]
        floor = [it for it in brian if it["condition"] == "linter"]
        self.assertTrue(all(os.path.exists(os.path.join(run_dir, it["verdict"])) for it in floor), "linter floor written")
        fl2 = [it for it in floor if it["case"] == "shed.2"][0]
        v = json.load(open(os.path.join(run_dir, fl2["verdict"])))
        self.assertEqual(v["verdict"], "REVISE", "a banned phrase makes the floor say REVISE")
        judged = [it for it in brian if it["condition"] != "linter"]
        self.assertTrue(all(it["model"] == "judge-1" and it.get("prompt_sha256") for it in judged))
        prompt = open(os.path.join(run_dir, "prompts", judged[0]["blind_id"] + ".txt")).read()
        self.assertIn("=== PASSAGE ===", prompt)
        self.assertIn('"rating"', prompt)

        # synthetic judge: the correct profile separates; the controls do not; one repeat wobbles
        def judge(it):
            ct, cond, rep = it["case_type"], it["condition"], it["repeat"]
            if cond == "correct":
                rating = {"authentic": 5, "atypical": 4, "override": 5, "flattened": 2, "impostor": 2}[ct]
                verdict = {5: "PASS", 4: "light REVISE", 2: "REVISE"}[rating]
                if ct == "impostor" and rep == 2:
                    rating, verdict = 4, "PASS"  # a severe wobble
                markers = ["marker one", "marker two"] if ct in ("authentic", "override") else ["marker one"]
            else:
                rating, verdict, markers = 3, "light REVISE", []
            return {"rating": rating, "verdict": verdict, "positive_register": ct != "flattened",
                    "markers": markers, "evidence": ["x"]}
        for it in judged:
            json.dump(judge(it), open(os.path.join(run_dir, it["verdict"]), "w"))

        code, out = self._run(["sheet", "d1"])
        self.assertEqual(code, 0, out)
        import csv
        pairs = list(csv.DictReader(open(os.path.join(run_dir, "pairs.csv"))))
        self.assertEqual(len(pairs), 2, "two flattenings of shed pair with the shed holdout")
        keyd = json.load(open(os.path.join(run_dir, "pairs-key.json")))
        labels = list(csv.DictReader(open(os.path.join(run_dir, "findings-labels.csv"))))
        self.assertTrue(any(r["rule_id"] == "soft.rhymes-with" for r in labels), "the override's finding is there to label")
        # the reader: right on pair 1, 'same' on pair 2; labels: rhymes-with is FP
        for r in pairs:
            r["pick"] = keyd[r["pair_id"]] if r["pair_id"] == pairs[0]["pair_id"] else "same"
        with open(os.path.join(run_dir, "pairs.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["pair_id", "writer", "pick"]); w.writeheader(); w.writerows(pairs)
        for r in labels:
            r["label"] = "FP" if r["rule_id"] == "soft.rhymes-with" else "TP"
        with open(os.path.join(run_dir, "findings-labels.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(labels[0].keys())); w.writeheader(); w.writerows(labels)

        code, out = self._run(["score", "d1"])
        self.assertEqual(code, 0, out)
        res = open(os.path.join(run_dir, "results.md")).read()
        self.assertIn("prereg.md still has TODO", res)
        self.assertIn("| correct | +3.00 |", res, "authentic 5 minus flattened 2 on the one usable pair")
        self.assertIn("| none | +0.00 |", res)
        self.assertIn("flattened +3.00", res, "lift over the flat controls")
        self.assertIn("authentic accepted", res)
        self.assertIn("exact 5/6, adjacent 0/6, severe 1/6", res, "the impostor wobble is severe movement")
        self.assertIn("told authentic from flattened on 1/1 decided pair(s); 1 pair(s) marked same", res)
        self.assertIn("| soft.rhymes-with | 0 | 1 | 0.00 |", res)
        self.assertIn("linter-only floor", res)

    def test_generic_arm_is_required(self):
        self._setup_writer()
        with self.assertRaises(SystemExit):
            self._run(["plan", "d2", "--task", "detect", "--writers", "brian", "--conditions", "wrong,none"])

    def test_authoring_items_carry_provenance(self):
        pass  # covered by ReviseTask


if __name__ == "__main__":
    unittest.main()
