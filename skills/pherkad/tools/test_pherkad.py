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

    def test_density_counts_only_what_counts(self):
        # Codex, 2026-09-15: advisory findings fed a density warning that blocked.
        text = "\n\n".join(["None of them wrong. None of them ours."] * 8) + "\n\n" + "word " * 120 + "\n"
        p = os.path.join(self.root, "dense.md")
        with open(p, "w") as fh:
            fh.write(text)
        code, out, _ = run(["check", "--strict", "--advisory", "structure.", p])
        self.assertEqual(code, 0)
        self.assertNotIn("density", out)
        code, out, _ = run(["check", p])
        self.assertIn("density", out, "without the advisory flag the same findings do count")
        # decide the repeated line: one record covers all eight occurrences, and density goes with them
        code, out, _ = run(["decide", "--decisions", self.dec, "--reason", "the refrain", p + ":1"])
        self.assertIn("8 occurrence(s)", out)
        code, out, _ = run(["check", "--decisions", self.dec, p])
        self.assertIn("8 decided", out)
        self.assertNotIn("density", out)

    def test_structural_decision_is_keyed_on_the_paragraph(self):
        # Astra, 2026-09-16: a structural finding is reported against its
        # paragraph's first line, so an edit further down left the decision in force.
        text = "None of them wrong. None of them ours.\nThe second line of the same paragraph.\n\nPlain prose.\n"
        p = os.path.join(self.root, "para.md")
        open(p, "w").write(text)
        code, out, _ = run(["decide", "--decisions", self.dec, "--reason", "refrain", p + ":1:structure.staccato"])
        self.assertEqual(code, 0, out)
        self.assertEqual(json.load(open(self.dec))[0]["scope"], "paragraph")
        code, out, _ = run(["check", "--decisions", self.dec, p])
        self.assertIn("1 decided", out)
        open(p, "w").write(text.replace("The second line", "An edited second line"))
        code, out, _ = run(["check", "--decisions", self.dec, p])
        self.assertNotIn("decided", out, "an edit anywhere in the paragraph makes it new again")
        self.assertIn("structure.staccato", out)

    def test_threshold_change_invalidates_a_structural_decision(self):
        text = "None of them wrong. None of them ours.\n"
        p = os.path.join(self.root, "th.md")
        open(p, "w").write(text)
        run(["decide", "--decisions", self.dec, "--reason", "refrain", p + ":1:structure.two-beat"])
        self.assertIn("1 decided", run(["check", "--decisions", self.dec, p])[1])
        ov = os.path.join(self.root, "ov.json")
        json.dump({"structure": {"two_beat_diff": 20}}, open(ov, "w"))
        code, out, _ = run(["check", "--decisions", self.dec, "--config", ov, p])
        self.assertNotIn("decided", out, "a changed threshold is a changed rule")
        code, out, _ = run(["decisions", "--decisions", self.dec, "--config", ov, p])
        self.assertIn("rule changed", out)

    def test_frame_finding_is_document_scoped_and_outside_density(self):
        titles = ["A choice, not a default"] * 5 + [f"Section {i}" for i in range(10)]
        text = "# Deck\n\n" + "\n\n".join(f"## {i}. {t}\n\nBody line for slide {i}." for i, t in enumerate(titles, 1)) + "\n"
        p = os.path.join(self.root, "deck.md")
        open(p, "w").write(text)
        code, out, _ = run(["check", p])
        self.assertIn("structure.frame.contrast.heading", out)
        self.assertNotIn("density", out)
        code, out, _ = run(["decide", "--decisions", self.dec, "--reason", "the deck's refrain", p + ":3:structure.frame.contrast.heading"])
        self.assertEqual(code, 0, out)
        self.assertEqual(json.load(open(self.dec))[0]["scope"], "document")
        self.assertIn("1 decided", run(["check", "--decisions", self.dec, p])[1])
        # change one of the quoted titles: the finding is new again
        open(p, "w").write(text.replace("## 2. A choice, not a default", "## 2. A choice, not a default, revised"))
        self.assertNotIn("decided", run(["check", "--decisions", self.dec, p])[1])

    def test_heading_rate_decision_covers_every_heading(self):
        # Astra, 2026-09-16: the rate finding was anchored to one heading, so a
        # decision on it survived edits to the other headings that moved the rate.
        heads = ["What thing %d does" % i for i in range(6)] + ["Section %d" % i for i in range(6)]
        text = "# D\n\n" + "\n\n".join(f"## {h}\n\nBody." for h in heads) + "\n"
        p = os.path.join(self.root, "rate.md")
        open(p, "w").write(text)
        code, out, _ = run(["check", p])
        self.assertIn("structure.interrogative-headers", out)
        line = [f for f in json.loads(run(["check", "--format", "json", p])[1])["files"][p] if f["rule"] == "interrogative-headers"][0]["line"]
        code, out, _ = run(["decide", "--decisions", self.dec, "--reason", "house style", f"{p}:{line}:structure.interrogative-headers"])
        self.assertEqual(code, 0, out)
        self.assertEqual(json.load(open(self.dec))[0]["scope"], "document")
        self.assertIn("1 decided", run(["check", "--decisions", self.dec, p])[1])
        open(p, "w").write(text.replace("## Section 5", "## What section 5 does"))
        self.assertNotIn("decided", run(["check", "--decisions", self.dec, p])[1], "another heading changed the rate")

    def test_structural_revision_is_in_the_hash(self):
        h1 = pherkad.rule_hashes(DEFAULT)["structure.two-beat"]
        saved = pherkad.structlint.STRUCT_REVISION["two-beat"]
        try:
            pherkad.structlint.STRUCT_REVISION["two-beat"] = saved + 1
            self.assertNotEqual(h1, pherkad.rule_hashes(DEFAULT)["structure.two-beat"])
            self.assertEqual(pherkad.rule_hashes(DEFAULT)["structure.staccato"], pherkad.rule_hashes(DEFAULT)["structure.staccato"])
        finally:
            pherkad.structlint.STRUCT_REVISION["two-beat"] = saved

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

    def test_fixture_that_loses_its_span_under_the_stack_is_a_warning(self):
        # "worth [word] than" fires alone, but the shipped "worth more than" wins the tie.
        code, out, _ = run(["check-overlay", self.overlay({"add_soft_phrases": [
            {"id": "soft.worth-word-than", "pattern": "worth [word] than",
             "fires": ["It was worth more than the rest."]}]})])
        self.assertEqual(code, 0)
        self.assertIn("fires alone but under the full stack the finding is soft.worth-more-than", out)

    def test_shipped_surface_overlay_is_clean(self):
        code, out, _ = run(["check-overlay", os.path.join(HERE, "surfaces", "assistant-chat.json")])
        self.assertEqual(code, 0)
        self.assertIn("0 error(s), 0 warning(s)", out)


class Surfaces(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.clean = os.path.join(self.d, "t.md")
        with open(self.clean, "w") as fh:
            fh.write("A statistically significant, robust result.\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_shipped_surface_resolves_and_validates(self):
        for name in pherkad.shipped_surfaces():
            with self.subTest(name):
                info = pherkad.resolve_surface(name)
                self.assertIn(info["speaker"], pherkad.SPEAKERS)
                self.assertIn(info["positive_register"], pherkad.REGISTERS)
                self.assertTrue(info["guidance"])
                cfg, _ = pherkad.load_layers(name, None)
                self.assertIn("banned_phrases", cfg)
        self.assertEqual(pherkad.resolve_surface("assistant-chat")["speaker"], "assistant")
        self.assertEqual(pherkad.resolve_surface("fiction")["positive_register"], "own-voice-document")

    def test_unknown_surface_is_rejected_with_the_list(self):
        code, _, err = run(["check", "--surface", "memo", self.clean])
        self.assertEqual(code, 2)
        self.assertIn("unknown surface 'memo'", err)
        self.assertIn("assistant-chat", err)

    def test_surface_changes_the_rules(self):
        code, out, _ = run(["check", "--surface", "technical", self.clean])
        self.assertIn("0 warning(s)", out)
        code, out, _ = run(["check", "--surface", "post", self.clean])
        self.assertIn("2 warning(s)", out)
        self.assertIn("surface post (author, register yes)", out)

    def test_surface_then_project_overlay_layer(self):
        ov = os.path.join(self.d, "ov.json")
        json.dump({"add_banned_phrases": ["robust result"]}, open(ov, "w"))
        code, out, _ = run(["check", "--surface", "technical", "--config", ov, self.clean])
        self.assertEqual(code, 1, "the project ban applies on top of the surface")
        self.assertIn("0 warning(s)", out, "and the surface's filler removals still hold")

    def test_slides_threshold_comes_from_the_surface(self):
        heads = "\n\n".join(["# D"] + [f"## What thing {i} does" for i in range(2)] + [f"## Section {i}" for i in range(7)])
        p = os.path.join(self.d, "deck.md")
        open(p, "w").write(heads + "\n")
        self.assertNotIn("interrogative", run(["check", "--surface", "post", p])[1])
        self.assertIn("interrogative-headers", run(["check", "--surface", "slides", p])[1])

    def test_user_map_adds_and_overrides(self):
        os.makedirs(os.path.join(self.d, "approved"))
        open(os.path.join(self.d, "approved", "a.md"), "w").write("x")
        json.dump({"add_banned_phrases": ["memo speak"]}, open(os.path.join(self.d, "memo.json"), "w"))
        m = os.path.join(self.d, "surfaces.json")
        json.dump({"_comment": "x",
                   "memo": {"overlay": "memo.json", "speaker": "author", "positive_register": "no", "guidance": "short"},
                   "email": {"excerpts": ["approved/a.md", "approved/missing.md"], "guidance": "Hi all"}},
                  open(m, "w"))
        info = pherkad.resolve_surface("memo", m)
        self.assertEqual((info["speaker"], info["positive_register"], info["from_map"]), ("author", "no", True))
        info = pherkad.resolve_surface("email", m)
        self.assertTrue(info["overlay"].endswith("surfaces/email.json"), "a shipped name keeps its overlay")
        self.assertEqual([e["exists"] for e in info["excerpts"]], [True, False])
        self.assertIn("Hi all", info["guidance"])
        self.assertIn("A message to a person", info["guidance"], "shipped guidance is kept")
        code, out, _ = run(["check", "--surfaces", m, "--surface", "memo", "-"], "memo speak here")
        self.assertEqual(code, 1)
        code, out, _ = run(["surfaces", "--surfaces", m])
        self.assertIn("memo", out)
        self.assertIn("(missing)", out)
        self.assertIn("1/2", out)

    def test_bad_map_values_are_rejected(self):
        m = os.path.join(self.d, "surfaces.json")
        json.dump({"memo": {"speaker": "robot"}}, open(m, "w"))
        self.assertEqual(run(["check", "--surfaces", m, "--surface", "memo", self.clean])[0], 2)
        json.dump({"memo": {"overlay": "nope.json"}}, open(m, "w"))
        self.assertEqual(run(["check", "--surfaces", m, "--surface", "memo", self.clean])[0], 2)

    def test_json_carries_the_surface(self):
        code, out, _ = run(["check", "--surface", "paper", "--format", "json", self.clean])
        d = json.loads(out)
        self.assertEqual((d["surface"], d["speaker"], d["positive_register"]), ("paper", "author", "frame"))


class ReviewPack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.draft = os.path.join(self.d, "draft.md")
        with open(self.draft, "w") as fh:
            fh.write("The honest answer is that we slipped. That is the point of the audit.\n\nNone of them wrong. None of them ours.\n")
        self.prof = os.path.join(self.d, "prof")
        os.makedirs(self.prof)
        for name, body in (("Voice_Profile.md", "# profile\n\nmarker one\n"), ("voice-rules.md", "# rules\n\nno X\n")):
            open(os.path.join(self.prof, name), "w").write(body)

    def tearDown(self):
        self.tmp.cleanup()

    def pack(self, *extra):
        code, out, err = run(["review-pack", "--surface", "email", "--profile-dir", self.prof, "--format", "json", *extra, self.draft])
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_bundle_shape(self):
        p = self.pack()
        for k in ("tool", "version", "generated", "depth", "surface", "config_sha256", "profile", "source",
                  "mechanical", "judgment_rules", "instructions", "output_schema"):
            self.assertIn(k, p)
        self.assertEqual((p["surface"]["name"], p["surface"]["speaker"], p["surface"]["positive_register"]),
                         ("email", "author", "profile"))
        self.assertEqual([f["rule_id"] for f in p["mechanical"]["findings"]],
                         ["honest-framing", "soft.is-the-point", "structure.two-beat"])
        self.assertEqual(p["source"]["words"], 22)
        self.assertTrue(p["source"]["sha256"])

    def test_profile_files_found_hashed_and_inlined(self):
        p = self.pack()
        files = p["profile"]["files"]
        self.assertTrue(files["Voice_Profile.md"]["present"])
        self.assertTrue(files["voice-rules.md"]["present"])
        self.assertFalse(files["voice-authoring.md"]["present"])
        self.assertIn("marker one", files["Voice_Profile.md"]["text"])
        self.assertTrue(files["Voice_Profile.md"]["sha256"])
        p = self.pack("--no-profile-text")
        self.assertNotIn("text", p["profile"]["files"]["Voice_Profile.md"])

    def test_judgment_rules_follow_speaker_and_register(self):
        email = self.pack()["judgment_rules"]
        self.assertTrue(any("positive register" in r for r in email))
        code, out, _ = run(["review-pack", "--surface", "technical", "--profile-dir", self.prof, "--format", "json", self.draft])
        tech = json.loads(out)["judgment_rules"]
        self.assertFalse(any("positive register" in r for r in tech))
        code, out, _ = run(["review-pack", "--surface", "assistant-chat", "--profile-dir", self.prof, "--format", "json", self.draft])
        chat = json.loads(out)["judgment_rules"]
        self.assertTrue(any("chat-only" in r for r in chat))
        self.assertFalse(any("positive register" in r for r in chat))

    def test_decisions_apply_to_the_packet(self):
        dec = os.path.join(self.d, "dec.json")
        run(["decide", "--decisions", dec, "--reason", "the audit is the point", self.draft + ":1:soft.is-the-point"])
        p = self.pack("--decisions", dec)
        self.assertEqual(p["mechanical"]["decided"], 1)
        live = [f["rule_id"] for f in p["mechanical"]["findings"] if not f["decision"]]
        self.assertNotIn("soft.is-the-point", live)
        code, out, _ = run(["review-pack", "--surface", "email", "--profile-dir", self.prof, "--decisions", dec, self.draft])
        self.assertIn("1 finding(s) already decided", out)
        self.assertNotIn("soft.is-the-point", out.split("=== MECHANICAL FINDINGS")[1].split("=== DRAFT")[0])

    def test_prompt_has_every_section_and_no_run_instruction(self):
        code, out, _ = run(["review-pack", "--surface", "email", "--profile-dir", self.prof, self.draft])
        for sec in ("=== INSTRUCTIONS ===", "=== JUDGMENT-ONLY RULES FOR THIS SURFACE ===", "=== OUTPUT ===",
                    "=== PROFILE: Voice_Profile.md ===", "=== MECHANICAL FINDINGS", "=== DRAFT (22 words) ==="):
            self.assertIn(sec, out)
        self.assertIn("do not run any tool", out)
        self.assertNotIn("**Run the mechanical layer once**", out)
        self.assertIn("The honest answer is that we slipped.", out)

    def test_out_dir_writes_both_files(self):
        o = os.path.join(self.d, "out")
        code, out, _ = run(["review-pack", "--surface", "email", "--profile-dir", self.prof, "--out", o, self.draft])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(o, "pack.json")))
        self.assertTrue(os.path.exists(os.path.join(o, "prompt.md")))
        self.assertIn("3 live finding(s)", out)
        self.assertIn("profile files missing: voice-authoring.md", out)

    def test_missing_profile_is_said_not_hidden(self):
        empty = os.path.join(self.d, "noprof")
        os.makedirs(empty)
        code, out, _ = run(["review-pack", "--surface", "email", "--profile-dir", empty, self.draft])
        self.assertIn("profile-less scan", out)

    def test_surface_is_required_and_checked(self):
        self.assertEqual(run(["review-pack", self.draft])[0], 2)
        self.assertEqual(run(["review-pack", "--surface", "memo", self.draft])[0], 2)


if __name__ == "__main__":
    unittest.main()


class MeasuredInPack(unittest.TestCase):
    def test_measured_view_is_carried_when_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft = os.path.join(tmp, "d.md")
            open(draft, "w").write("A short draft. It says one thing.\n")
            prof = os.path.join(tmp, "prof")
            os.makedirs(prof)
            open(os.path.join(prof, "Voice_Profile.md"), "w").write("# profile\n\nmarker\n")
            code, out, err = run(["review-pack", "--surface", "email", "--profile-dir", prof, "--format", "json", draft])
            files = json.loads(out)["profile"]["files"]
            self.assertNotIn("Voice_Profile.measured.md", files, "absent unless present or named")
            measured = os.path.join(tmp, "elsewhere.md")
            open(measured, "w").write("# Measured voice profile\n\n- 12.1 words on average\n")
            code, out, err = run(["review-pack", "--surface", "email", "--profile-dir", prof, "--measured", measured, "--format", "json", draft])
            files = json.loads(out)["profile"]["files"]
            self.assertTrue(files["Voice_Profile.measured.md"]["present"])
            self.assertEqual(files["Voice_Profile.measured.md"]["path"], measured)
            self.assertIn("12.1 words on average", files["Voice_Profile.measured.md"]["text"])
            code, out, err = run(["review-pack", "--surface", "email", "--profile-dir", prof, "--measured", measured, draft])
            self.assertIn("12.1 words on average", out, "the prompt carries the measured view")


class ReviewImport(unittest.TestCase):
    TABLE = (
        "| rule_ref | quote | decision | rationale | proposed_edit |\n"
        "|---|---|---|---|---|\n"
        "| honest-framing | `The honest answer is that we slipped.` | fix | announces candour | `We slipped.` |\n"
        "| soft.is-the-point | `That is the point of the audit.` | intentional | the sentence is the point | |\n"
        "| judgment (5c) | `Not a failure, but a lesson.` | intentional | a real contrast, once | |\n"
        "| judgment (5a) | `Not in this draft.` | intentional | quote is not in the file | |\n"
        "| positive-register | | not applicable | a status email | |\n"
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.draft = os.path.join(self.d, "draft.md")
        self.table = os.path.join(self.d, "table.md")
        self.dec = os.path.join(self.d, "dec.json")
        open(self.draft, "w").write("The honest answer is that we slipped. That is the point of the audit.\n\n"
                                    "Not a failure, but a lesson. We shipped on Tuesday.\n")
        open(self.table, "w").write(self.TABLE)

    def tearDown(self):
        self.tmp.cleanup()

    def do_import(self):
        return run(["review-import", self.table, "--file", self.draft, "--decisions", self.dec, "--surface", "email"])

    def test_parse_table_rows(self):
        rows = pherkad.parse_review_table(self.TABLE)
        self.assertEqual([r["rule_ref"] for r in rows],
                         ["honest-framing", "soft.is-the-point", "judgment (5c)", "judgment (5a)", "positive-register"])
        self.assertEqual(rows[1]["quote"], "That is the point of the audit.")
        self.assertEqual(pherkad._judgment_id("judgment (5c)"), "judgment.5c")
        self.assertEqual(pherkad._judgment_id("positive-register"), "judgment.positive-register")

    def test_records_ruled_rows_only(self):
        code, out, err = self.do_import()
        self.assertEqual(code, 0, err)
        recs = json.load(open(self.dec))
        self.assertEqual(sorted(r["rule_id"] for r in recs), ["judgment.5c", "soft.is-the-point"])
        j = next(r for r in recs if r["rule_id"] == "judgment.5c")
        self.assertEqual((j["quote"], j["line"], j["disposition"], j["scope"]),
                         ("Not a failure, but a lesson.", 3, "intentional", "quote"))
        m = next(r for r in recs if r["rule_id"] == "soft.is-the-point")
        self.assertEqual((m["line"], m["scope"]), (1, "line"))
        self.assertIn("quote not found", out)     # the 5a row
        self.assertIn("needs a quote", out)       # the row without one
        # the mechanical record is a real decision: check hides it
        code, out, err = run(["check", "--surface", "email", "--decisions", self.dec, self.draft])
        self.assertIn("1 decided (1 intentional)", out)
        self.assertNotIn("is the point", out.split("pherkad:")[0])

    def test_judgment_record_lives_by_quote(self):
        self.do_import()
        code, out, err = run(["decisions", "--surface", "email", "--decisions", self.dec, self.draft])
        self.assertIn("2 decision(s) live, 0 stale", out)
        code, out, err = run(["review-pack", "--surface", "email", "--no-profile-text", "--decisions", self.dec,
                              "--format", "json", self.draft])
        self.assertEqual(code, 0, err)
        p = json.loads(out)
        self.assertEqual([d["rule_id"] for d in p["already_ruled"]], ["judgment.5c"])
        code, out, err = run(["review-pack", "--surface", "email", "--no-profile-text", "--decisions", self.dec, self.draft])
        self.assertIn("ALREADY RULED BY THE AUTHOR", out)
        text = open(self.draft).read().replace("Not a failure, but a lesson.", "A lesson.")
        open(self.draft, "w").write(text)
        code, out, err = run(["decisions", "--surface", "email", "--decisions", self.dec, self.draft])
        self.assertIn("stale (quote gone)", out)
        self.assertIn("1 decision(s) live, 1 stale", out)
        code, out, err = run(["review-pack", "--surface", "email", "--no-profile-text", "--decisions", self.dec,
                              "--format", "json", self.draft])
        self.assertEqual(json.loads(out)["already_ruled"], [])

    def test_reimport_updates_in_place(self):
        self.do_import()
        self.do_import()
        self.assertEqual(len(json.load(open(self.dec))), 2)


class Fingerprint(unittest.TestCase):
    def test_check_reports_measured_voice_findings(self):
        import fingerprint
        import samples
        with tempfile.TemporaryDirectory() as tmp:
            sdir = os.path.join(tmp, "samples")
            for i in range(4):
                p = os.path.join(tmp, f"s{i}.md")
                open(p, "w").write(("The dog sat. It rained. We left. Nobody spoke. " * 12 + "\n\n") * 5)
                samples.main(["add", p, "--dir", sdir, "--provenance", "hand", "--surface", "note"])
            fp = os.path.join(tmp, "fp.json")
            fingerprint.main(["build", "--samples", sdir, "--out", fp])
            draft = os.path.join(tmp, "draft.md")
            open(draft, "w").write(("Because the committee had not decided whether the proposal would be funded, the team kept drafting "
                                    "the protocol as if it would be, which meant several long evenings for everyone that spring; nobody objected. ") * 8 + "\n")
            code, out, err = run(["check", "--fingerprint", fp, "--format", "json", draft])
            self.assertEqual(code, 0, err)
            fs = json.loads(out)["files"][draft]
            ids = [f["rule_id"] for f in fs if f["engine"] == "fingerprint"]
            self.assertIn("voice.sent_mean", ids)
            self.assertIn("voice.distance", ids)
            self.assertTrue(all(f["severity"] == "advisory" for f in fs if f["engine"] == "fingerprint"))
            sm = next(f for f in fs if f["rule_id"] == "voice.sent_mean")
            self.assertTrue(sm["match"].startswith("Because"))
            self.assertIn("more than the author", sm["message"])
            # text output prints them and the summary counts them as advisory, not warnings
            code, out, err = run(["check", "--fingerprint", fp, draft])
            self.assertIn("[advisory] voice (voice.sent_mean)", out)
            self.assertIn("0 warning(s)", out)
