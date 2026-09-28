#!/usr/bin/env python3
"""Tests for runner: the shared runner call, error replies, and the canary."""
from __future__ import annotations
import os
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import runner as rn  # noqa: E402


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def script(self, body, name="r.py"):
        p = os.path.join(self.tmp.name, name)
        with open(p, "w") as fh:
            fh.write(body)
        return f"{sys.executable} {p}"

    def test_reply_and_meta(self):
        r = self.script("import sys; sys.stdin.read(); sys.stderr.write('noise\\nrunner-meta: {\"models\": [\"m-1\"]}\\n'); print(' hi ')")
        reply, err, meta = rn.run(r, "prompt", 30)
        self.assertEqual((reply, err, meta), ("hi", "", {"models": ["m-1"]}))

    def test_a_failed_runner_keeps_what_it_printed(self):
        r = self.script("import sys; print('partial answer'); sys.stderr.write('boom'); sys.exit(4)")
        reply, err, _ = rn.run(r, "p", 30)
        self.assertIsNone(reply)
        self.assertIn("runner exit 4", err)
        self.assertIn("boom", err)
        self.assertIn("partial answer", err, "stdout is kept in the error (I023)")

    def test_a_timeout_kills_the_whole_group(self):
        # I021: a timed-out codex.sh left its codex child running
        pidfile = os.path.join(self.tmp.name, "child.pid")
        r = self.script("import subprocess, sys, time\n"
                        f"c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                        f"open({pidfile!r}, 'w').write(str(c.pid))\n"
                        "time.sleep(60)\n")
        reply, err, _ = rn.run(r, "p", 2)
        self.assertIsNone(reply)
        self.assertIn("timed out", err)
        pid = int(open(pidfile).read())
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            os.kill(pid, 9)
            self.fail("the runner's child outlived the timeout")


class Replies(unittest.TestCase):
    def test_runner_errors_and_refusals_are_not_drafts(self):
        for text in ("API Error: 529 overloaded, try again in a minute and it should be fine again",
                     "Credit balance is too low to access the Anthropic API. Please go to Plans & Billing.",
                     "You've hit your usage limit. Upgrade or try again at 4pm to continue working.",
                     "I can't help with rewriting this text in someone else's voice, but here is a summary."):
            with self.subTest(text=text[:30]):
                self.assertTrue(rn.looks_like_error(text))
        self.assertEqual(rn.looks_like_error("Errors in the budget were fixed on Tuesday, and the team moved on."), "")
        self.assertEqual(rn.looks_like_error("The draft follows. It keeps every fact in the notes."), "")


class Canary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def answering(self, answer):
        p = os.path.join(self.tmp.name, "c.py")
        with open(p, "w") as fh:
            fh.write(f"import sys; sys.stdin.read(); print({answer!r})")
        return f"{sys.executable} {p}"

    def test_only_a_bare_none_is_isolated(self):
        self.assertTrue(rn.canary(self.answering("NONE"), 30)[0])
        self.assertTrue(rn.canary(self.answering("None."), 30)[0])
        self.assertFalse(rn.canary(self.answering("PRESENT: a memory file on the author's voice"), 30)[0])
        self.assertFalse(rn.canary(self.answering("NONE, apart from a style guide in AGENTS.md"), 30)[0])


if __name__ == "__main__":
    unittest.main()
