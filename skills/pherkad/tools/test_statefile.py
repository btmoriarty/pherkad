#!/usr/bin/env python3
"""Tests for statefile: atomic writes and the load-change-save lock."""
from __future__ import annotations
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import statefile  # noqa: E402

CORRECTIONS = os.path.join(HERE, "corrections.py")


class Atomic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_and_replaces(self):
        p = os.path.join(self.d, "s.json")
        statefile.write_json(p, {"a": 1})
        statefile.write_json(p, {"a": 2})
        self.assertEqual(open(p).read(), '{\n  "a": 2\n}\n')

    def test_an_interrupted_write_leaves_the_old_file_whole(self):
        p = os.path.join(self.d, "ledger.jsonl")
        statefile.write_text(p, "one\ntwo\n")
        with mock.patch("statefile.os.replace", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                statefile.write_text(p, "cut")
        self.assertEqual(open(p).read(), "one\ntwo\n")
        self.assertEqual(os.listdir(self.d), ["ledger.jsonl"], "no temporary file left behind")

    def test_a_symlink_keeps_pointing_at_its_target(self):
        # the voice files in the pherkad root are links into another repository
        real = os.path.join(self.d, "real.md")
        link = os.path.join(self.d, "link.md")
        open(real, "w").write("old\n")
        os.symlink(real, link)
        statefile.write_text(link, "new\n")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(open(real).read(), "new\n")

    def test_keeps_the_mode_of_an_existing_file(self):
        p = os.path.join(self.d, "m.json")
        open(p, "w").write("{}")
        os.chmod(p, 0o600)
        statefile.write_text(p, "{}\n")
        self.assertEqual(os.stat(p).st_mode & 0o777, 0o600)

    @unittest.skipIf(statefile.fcntl is None, "no fcntl on this platform")
    def test_concurrent_adds_lose_nothing(self):
        ledger = os.path.join(self.d, "c.jsonl")
        procs = [subprocess.Popen([sys.executable, CORRECTIONS, "add", "--init", "--ledger", ledger,
                                   "--before", f"phrase number {i}", "--after", "", "--source", "t",
                                   "--surface", "email", "--rationale", "r"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
                 for i in range(8)]
        for p in procs:
            _, err = p.communicate()
            self.assertEqual(p.returncode, 0, err)
        with open(ledger) as fh:
            self.assertEqual(sum(1 for line in fh if line.strip()), 8, "every concurrent add is kept")


if __name__ == "__main__":
    unittest.main()
