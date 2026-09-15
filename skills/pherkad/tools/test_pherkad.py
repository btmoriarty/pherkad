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


if __name__ == "__main__":
    unittest.main()
