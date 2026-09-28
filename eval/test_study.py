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

    # I174: annotated flags, flagged rows with no rating, repeats, and bad numbers
    def test_an_annotated_flag_is_still_a_flag(self):
        ratings, _ = study._read_ratings([row("item-a", "brian", "a", rating="4", flag="F: invented a date")])
        self.assertEqual(ratings, {"item-a": (4.0, "F")})

    def test_a_flag_that_is_not_f_stops_the_run(self):
        with self.assertRaises(SystemExit):
            study._read_ratings([row("item-a", "brian", "a", rating="4", flag="ok")])

    def test_a_flagged_row_with_no_rating_counts_as_a_failure(self):
        ratings, _ = study._read_ratings([row("item-a", "brian", "a", flag="F")])
        self.assertEqual(ratings, {"item-a": (1.0, "F")})

    def test_a_repeated_blind_id_stops_the_run(self):
        with self.assertRaises(SystemExit):
            study._read_ratings([row("item-a", "brian", "a", rating="4"), row(" item-a ", "brian", "b", rating="3")])

    def test_nan_and_negative_numbers_stop_the_run(self):
        with self.assertRaises(SystemExit):
            study._read_ratings([row("item-a", "brian", "a", rating="nan")])
        bad = dict(row("item-a", "brian", "a", rating="4"), minutes="-2")
        with self.assertRaises(SystemExit):
            study._read_ratings([bad])

    def test_both_carries_every_judgment_clause(self):
        # I170: the both arm is compared with the judgment arm, so it must read at least as much
        self.assertIn(study.JUDGMENT_CLAUSES, study.BOTH_REVIEW)
        self.assertIn(study.JUDGMENT_CLAUSES, study.JUDGMENT_REVIEW)
        self.assertIn("positive register", study.BOTH_REVIEW)


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
                with open(p, "w") as fh:  # generic writes the same text twice: rated once, scored for both (I156)
                    fh.write(f"Revised by {it['arm']}.\n" if it["arm"] == "generic" else f"Revised by {it['arm']}, pass {it['repeat']}.\n")
        code, out = self._run(["sheet", "r1"])
        self.assertEqual(code, 0, out)
        self.assertIn("revision task", open(os.path.join(run_dir, "rating-sheet.md")).read())
        import csv
        rows = list(csv.DictReader(open(os.path.join(run_dir, "ratings.csv"))))
        # the source once, generic's identical pair once, mechanical/judgment/both twice each (I156, I172)
        self.assertEqual(len(rows), 1 + 1 + 3 * 2)
        sheet_md = open(os.path.join(run_dir, "rating-sheet.md")).read()
        self.assertEqual(sheet_md.count("This is a game-changer. The honest answer is that it works."), 1)
        self.assertIn("The starting draft", sheet_md)
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
        self.assertIn("| mechanical | 2 | 4.00 (4 to 4) | 0/2 | 4.00 | 2.0 | 0.0 | 1.0 | 0/2 | +1.00 |", res)
        # judgment rated 5 and 5, one flagged: unflagged mean 5.00, penalised (5 + 1) / 2 = 3.00, so no lift
        self.assertIn("| judgment | 2 | 5.00 | 1/2 | 3.00 | 2.0 | 3.0 | 1.0 | 0/2 | +0.00 |", res,
                      "a flagged draft is scored 1 in the primary contrast")
        self.assertIn("| untouched | 2 | 2.00 (2 to 2) | 0/2 | 2.00 | 2.0 | 0.0 | 1.0 | 2/2 | -1.00 |", res,
                      "the untouched arm is the source itself, unchanged 2/2 (I171)")
        self.assertIn("**mechanical**: mean +1.00 over 1 writer(s)", res)
        self.assertIn("**judgment**: mean +0.00 over 1 writer(s)", res)
        self.assertIn("writers: brian (n=2)", res, "each pooled comparison names its writers (I177)")
        with self.assertRaises(SystemExit):
            self._run(["sheet", "r1"])  # the ratings are filled; regenerating would blank them (I147)

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

    def _runner(self, body, canary="NONE", name="runner.py"):
        # an isolated runner answers the canary question NONE (tools/runner.py);
        # the body then reads the prompt from stdin as before
        head = ("import io, sys as _s\n_p = _s.stdin.read()\n"
                f"if 'reply with exactly the word NONE' in _p:\n    print({canary!r}); _s.exit(0)\n"
                "_s.stdin = io.StringIO(_p)\n")
        p = os.path.join(self.tmp.name, name)
        with open(p, "w") as fh:
            fh.write(head + body)
        return f"{sys.executable} {p}"

    def test_a_runner_that_is_not_isolated_is_refused(self):
        # I019, I020: a runner carrying the operator's profile contaminates every control arm
        self._detect_run()
        leaky = self._runner("raise SystemExit('the prompt must never be sent')",
                             canary="PRESENT: memory entries on the author's voice")
        with self.assertRaises(SystemExit) as cm:
            self._run(["run", "d1", "--runner", leaky, "--limit", "1"])
        self.assertIn("not isolated", str(cm.exception))
        run_dir = os.path.join(study.RUNS, "d1")
        self.assertFalse(os.path.exists(os.path.join(run_dir, "status.json")), "nothing was sent")
        self.assertFalse(json.load(open(os.path.join(run_dir, "canary.json")))["isolated"])

    def test_the_model_recorded_is_the_one_the_runner_reports(self):
        # I026: the operator's --model is a label; the runner's own report is the record
        self._detect_run()
        good = self._runner("import sys; sys.stdin.read(); "
                            "sys.stderr.write('runner-meta: {\"models\": [\"real-model-7\"], \"cli\": \"x 1.0\"}\\n'); "
                            "print('{\"rating\": 4, \"verdict\": \"PASS\", \"evidence\": [\"e\"]}')")
        self._run(["run", "d1", "--runner", good, "--model", "what-i-typed", "--limit", "1"])
        st = next(v for v in json.load(open(os.path.join(study.RUNS, "d1", "status.json"))).values())
        self.assertEqual(st["model"], "real-model-7")
        self.assertEqual(st["label"], "what-i-typed")
        self.assertEqual(st["cli"], "x 1.0")

    def test_a_reply_written_before_an_interruption_is_adopted(self):
        # I024: a finished reply whose status entry was never written is kept, not re-sent
        self._detect_run()
        run_dir = os.path.join(study.RUNS, "d1")
        manifest = json.load(open(os.path.join(run_dir, "manifest.json")))
        it = next(i for i in manifest["items"] if os.path.exists(os.path.join(run_dir, "prompts", i["blind_id"] + ".txt")))
        study._write(os.path.join(run_dir, it["verdict"]), '{"rating": 4, "verdict": "PASS", "evidence": ["e"]}\n')
        never = self._runner("raise SystemExit(9)")
        code, out = self._run(["run", "d1", "--runner", never, "--dry-run"])
        self.assertIn("adopted 1 reply file", out)
        self.assertEqual(json.load(open(os.path.join(run_dir, "status.json")))[it["blind_id"]]["state"], "done")

    def _detect_run(self):
        DetectTask._setup_detect(self)
        self._run(["plan", "d1", "--task", "detect", "--writers", "brian,rosa", "--repeats", "1",
                   "--conditions", "correct,none"])
        DetectTask._freeze(self, "d1")
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
        # the typed --model is a label; the model is what the runner reports, and this fake reports none (I026)
        self.assertTrue(all(it["model"] == "unreported" and it["model_label"] == "fake-1" for it in judged))
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
        good = self._runner("print('{\"rating\": 2, \"verdict\": \"REVISE\", \"evidence\": [\"e\"]}')")
        code, out = self._run(["run", "d1", "--runner", good, "--force", "--limit", "1"])
        self.assertEqual(code, 0, out)

    def test_bad_rating_is_invalid(self):
        self.assertFalse(study._validate_reply("detect", '{"rating": 9, "verdict": "PASS"}')[0])
        self.assertFalse(study._validate_reply("detect", '{"rating": 3, "verdict": "MAYBE"}')[0])
        self.assertTrue(study._validate_reply("detect", 'ok {"rating": 3, "verdict": "light REVISE", "evidence": ["x"]} done')[0])
        self.assertFalse(study._validate_reply("revise", "short")[0])

    def test_contradictory_verdicts_are_invalid(self):
        # detect-01 produced PASS/1 and PASS with no evidence; both are now retried, not scored
        ok, why = study._validate_reply("detect", '{"rating": 1, "verdict": "PASS", "evidence": ["x"]}')
        self.assertFalse(ok); self.assertIn("disagree", why)
        ok, why = study._validate_reply("detect", '{"rating": 4, "verdict": "REWRITE", "evidence": ["x"]}')
        self.assertFalse(ok); self.assertIn("disagree", why)
        ok, why = study._validate_reply("detect", '{"rating": 4, "verdict": "PASS", "evidence": []}')
        self.assertFalse(ok); self.assertIn("no quoted evidence", why)
        self.assertTrue(study._validate_reply("detect", '{"rating": 2, "verdict": "REWRITE", "evidence": ["it"]}')[0])

    def test_runner_failure_is_reported_not_hidden(self):
        self._detect_run()
        broken = self._runner("import sys; sys.exit(3)")
        code, out = self._run(["run", "d1", "--runner", broken, "--retries", "0", "--limit", "1"])
        self.assertEqual(code, 1)
        self.assertIn("runner exit 3", out)

    def test_flatten_writes_k_per_holdout_within_length_band(self):
        self._setup_writer()
        hold = os.path.join(study.WRITERS, "brian", "holdout")
        os.makedirs(hold, exist_ok=True)
        src = " ".join(f"word{i}" for i in range(100)) + "\n"
        with open(os.path.join(hold, "piece.md"), "w") as fh:
            fh.write(src)
        # echoes the text section back: same length, so inside the band; the prompt never carries the profile
        echo = self._runner("import sys; p=sys.stdin.read(); assert 'marker one' not in p; print(p.split('=== TEXT ===')[1])")
        code, out = self._run(["flatten", "brian", "--runner", echo, "--k", "2", "--model", "fam-b", "--dry-run"])
        self.assertIn("2 flattening(s) would be written", out)
        code, out = self._run(["flatten", "brian", "--runner", echo, "--k", "2", "--model", "fam-b"])
        self.assertEqual(code, 0, out)
        fl = os.path.join(study.WRITERS, "brian", "flattened")
        self.assertEqual(sorted(os.listdir(fl)), ["piece.1.md", "piece.1.meta.json", "piece.2.md", "piece.2.meta.json"])
        meta = json.load(open(os.path.join(fl, "piece.2.meta.json")))
        self.assertEqual((meta["k"], meta["model"], meta["label"], meta["source_words"]), (2, "unreported", "fam-b", 100))
        code, out = self._run(["flatten", "brian", "--runner", echo])
        self.assertIn("nothing to flatten", out)
        short = self._runner("print('too short')")
        code, out = self._run(["flatten", "brian", "--runner", short, "--k", "3", "--retries", "0"])
        self.assertEqual(code, 1)
        self.assertIn("outside the 10 percent band", out)
        self.assertFalse(os.path.exists(os.path.join(fl, "piece.3.md")))

    def test_plan_prompts_sheet_score(self):
        pass  # covered by DetectTask


class AuthorScore(ReviseTask):
    """The author task's scorer, end to end (I178): two writers, distinct control
    means, a flagged correct draft, and a forced-choice pick."""

    def test_lift_penalises_flags_and_reports_each_control(self):
        self._setup_writer()
        self._run(["add-writer", "rosa"])
        open(os.path.join(study.WRITERS, "rosa", "profile.md"), "w").write("# rosa\n\nLong clauses.\n")
        code, out = self._run(["plan", "a1", "--brief", "weeding", "--writers", "brian,rosa"])
        self.assertEqual(code, 0, out)
        run_dir = os.path.join(study.RUNS, "a1")
        m = json.load(open(os.path.join(run_dir, "manifest.json")))
        for it in m["items"]:
            open(os.path.join(run_dir, it["draft"]), "w").write(f"Draft {it['blind_id']}.\n")
        code, out = self._run(["sheet", "a1"])
        self.assertEqual(code, 0, out)
        import csv
        rows = list(csv.DictReader(open(os.path.join(run_dir, "ratings.csv"))))
        key = {it["blind_id"]: it for it in m["items"]}
        # brian: correct 5 but flagged (so it counts 1), wrong 3, none 2; rosa: correct 4, wrong 2, none 3
        table = {("brian", "correct"): ("5", "F"), ("brian", "wrong"): ("3", ""), ("brian", "none"): ("2", ""),
                 ("rosa", "correct"): ("4", ""), ("rosa", "wrong"): ("2", ""), ("rosa", "none"): ("3", "")}
        for r in rows:
            it = key[r["blind_id"]]
            r["rating"], r["fidelity_flag"] = table[(it["target"], it["condition"])]
            if it["target"] == "rosa" and it["condition"] == "correct":
                r["forced_choice_pick"] = r["candidate"]
        with open(os.path.join(run_dir, "ratings.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
        code, out = self._run(["score", "a1"])
        self.assertEqual(code, 0, out)
        res = open(os.path.join(run_dir, "results.md")).read()
        # brian: the flagged correct counts 1, so lift = 1 - (3 + 2) / 2 = -1.50
        self.assertIn("**brian**: correct=1.00 (unflagged", res)
        self.assertIn("lift = -1.50", res, "a flagged draft does not carry its rating into the lift (I175)")
        # rosa: 4 - (2 + 3) / 2 = +1.50
        self.assertIn("lift = +1.50", res)
        self.assertIn("mean +0.00 across 2 writer(s), range -1.50 to +1.50", res)
        self.assertIn("Picked the correct-profile draft on 1/1", res)


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

    def test_fingerprint_condition_writes_floor_verdicts(self):
        import random
        sys.path.insert(0, study.TOOLS)
        import fingerprint
        import samples
        self._setup_detect()
        sdir = os.path.join(self.tmp.name, "fsamples")
        rng = random.Random(1)
        short = ["The shed leaked.", "Forty bags.", "All wet.", "Nobody came.", "We counted.", "It rained."]
        for i in range(4):
            p = os.path.join(self.tmp.name, f"m{i}.md")
            open(p, "w").write("\n\n".join(" ".join(rng.choice(short) for _ in range(14)) for _ in range(5)) + "\n")
            samples.main(["add", p, "--dir", sdir, "--provenance", "hand", "--surface", "email"])
        fpp = os.path.join(self.tmp.name, "fp.json")
        fingerprint.main(["build", "--samples", sdir, "--out", fpp])
        rdir = os.path.join(self.tmp.name, "refs")
        os.makedirs(rdir)
        long = "Because the storage facility had not been inspected in several months, the bags stored inside were found to be damaged by water when the team arrived. "
        for i in range(4):
            open(os.path.join(rdir, f"r{i}.md"), "w").write((long * 8 + "\n\n") * 3)
        rp = os.path.join(self.tmp.name, "ref.json")
        fingerprint.main(["build-reference", rdir, "--out", rp, "--name", "generic"])
        code, out = self._run(["plan", "d2", "--task", "detect", "--writers", "brian", "--repeats", "1",
                               "--conditions", "correct,linter,fingerprint"])
        self.assertEqual(code, 0, out)
        self._freeze("d2")
        with self.assertRaises(SystemExit):
            self._run(["prompts", "d2"])  # the condition needs the two profiles
        code, out = self._run(["prompts", "d2", "--fingerprint", fpp, "--reference", rp])
        self.assertEqual(code, 0, out)
        run_dir = os.path.join(study.RUNS, "d2")
        m = json.load(open(os.path.join(run_dir, "manifest.json")))
        fps = [it for it in m["items"] if it["condition"] == "fingerprint"]
        self.assertTrue(fps)
        for it in fps:
            v = json.load(open(os.path.join(run_dir, it["verdict"])))
            self.assertTrue(v["fingerprint_only"])
            self.assertIn(v["verdict"], ("PASS", "light REVISE", "REVISE", "REWRITE"))
            self.assertEqual(it["model"], "none (fingerprint floor)")
            self.assertTrue(it["fingerprint_sha256"])
        # the score never asks a model for these; score runs with only the floors filled
        for it in m["items"]:
            if it["condition"] == "correct":
                open(os.path.join(run_dir, it["verdict"]), "w").write('{"rating": 4, "verdict": "PASS", "evidence": ["x"]}')
        code, out = self._run(["score", "d2"])
        self.assertEqual(code, 0, out)
        self.assertIn("floor: fingerprint margin", open(os.path.join(run_dir, "results.md")).read())

    def _freeze(self, run):
        # a complete prereg, then frozen: prompts, run, and score need both (I163)
        p = os.path.join(study.RUNS, run, "prereg.md")
        text = open(p).read().replace("TODO", "set for the test")
        open(p, "w").write(text)
        code, out = self._run(["freeze", run])
        self.assertEqual(code, 0, out)

    def test_plan_prompts_sheet_score(self):
        self._setup_detect()
        code, out = self._run(["plan", "d1", "--task", "detect", "--writers", "brian,rosa", "--repeats", "2"])
        self.assertEqual(code, 0, out)
        self.assertIn("missing: rosa: no authentic case", out)
        run_dir = os.path.join(study.RUNS, "d1")
        m = json.load(open(os.path.join(run_dir, "manifest.json")))
        self.assertEqual(m["task"], "detect")
        brian = [it for it in m["items"] if it["target"] == "brian"]
        self.assertEqual(len(brian), 6 * 5 * 2)  # 6 cases x 5 conditions x 2 repeats
        self.assertEqual({it["case_type"] for it in brian}, {"authentic", "atypical", "flattened", "impostor", "override"})
        shuffled = open(os.path.join(run_dir, "profiles", "brian-shuffled.md")).read()
        self.assertTrue(shuffled.startswith("# Voice profile\n"), "the shuffled control is not labelled a control (I161)")
        wrong = [it for it in brian if it["condition"] == "wrong"][0]
        self.assertEqual(wrong["profile"], "rosa")
        self.assertEqual(wrong["profile_sha256"], study._profile_sha("rosa"), "the hash of the profile actually used (I162)")
        self.assertEqual([it for it in brian if it["condition"] == "none"][0]["profile_sha256"], "")
        self.assertEqual(len({it["blind_id"] for it in m["items"]}), len(m["items"]))

        with self.assertRaises(SystemExit) as cm:
            self._run(["prompts", "d1", "--model", "judge-1"])
        self.assertIn("TODO", str(cm.exception), "nothing is collected before the plan is complete and frozen")
        self._freeze("d1")
        code, out = self._run(["prompts", "d1", "--model", "judge-1"])
        self.assertEqual(code, 0, out)
        m = json.load(open(os.path.join(run_dir, "manifest.json")))
        brian = [it for it in m["items"] if it["target"] == "brian"]
        floor = [it for it in brian if it["condition"] == "linter"]
        self.assertTrue(all(os.path.exists(os.path.join(run_dir, it["verdict"])) for it in floor), "linter floor written")
        fl2 = [it for it in floor if it["case"] == "shed.2"][0]
        self.assertEqual(json.load(open(os.path.join(run_dir, fl2["verdict"])))["verdict"], "REVISE")
        judged = [it for it in brian if it["condition"] != "linter"]

        # a synthetic judge with asymmetric controls (I178): wrong discriminates a little,
        # shuffled and none accept everything and so are degenerate (I165)
        table = {
            "correct":  {"authentic": 5, "atypical": 4, "override": 5, "flattened": 2, "impostor": 2},
            "wrong":    {"authentic": 4, "atypical": 4, "override": 4, "flattened": 2, "impostor": 3},
            "shuffled": {"authentic": 4, "atypical": 4, "override": 4, "flattened": 3, "impostor": 3},
            "none":     {"authentic": 3, "atypical": 3, "override": 3, "flattened": 3, "impostor": 3},
        }
        verdict_for = {5: "PASS", 4: "PASS", 3: "light REVISE", 2: "REVISE"}

        def judge(it):
            rating = table[it["condition"]][it["case_type"]]
            if it["condition"] == "correct" and it["case_type"] == "impostor" and it["repeat"] == 2:
                rating = 4  # a severe wobble
            markers = ["marker one", "marker two"] if it["case_type"] in ("authentic", "override") else ["marker one"]
            return {"rating": rating, "verdict": verdict_for[rating], "positive_register": True,
                    "markers": markers, "evidence": ["x"]}
        for it in judged:
            json.dump(judge(it), open(os.path.join(run_dir, it["verdict"]), "w"))
        # a stale verdict the current validator rejects is dropped and counted (I022)
        stale = [it for it in brian if it["condition"] == "none" and it["case_type"] == "override"][0]
        open(os.path.join(run_dir, stale["verdict"]), "w").write('{"rating": 3, "verdict": "light REVISE"}')

        code, out = self._run(["sheet", "d1"])
        self.assertEqual(code, 0, out)
        import csv
        pairs = list(csv.DictReader(open(os.path.join(run_dir, "pairs.csv"))))
        self.assertEqual(len(pairs), 2, "two flattenings of shed pair with the shed holdout")
        self.assertEqual({p["sheet"] for p in pairs}, {"1", "2"}, "one sheet per flattening round (I156)")
        for k in (1, 2):
            text = open(os.path.join(run_dir, f"pairs-sheet-{k}.md")).read()
            self.assertEqual(text.count("The shed leaked. Forty bags, all wet."), 1, "the authentic text appears once per sheet")
        keyd = json.load(open(os.path.join(run_dir, "pairs-key.json")))
        labels = list(csv.DictReader(open(os.path.join(run_dir, "findings-labels.csv"))))
        self.assertTrue(any(r["rule_id"] == "soft.rhymes-with" for r in labels))
        for r in pairs:  # the reader: right on the first pair, 'same' on the second
            r["pick"] = keyd[r["pair_id"]]["authentic_is"] if r is pairs[0] else "same"
        with open(os.path.join(run_dir, "pairs.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["pair_id", "sheet", "writer", "pick"]); w.writeheader(); w.writerows(pairs)
        for r in labels:
            r["label"] = "FP" if r["rule_id"] == "soft.rhymes-with" else "TP"
        with open(os.path.join(run_dir, "findings-labels.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(labels[0].keys())); w.writeheader(); w.writerows(labels)
        with self.assertRaises(SystemExit):
            self._run(["sheet", "d1"])  # regenerating would blank the reader's answers (I147)

        code, out = self._run(["score", "d1"])
        self.assertEqual(code, 0, out)
        res = open(os.path.join(run_dir, "results.md")).read()
        self.assertNotIn("EXPLORATORY", res)
        self.assertIn("| none | 2/2 | 2/2 | 4/4 | 2/2 | 1/2 | 1 |", res, "planned versus scored, the stale verdict dropped")
        self.assertIn("| correct | +3.00 |", res, "authentic 5 minus flattened 2 on the one usable pair")
        self.assertIn("| shuffled (degenerate) |", res)
        self.assertIn("| none (degenerate) |", res)
        self.assertIn("| wrong | +1.00", res, "correct minus wrong, paired by case")
        self.assertIn("| shuffled (degenerate: not pooled) | +2.00", res)
        self.assertIn("authentic versus flattened: mean +1.00 over 1 writer(s)", res,
                      "pooled over wrong only; the old mean of all three controls said +2.00")
        self.assertIn("atypical accepted", res)
        self.assertIn("exact 4/5, adjacent 0/5, severe 1/5", res, "the excluded pair is out of stability too")
        self.assertIn("2 pair(s) read: 1 marked same and 0 where the reader heard the flattening", res)
        self.assertIn("| correct | 1/1 |", res)
        self.assertIn("| none | 0/1 |", res, "none rates both 3: no preference, so it disagrees with the reader")
        self.assertIn("| soft.rhymes-with | 0 | 1 | 0.00 |", res)
        self.assertIn("floor: linter margin", res)

        # a reader who hears the flattening as the writer: that pair leaves the model's scores (I164)
        for r in pairs:
            key = keyd[r["pair_id"]]["authentic_is"]
            r["pick"] = ("B" if key == "A" else "A") if r is pairs[0] else "same"
        with open(os.path.join(run_dir, "pairs.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["pair_id", "sheet", "writer", "pick"]); w.writeheader(); w.writerows(pairs)
        self._run(["score", "d1"])
        res = open(os.path.join(run_dir, "results.md")).read()
        self.assertIn("| correct | n/a |", res, "no flattened pair is left to score")
        self.assertIn("1 where the reader heard the flattening as the writer", res)
        # a pick that is not A, B, or same stops the score (I166)
        pairs[0]["pick"] = "maybe"
        with open(os.path.join(run_dir, "pairs.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["pair_id", "sheet", "writer", "pick"]); w.writeheader(); w.writerows(pairs)
        with self.assertRaises(SystemExit):
            self._run(["score", "d1"])

    def test_generic_arm_is_required(self):
        self._setup_writer()
        with self.assertRaises(SystemExit):
            self._run(["plan", "d2", "--task", "detect", "--writers", "brian", "--conditions", "wrong,none"])

    def test_authoring_items_carry_provenance(self):
        pass  # covered by ReviseTask


if __name__ == "__main__":
    unittest.main()
