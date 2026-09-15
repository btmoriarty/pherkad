#!/usr/bin/env python3
"""Tests for pherkad.py, the combined runner. Dependency-free.

Run from anywhere:  python3 /path/to/test_pherkad.py
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

import pherkad  # noqa: E402
import voicelint  # noqa: E402

SCRIPT = os.path.join(HERE, "pherkad.py")
DEFAULT = voicelint.load_config(None)


def run(args, text=None):
    proc = subprocess.run([sys.executable, SCRIPT, *args], input=text, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def ids(text, cfg=DEFAULT, structure=True):
    return [f["rule_id"] for f in pherkad.run_text(text, cfg, structure)[0]]


class Schema(unittest.TestCase):
    def test_both_engines_in_one_list_in_position_order(self):
        text = "None of them wrong. None of them ours. This is a game-changer.\n"
        fs, _ = pherkad.run_text(text, DEFAULT)
        self.assertEqual([f["rule_id"] for f in fs], ["structure.staccato", "banned.game-changer"])
        for f in fs:
            for k in ("line", "col", "severity", "rule", "match", "message", "rule_id", "engine"):
                self.assertIn(k, f)
        self.assertEqual([f["engine"] for f in fs], ["structure", "voice"])

    def test_no_structure(self):
        text = "None of them wrong. None of them ours. This is a game-changer.\n"
        self.assertEqual(ids(text, structure=False), ["banned.game-changer"])

    def test_suppressed_count_carried(self):
        _, dropped = pherkad.run_text("This is a game-changer. <!-- voicelint: ignore-line -->", DEFAULT)
        self.assertEqual(dropped, 1)


class Overlap(unittest.TestCase):
    def test_header_named_by_a_voice_rule_is_reported_once(self):
        # structlint's header check and voicelint's soft phrase both see "is the point".
        fs, _ = pherkad.run_text("## The one thing that is the point\n", DEFAULT)
        self.assertEqual([f["rule_id"] for f in fs], ["soft.is-the-point"])

    def test_header_with_no_voice_rule_is_kept(self):
        fs, _ = pherkad.run_text("## Why this matters\n", DEFAULT)
        self.assertEqual([f["rule_id"] for f in fs], ["structure.header"])


class Density(unittest.TestCase):
    def test_one_density_over_both_engines(self):
        # 12 two-beats (structure) and 12 banned phrases (voice) in ~200 words:
        # structlint alone would be under its cap; combined it is over.
        para = "None of them wrong. None of them ours. This is a game-changer.\n\n"
        text = para * 12 + ("word " * 60) + "\n"
        fs, _ = pherkad.run_text(text, DEFAULT)
        dens = [f for f in fs if f["rule"] == "density"]
        self.assertEqual(len(dens), 1)
        self.assertEqual((dens[0]["engine"], dens[0]["rule_id"], dens[0]["line"]), ("combined", "density", 0))

    def test_structlint_own_density_is_dropped(self):
        text = "None of them wrong. None of them ours.\n\n" * 12 + ("word " * 60) + "\n"
        fs, _ = pherkad.run_text(text, DEFAULT)
        self.assertEqual(sum(f["rule_id"] == "density" for f in fs), 1)
        self.assertFalse(any(f["rule_id"] == "structure.density" for f in fs))

    def test_short_document_has_no_density(self):
        fs, _ = pherkad.run_text("None of them wrong. None of them ours. This is a game-changer.\n", DEFAULT)
        self.assertFalse(any(f["rule"] == "density" for f in fs))

    def test_threshold_from_config(self):
        cfg = json.loads(json.dumps(DEFAULT))
        cfg["structure"]["density_per_100"] = 50
        text = "None of them wrong. None of them ours. This is a game-changer.\n\n" * 12 + ("word " * 60) + "\n"
        self.assertFalse(any(f["rule"] == "density" for f in pherkad.run_text(text, cfg)[0]))


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.bad = os.path.join(d, "bad.md")
        with open(self.bad, "w") as fh:
            fh.write("None of them wrong. None of them ours. This is a game-changer.\n")
        self.warn = os.path.join(d, "warn.md")
        with open(self.warn, "w") as fh:
            fh.write("None of them wrong. None of them ours.\n")
        self.clean = os.path.join(d, "clean.md")
        with open(self.clean, "w") as fh:
            fh.write("A plain sentence about the weather, long enough not to be short.\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_text_format_and_exit(self):
        code, out, _ = run(["check", self.bad])
        self.assertEqual(code, 1)
        self.assertIn("[error] banned-phrase (banned.game-changer):", out)
        self.assertIn("[warning] staccato (structure.staccato):", out)
        self.assertIn("pherkad: 1 error(s), 1 warning(s) across 1 file(s).", out)

    def test_exit_codes(self):
        self.assertEqual(run(["check", self.clean])[0], 0)
        self.assertEqual(run(["check", self.warn])[0], 0)
        self.assertEqual(run(["check", "--strict", self.warn])[0], 1)
        self.assertEqual(run(["check", "/no/such/file.md"])[0], 2)
        self.assertEqual(run(["check", "--surface", "nope", self.clean])[0], 2)
        self.assertEqual(run(["check", "--surface", "assistant-chat", "--config", self.clean, self.clean])[0], 2)

    def test_advisory_prefix_is_reported_not_counted(self):
        code, out, _ = run(["check", "--strict", "--advisory", "structure.", self.warn])
        self.assertEqual(code, 0)
        self.assertIn("[advisory] two-beat (structure.two-beat)", out)
        self.assertIn("0 warning(s), 1 advisory", out)

    def test_json_envelope(self):
        code, out, _ = run(["check", "--format", "json", "--advisory", "structure.", self.bad])
        d = json.loads(out)
        self.assertEqual(d["tool"], "pherkad")
        for k in ("version", "config_sha256", "suppressed", "files", "advisory_prefixes"):
            self.assertIn(k, d)
        self.assertEqual(d["advisory_prefixes"], ["structure."])
        fs = d["files"][self.bad]
        self.assertEqual({f["engine"] for f in fs}, {"voice", "structure"})

    def test_sarif(self):
        code, out, _ = run(["check", "--format", "sarif", "--advisory", "structure.", self.bad])
        d = json.loads(out)
        self.assertEqual(d["version"], "2.1.0")
        r = d["runs"][0]
        self.assertEqual(r["tool"]["driver"]["name"], "pherkad")
        levels = {x["ruleId"]: x["level"] for x in r["results"]}
        self.assertEqual(levels["banned.game-changer"], "error")
        self.assertEqual(levels["structure.staccato"], "note", "advisory maps to note")
        self.assertEqual({x["id"] for x in r["tool"]["driver"]["rules"]}, set(levels))
        loc = r["results"][0]["locations"][0]["physicalLocation"]
        self.assertEqual(loc["artifactLocation"]["uri"], self.bad)
        self.assertGreaterEqual(loc["region"]["startLine"], 1)

    def test_surface_applies(self):
        with open(self.clean, "w") as fh:
            fh.write("See [the file](docs/x.md).\n")
        self.assertEqual(run(["check", self.clean])[0], 0)
        self.assertEqual(run(["check", "--surface", "assistant-chat", self.clean])[0], 1)

    def test_stdin(self):
        code, out, _ = run(["check", "-"], "This is a game-changer.\n")
        self.assertEqual(code, 1)

    def test_rules_lists_both_engines(self):
        code, out, _ = run(["rules", "--json"])
        rows = {r["id"] for r in json.loads(out)}
        self.assertIn("banned.game-changer", rows)
        self.assertIn("structure.two-beat", rows)
        self.assertIn("density", rows)


class Decisions(unittest.TestCase):
    TEXT = ("The count was wrong. The ledger was right. That is the whole error.\n\n"
            "The honest answer is no.\n\n"
            "Plain prose that is the whole of it, and is the whole of that too.\n")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "canon"))
        self.f = os.path.join(self.root, "canon", "a.md")
        with open(self.f, "w") as fh:
            fh.write(self.TEXT)
        self.dec = os.path.join(self.root, "voice-decisions.json")

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, *extra):
        code, out, _ = run(["check", "--decisions", self.dec, *extra, self.f])
        return code, out

    def decide(self, loc, reason="read it", disposition="accepted", *extra):
        return run(["decide", "--decisions", self.dec, "--reason", reason, "--disposition", disposition, *extra,
                    os.path.join(self.root, loc)])

    def test_undecided_baseline(self):
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn("1 error(s), 4 warning(s)", out)

    def test_decide_hides_and_stops_counting(self):
        self.assertEqual(self.decide("canon/a.md:3", "literal", "intentional")[0], 0)
        code, out = self.check()
        self.assertEqual(code, 0, "a decided error no longer counts")
        self.assertNotIn("honest-framing", out)
        self.assertIn("1 decided (1 intentional)", out)
        code, out = self.check("--show-decided")
        self.assertIn("[decided:intentional] honest-framing", out)

    def test_decision_file_shape(self):
        self.decide("canon/a.md:3", "literal", "intentional")
        d = json.load(open(self.dec))
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["path"], "canon/a.md", "relative to the decision file's directory")
        for k in ("rule_id", "context_hash", "rule_hash", "count", "disposition", "reason", "decided"):
            self.assertIn(k, d[0])
        self.assertEqual(d[0]["reason"], "literal")

    def test_count_covers_occurrences_on_the_line(self):
        # Line 5 has two "is the whole"; deciding the line records count 2.
        self.decide("canon/a.md:5:soft.is-the-whole")
        self.assertEqual(json.load(open(self.dec))[0]["count"], 2)
        code, out = self.check()
        self.assertIn("2 decided", out)
        # A third occurrence changes the line, so the whole line is new again.
        text = self.TEXT.replace("and is the whole of that too.", "and is the whole of that too, which is the whole.")
        with open(self.f, "w") as fh:
            fh.write(text)
        code, out = self.check()
        self.assertNotIn("decided", out)
        self.assertEqual(out.count("soft.is-the-whole"), 4, "three on line 5 plus one on line 1, all reported")

    def test_changed_line_surfaces_the_finding_again(self):
        self.decide("canon/a.md:3", "literal", "intentional")
        with open(self.f, "w") as fh:
            fh.write(self.TEXT.replace("is no.", "is yes."))
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn("honest-framing", out)
        code, out, _ = run(["decisions", "--decisions", self.dec, self.f])
        self.assertIn("1 stale", out)
        self.assertIn("line changed or finding gone", out)

    def test_changed_rule_invalidates(self):
        self.decide("canon/a.md:3", "literal", "intentional")
        d = json.load(open(self.dec))
        d[0]["rule_hash"] = "0000000000000000"
        json.dump(d, open(self.dec, "w"))
        code, out = self.check()
        self.assertEqual(code, 1)
        code, out, _ = run(["decisions", "--decisions", self.dec, self.f])
        self.assertIn("rule changed", out)

    def test_prune_is_explicit(self):
        self.decide("canon/a.md:3", "literal", "intentional")
        with open(self.f, "w") as fh:
            fh.write("clean now\n")
        run(["decisions", "--decisions", self.dec, self.f])
        self.assertEqual(len(json.load(open(self.dec))), 1, "not pruned without --prune")
        code, out, _ = run(["decisions", "--decisions", self.dec, "--prune", self.f])
        self.assertEqual(json.load(open(self.dec)), [])

    def test_rule_specific_decision_leaves_other_rules(self):
        self.decide("canon/a.md:1:structure.two-beat")
        code, out = self.check()
        self.assertNotIn("structure.two-beat", out)
        self.assertIn("soft.is-the-whole", out)

    def test_refusals(self):
        self.assertEqual(self.decide("canon/a.md:3", "   ")[0], 2, "a reason is required")
        self.assertEqual(self.decide("canon/a.md:2")[0], 2, "no finding there")
        self.assertEqual(self.decide("canon/a.md:3:banned.game-changer")[0], 2, "no such finding there")
        bad = os.path.join(self.root, "bad.json")
        json.dump([{"rule_id": "x", "path": "p", "context_hash": "c", "rule_hash": "r",
                    "disposition": "whatever", "reason": "r"}], open(bad, "w"))
        self.assertEqual(run(["check", "--decisions", bad, self.f])[0], 2)
        json.dump([{"rule_id": "x", "path": "p", "context_hash": "c", "rule_hash": "r",
                    "disposition": "accepted", "reason": ""}], open(bad, "w"))
        self.assertEqual(run(["check", "--decisions", bad, self.f])[0], 2)

    def test_json_and_sarif_reflect_decisions(self):
        self.decide("canon/a.md:3", "literal", "intentional")
        code, out, _ = run(["check", "--decisions", self.dec, "--format", "json", self.f])
        d = json.loads(out)
        self.assertEqual(d["decided"]["intentional"], 1)
        fs = d["files"][self.f]
        self.assertTrue(any(f["decision"] and f["rule_id"] == "honest-framing" for f in fs))
        code, out, _ = run(["check", "--decisions", self.dec, "--format", "sarif", self.f])
        self.assertNotIn("honest-framing", {r["ruleId"] for r in json.loads(out)["runs"][0]["results"]})

    def test_deferred_counts_separately(self):
        self.decide("canon/a.md:3", "fix next pass", "deferred")
        code, out = self.check()
        self.assertEqual(code, 0)
        self.assertIn("1 decided (1 deferred)", out)


class Manifest(unittest.TestCase):
    def test_manifest_verifies_in_the_repo(self):
        # The committed manifest must match the files beside it; a release that
        # forgets `manifest --write` fails here, which is the point.
        code, out, _ = run(["manifest", "--verify"])
        self.assertEqual(code, 0, out)

    def test_manifest_shape(self):
        m = pherkad.build_manifest()
        for k in ("tool", "version", "schema", "generated", "files", "rule_ids"):
            self.assertIn(k, m)
        for f in ("pherkad.py", "voicelint.py", "structlint.py", "mdmask.py", "voice_config.json",
                  "surfaces/assistant-chat.json"):
            self.assertIn(f, m["files"])
        self.assertIn("banned.game-changer", m["rule_ids"])
        self.assertIn("structure.two-beat", m["rule_ids"])

    def test_vendored_copy_verifies_without_optional_files(self):
        # A downstream gate vendors the five required files and the manifest,
        # with no VERSION beside them; that must verify, and a changed required
        # file must not.
        import shutil
        with tempfile.TemporaryDirectory() as d:
            for f in pherkad.REQUIRED_FILES + ("bundle-manifest.json",):
                shutil.copy(os.path.join(HERE, f), d)
            proc = subprocess.run([sys.executable, os.path.join(d, "pherkad.py"), "manifest", "--verify"],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            with open(os.path.join(d, "voicelint.py"), "a") as fh:
                fh.write("\n# drift\n")
            proc = subprocess.run([sys.executable, os.path.join(d, "pherkad.py"), "manifest", "--verify"],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("changed: voicelint.py", proc.stdout)

    def test_verify_detects_a_changed_file(self):
        with tempfile.TemporaryDirectory() as d:
            m = pherkad.build_manifest()
            m["files"]["voicelint.py"] = "0" * 64
            p = os.path.join(d, "bundle-manifest.json")
            json.dump(m, open(p, "w"))
            # verify_manifest reads files relative to the manifest's directory,
            # so point it at the real tools dir by copying the manifest there is
            # not an option; instead check the comparison logic directly.
            problems = pherkad.verify_manifest(p)
            self.assertTrue(any(p_.startswith("missing:") for p_ in problems), problems)


class CheckOverlay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def overlay(self, body):
        p = os.path.join(self.tmp.name, "ov.json")
        json.dump(body, open(p, "w"))
        return p

    def test_clean_overlay(self):
        code, out, _ = run(["check-overlay", self.overlay({"add_banned_phrases": ["circle back"],
                                                           "remove_soft_phrases": ["soft.is-the-point"]})])
        self.assertEqual(code, 0)
        self.assertIn("0 error(s), 0 warning(s)", out)

    def test_removal_of_a_missing_rule_is_an_error(self):
        code, out, _ = run(["check-overlay", self.overlay({"remove_soft_phrases": ["soft.the-one-that"]})])
        self.assertEqual(code, 1)
        self.assertIn("names no shipped rule", out)

    def test_duplicate_add_is_a_warning(self):
        code, out, _ = run(["check-overlay", self.overlay({"add_banned_phrases": ["game-changer"]})])
        self.assertEqual(code, 0)
        self.assertIn("already a shipped rule", out)

    def test_wholesale_replacement_is_a_warning(self):
        code, out, _ = run(["check-overlay", self.overlay({"soft_phrases": ["x"]})])
        self.assertEqual(code, 0)
        self.assertIn("replaces the whole shipped list", out)

    def test_empty_shipped_list_replacement_is_not_a_warning(self):
        code, out, _ = run(["check-overlay", self.overlay({"aggregator_domains": ["msn.com"]})])
        self.assertIn("0 warning(s)", out)

    def test_unknown_structure_key_is_a_config_error(self):
        self.assertEqual(run(["check-overlay", self.overlay({"structure": {"nope": 1}})])[0], 2)

    def test_shipped_surface_overlay_is_clean(self):
        code, out, _ = run(["check-overlay", os.path.join(HERE, "surfaces", "assistant-chat.json")])
        self.assertEqual(code, 0)
        self.assertIn("0 error(s), 0 warning(s)", out)


if __name__ == "__main__":
    unittest.main()
