#!/usr/bin/env python3
"""Tests for replycheck and its Stop hook. Dependency-free.

Run from anywhere:  python3 /path/to/test_replycheck.py
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

import replycheck  # noqa: E402
import voicelint  # noqa: E402

SCRIPT = os.path.join(HERE, "replycheck.py")
HOOK = os.path.join(HERE, "replycheck-hook.py")


def run(args, text=None, env=None):
    e = dict(os.environ)
    e.update(env or {})
    proc = subprocess.run([sys.executable, SCRIPT, *args], input=text,
                          capture_output=True, text=True, env=e)
    return proc.returncode, proc.stdout, proc.stderr


def hook(payload, env=None):
    e = dict(os.environ)
    e.update(env or {})
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                          capture_output=True, text=True, env=e)
    return proc.returncode, proc.stderr


class Surface(unittest.TestCase):
    def test_default_surface_loads_and_validates(self):
        cfg = voicelint.load_config(replycheck.surface_path("assistant-chat"))
        ids = {r["id"] for r in voicelint.all_rules(cfg)}
        self.assertIn("banned.markdown-link", ids)
        self.assertIn("banned.game-changer", ids, "the shipped rules are still there")

    def test_surface_examples_hold(self):
        cfg = voicelint.load_config(replycheck.surface_path("assistant-chat"))
        for field in voicelint._LIST_FIELDS:
            for e in voicelint.rule_entries(cfg, field):
                for text in e.get("fires", []):
                    with self.subTest(rule=e["id"], fires=text):
                        self.assertIn(e["id"], {f.rule_id for f in voicelint.check(text, cfg)})
                for text in e.get("clean", []):
                    with self.subTest(rule=e["id"], clean=text):
                        self.assertNotIn(e["id"], {f.rule_id for f in voicelint.check(text, cfg)})

    def test_unknown_surface_exits_2(self):
        code, _, err = run(["--surface", "nope", "-"], "hi")
        self.assertEqual(code, 2)
        self.assertIn("assistant-chat", err)


class ChatRules(unittest.TestCase):
    def ids(self, text):
        return {f["rule_id"] for f in replycheck.check_reply(text, structure=False)["findings"]}

    def test_chat_specific_bans(self):
        self.assertIn("banned.markdown-link", self.ids("See [the file](docs/x.md)."))
        self.assertIn("banned.tilde-path", self.ids("Open ~/Documents now."))
        self.assertIn("banned.section-sign", self.ids("See § 5."))
        self.assertIn("banned.pointer-that-is-the-part-that", self.ids("That is the part that matters."))
        self.assertIn("banned.question-praise-great", self.ids("Great question."))
        self.assertIn("banned.worth-noting", self.ids("Worth noting: the cache."))

    def test_shipped_rules_still_apply(self):
        self.assertIn("honest-framing", self.ids("The honest answer is no."))
        self.assertIn("dash", self.ids("We shipped — then paused."))

    def test_clean_reply_has_no_findings(self):
        text = ("Committed as 9c352db. All 86 tests pass under pytest and unittest.\n\n"
                "The overlay at /Users/moriarty/el_loco_lobo/tools/voice_config.json keeps working.\n")
        self.assertEqual(self.ids(text), set())

    def test_code_and_paths_are_not_prose(self):
        text = "Run `python3 /x/voicelint.py --json` and quote `game-changer` in backticks.\n```\nthe honest answer\n```\n"
        self.assertEqual(self.ids(text), set())

    def test_backticks_are_how_to_quote_a_banned_phrase(self):
        # The one habit the recipe names: an example quoted in plain quotes fires.
        self.assertIn("banned.game-changer", self.ids('The rule bans "game-changer".'))
        self.assertNotIn("banned.game-changer", self.ids("The rule bans `game-changer`."))


class Verdict(unittest.TestCase):
    def test_fix_on_error_exit_1(self):
        code, out, _ = run(["-"], "The honest answer is no.\n")
        self.assertEqual(code, 1)
        self.assertIn("replycheck: FIX", out)

    def test_pass_exit_0(self):
        code, out, _ = run(["-"], "Committed. All tests pass.\n")
        self.assertEqual(code, 0)
        self.assertIn("replycheck: PASS", out)

    def test_warning_is_pass_unless_strict(self):
        text = "Frankly, it passed.\n"
        self.assertEqual(run(["-"], text)[0], 0)
        self.assertEqual(run(["--strict", "-"], text)[0], 1)

    def test_structure_is_advisory(self):
        text = "Done. Tests pass. Committed.\n"
        code, out, _ = run(["-"], text)
        self.assertEqual(code, 0)
        self.assertIn("[advisory] structure.staccato", out)
        code, out, _ = run(["--no-structure", "-"], text)
        self.assertNotIn("advisory", out)

    def test_json_shape(self):
        code, out, _ = run(["--json", "-"], "The honest answer is no.\n")
        r = json.loads(out)
        self.assertEqual(r["verdict"], "FIX")
        self.assertEqual(r["surface"], "assistant-chat")
        self.assertEqual(r["findings"][0]["rule_id"], "honest-framing")
        self.assertIn("structure", r)

    def test_missing_file_exits_2(self):
        self.assertEqual(run(["/no/such/reply.md"])[0], 2)


class StopHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "t.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def transcript(self, *rows):
        with open(self.path, "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        return self.path

    @staticmethod
    def user(text):
        return {"type": "user", "message": {"role": "user", "content": text}}

    @staticmethod
    def tool_result():
        return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}}

    @staticmethod
    def assistant(*blocks):
        return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}

    def test_blocks_on_error_with_findings(self):
        p = self.transcript(self.user("go"), self.assistant({"type": "text", "text": "That is the part that matters."}))
        code, err = hook({"transcript_path": p, "stop_hook_active": False})
        self.assertEqual(code, 2)
        self.assertIn("banned.pointer-that-is-the-part-that", err)

    def test_passes_a_clean_reply(self):
        p = self.transcript(self.user("go"), self.assistant({"type": "text", "text": "Done, committed as abc123."}))
        self.assertEqual(hook({"transcript_path": p, "stop_hook_active": False})[0], 0)

    def test_one_enforced_revision_only(self):
        p = self.transcript(self.user("go"), self.assistant({"type": "text", "text": "That is the part that matters."}))
        self.assertEqual(hook({"transcript_path": p, "stop_hook_active": True})[0], 0)

    def test_checks_only_the_turn_since_the_last_human_message(self):
        p = self.transcript(
            self.user("first"), self.assistant({"type": "text", "text": "That is the part that matters."}),
            self.user("second"), self.assistant({"type": "tool_use", "name": "Bash", "input": {}}),
            self.tool_result(), self.assistant({"type": "text", "text": "Clean this time."}))
        self.assertEqual(hook({"transcript_path": p, "stop_hook_active": False})[0], 0)

    def test_joins_text_blocks_across_tool_calls(self):
        p = self.transcript(
            self.user("go"), self.assistant({"type": "text", "text": "Starting."}),
            self.assistant({"type": "tool_use", "name": "Bash", "input": {}}), self.tool_result(),
            self.assistant({"type": "text", "text": "See [it](x.md)."}))
        code, err = hook({"transcript_path": p, "stop_hook_active": False})
        self.assertEqual(code, 2)
        self.assertIn("banned.markdown-link", err)

    def test_warnings_block_only_under_strict(self):
        p = self.transcript(self.user("go"), self.assistant({"type": "text", "text": "Frankly, it passed."}))
        self.assertEqual(hook({"transcript_path": p, "stop_hook_active": False})[0], 0)
        self.assertEqual(hook({"transcript_path": p, "stop_hook_active": False}, {"REPLYCHECK_STRICT": "1"})[0], 2)

    def test_never_wedges_on_a_bad_payload(self):
        self.assertEqual(hook({"transcript_path": "/no/such/file"})[0], 0)
        proc = subprocess.run([sys.executable, HOOK], input="not json", capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
