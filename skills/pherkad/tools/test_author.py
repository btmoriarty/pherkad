#!/usr/bin/env python3
"""Tests for author.py. Run from anywhere: python3 /path/to/test_author.py"""
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import author  # noqa: E402
import fingerprint  # noqa: E402
import samples  # noqa: E402
import voicelint  # noqa: E402

SHORT = ["The shed leaked.", "Forty bags, all wet.", "Nobody came.", "We counted them.", "It rained again.", "I sent the bill."]
LONG = "Because the storage facility had not been inspected in several months, the bags stored inside were found to be damaged by water when the team arrived. "


def prose(seed, n=5, per=14):
    rng = random.Random(seed)
    return "\n\n".join(" ".join(rng.choice(SHORT) for _ in range(per)) for _ in range(n)) + "\n"


class Packet(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.sdir = os.path.join(d, "samples")
        for i in range(5):
            p = os.path.join(d, f"s{i}.md")
            body = prose(i) if i else "The shed leaked and the bags got wet. We counted forty. I sent the bill to the landlord on Monday. " * 5 + "\n"
            open(p, "w").write(body)
            samples.main(["add", p, "--dir", self.sdir, "--provenance", "hand", "--surface", "email"])
        self.fp = os.path.join(d, "fp.json")
        fingerprint.main(["build", "--samples", self.sdir, "--out", self.fp])
        rdir = os.path.join(d, "ref")
        os.makedirs(rdir)
        for i in range(4):
            open(os.path.join(rdir, f"r{i}.md"), "w").write((LONG * 8 + "\n\n") * 3)
        self.ref = os.path.join(d, "ref.json")
        fingerprint.main(["build-reference", rdir, "--out", self.ref, "--name", "generic"])
        self.notes = os.path.join(d, "notes.md")
        open(self.notes, "w").write("- the shed leaked\n- forty bags wet\n- bill sent to the landlord\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_constraints_come_from_the_numbers(self):
        fp = json.load(open(self.fp))
        cons = author.constraints(fp["surfaces"]["email"], json.load(open(self.ref)))
        text = "\n".join(cons)
        self.assertIn("Sentences average", text)
        self.assertIn("No dashes of any kind", text)
        self.assertIn("Words the author uses", text)

    def test_exemplars_are_nearest_in_subject(self):
        smp = fingerprint.load_samples(self.sdir, ("hand",), None)
        ex = author.nearest_exemplars("shed leaked bags wet landlord bill", smp, k=2)
        self.assertEqual(len(ex), 2)
        self.assertIn("landlord", ex[0]["text"])
        self.assertGreater(ex[0]["similarity"], ex[1]["similarity"])

    def test_packet_renders_and_loop_keeps_the_best(self):
        fp = json.load(open(self.fp))
        ref = json.load(open(self.ref))
        smp = fingerprint.load_samples(self.sdir, ("hand",), None)
        packet = author.build_packet("- the shed leaked\n- forty bags", "email", fp, ref, smp, 2, "Archetype: flat consequence.", None)
        prompt = author.render(packet)
        for block in ("HOW THE AUTHOR WRITES", "THE AUTHOR'S MOVES", "NEAREST IN SUBJECT", "NOTES TO WRITE FROM"):
            self.assertIn(block, prompt)
        self.assertNotIn("PREVIOUS DRAFT", prompt)
        self.assertIn("PREVIOUS DRAFT", author.render(packet, "- shorten", "old draft"))
        # a runner that answers in the author's short register the first time and in long generic prose after
        runner = os.path.join(self.tmp.name, "runner.py")
        open(runner, "w").write("import sys\np=sys.stdin.read()\nprint(('%s' if 'PREVIOUS DRAFT' not in p else '%s'))\n"
                                % (prose(9, 3, 8).replace("\n", "\\n"), (LONG * 6).replace("\n", "\\n")))
        cfg = voicelint.load_config(None)
        res = author.author_loop(packet, f"{sys.executable} {runner}", 1, fp, "email", ref, cfg)
        self.assertEqual(res["rounds"], 1)
        self.assertGreater(res["score"]["discriminant"], 0, "the first, author-like draft is kept over the generic revision")
        self.assertIn("shed", res["draft"])

    def test_cli_prints_the_packet_without_a_runner(self):
        proc = subprocess.run([sys.executable, os.path.join(HERE, "pherkad.py"), "author", self.notes, "--surface", "email",
                               "--fingerprint", self.fp, "--reference", self.ref, "--samples", self.sdir, "--format", "json"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        p = json.loads(proc.stdout)
        self.assertEqual(p["surface"], "email")
        self.assertEqual(len(p["exemplars"]), 3)
        self.assertIn("forty bags", p["notes"])


if __name__ == "__main__":
    unittest.main()
