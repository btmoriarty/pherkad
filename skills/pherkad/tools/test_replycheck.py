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
        # Since 0b8b7b4 a relative link is what the desktop app wants; only an
        # absolute, ~ or http target is the miss.
        self.assertIn("banned.markdown-link", self.ids("See [the file](/Users/moriarty/docs/x.md)."))
        self.assertIn("banned.markdown-link", self.ids("See [the file](https://example.com/x)."))
        self.assertNotIn("banned.markdown-link", self.ids("See [the file](docs/x.md)."))
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
        text = "It was a very small change.\n"
        self.assertEqual(run(["-"], text)[0], 0)
        self.assertEqual(run(["--strict", "-"], text)[0], 1)

    def test_structure_is_advisory(self):
        text = "Done. Tests pass. Committed.\n"
        code, out, _ = run(["-"], text)
        self.assertEqual(code, 0)
        self.assertIn("[advisory] structure.staccato", out)
        code, out, _ = run(["--json", "-"], text)
        self.assertEqual(json.loads(out)["structure"][0]["rule_id"], "structure.staccato")
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

    def test_skips_a_headless_run(self):
        # A `claude -p` call from a script opens its turn with turnOrigin "sdk";
        # its output feeds a program, so the hook must not make it rewrite.
        row = dict(self.user("extract"), turnOrigin="sdk")
        p = self.transcript(row, self.assistant({"type": "text", "text": "That is the part that matters."}))
        self.assertEqual(hook({"transcript_path": p, "stop_hook_active": False})[0], 0)

    def test_still_checks_a_human_turn_after_a_headless_one(self):
        rows = (dict(self.user("extract"), turnOrigin="sdk"), self.assistant({"type": "text", "text": "{}"}),
                dict(self.user("go"), turnOrigin="human"),
                self.assistant({"type": "text", "text": "That is the part that matters."}))
        self.assertEqual(hook({"transcript_path": self.transcript(*rows), "stop_hook_active": False})[0], 2)

    def test_still_checks_a_task_notification_turn(self):
        row = dict(self.user("<task-notification>done</task-notification>"), turnOrigin="task_notification")
        p = self.transcript(row, self.assistant({"type": "text", "text": "That is the part that matters."}))
        self.assertEqual(hook({"transcript_path": p, "stop_hook_active": False})[0], 2)

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
            self.assistant({"type": "text", "text": "See [it](/Users/moriarty/x.md)."}))
        code, err = hook({"transcript_path": p, "stop_hook_active": False})
        self.assertEqual(code, 2)
        self.assertIn("banned.markdown-link", err)

    def test_warnings_block_only_under_strict(self):
        p = self.transcript(self.user("go"), self.assistant({"type": "text", "text": "It was a very small change."}))
        self.assertEqual(hook({"transcript_path": p, "stop_hook_active": False})[0], 0)
        self.assertEqual(hook({"transcript_path": p, "stop_hook_active": False}, {"REPLYCHECK_STRICT": "1"})[0], 2)

    def test_never_wedges_on_a_bad_payload(self):
        proc = subprocess.run([sys.executable, HOOK], input="not json", capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)

    # Wave 1 (2026-09-27): the hook never passes a reply in silence.
    BAD = "That is the part that matters."

    def run_hook(self, payload, env=None, cwd=None, hook_path=HOOK):
        e = dict(os.environ)
        e.update(env or {})
        return subprocess.run([sys.executable, hook_path], input=json.dumps(payload),
                              capture_output=True, text=True, env=e, cwd=cwd)

    def test_missing_transcript_blocks_once_as_unchecked(self):
        p = self.run_hook({"transcript_path": "/no/such/file", "stop_hook_active": False})
        self.assertEqual(p.returncode, 2)
        self.assertIn("did not run", p.stderr)
        p = self.run_hook({"transcript_path": "/no/such/file", "stop_hook_active": True})
        self.assertEqual(p.returncode, 0, "never a second block")
        self.assertIn("did not run", json.loads(p.stdout)["systemMessage"])

    def test_broken_overlay_blocks_once_as_unchecked(self):
        bad = os.path.join(self.tmp.name, "broken.json")
        open(bad, "w").write("{ not json")
        t = self.transcript(self.user("go"), self.assistant({"type": "text", "text": self.BAD}))
        p = self.run_hook({"transcript_path": t, "stop_hook_active": False}, {"REPLYCHECK_SURFACE": bad})
        self.assertEqual(p.returncode, 2)
        self.assertIn("did not run", p.stderr)

    def test_missing_sibling_blocks_once_as_unchecked(self):
        alone = os.path.join(self.tmp.name, "alone")
        os.makedirs(alone)
        import shutil
        lone = shutil.copy(HOOK, alone)
        t = self.transcript(self.user("go"), self.assistant({"type": "text", "text": "Done."}))
        p = self.run_hook({"transcript_path": t, "stop_hook_active": False}, hook_path=lone)
        self.assertEqual(p.returncode, 2)
        self.assertIn("cannot load replycheck", p.stderr)

    def test_the_revision_is_still_checked(self):
        t = self.transcript(self.user("go"), self.assistant({"type": "text", "text": self.BAD}))
        p = self.run_hook({"transcript_path": t, "stop_hook_active": True})
        self.assertEqual(p.returncode, 0, "the one enforced revision never blocks again")
        self.assertIn("banned.pointer-that-is-the-part-that", json.loads(p.stdout)["systemMessage"])

    def test_a_meta_row_is_not_the_turn_boundary(self):
        meta = dict(self.user("[Image: 800x600]"), isMeta=True)
        t = self.transcript(self.user("go"), self.assistant({"type": "text", "text": self.BAD}),
                            meta, self.assistant({"type": "text", "text": "Done."}))
        self.assertEqual(self.run_hook({"transcript_path": t, "stop_hook_active": False}).returncode, 2)

    def test_checks_the_last_message_not_yet_in_the_transcript(self):
        t = self.transcript(self.user("go"), self.assistant({"type": "text", "text": "Done."}))
        p = self.run_hook({"transcript_path": t, "stop_hook_active": False, "last_assistant_message": self.BAD})
        self.assertEqual(p.returncode, 2)

    def test_a_surfaces_map_in_the_working_folder_is_ignored(self):
        work = os.path.join(self.tmp.name, "project")
        os.makedirs(work)
        relaxed = os.path.join(work, "relaxed.json")
        json.dump({"_surface": {"speaker": "assistant"}, "banned_phrases": []}, open(relaxed, "w"))
        json.dump({"assistant-chat": {"overlay": relaxed}}, open(os.path.join(work, "surfaces.json"), "w"))
        t = self.transcript(self.user("go"), self.assistant({"type": "text", "text": self.BAD}))
        env = {k: "" for k in ("PHERKAD_SURFACES",)}
        p = self.run_hook({"transcript_path": t, "stop_hook_active": False}, env, cwd=work)
        self.assertEqual(p.returncode, 2, "a project folder cannot relax the chat check")
        open(os.path.join(work, "surfaces.json"), "w").write("{ broken")
        p = self.run_hook({"transcript_path": t, "stop_hook_active": False}, env, cwd=work)
        self.assertEqual(p.returncode, 2)
        self.assertIn("banned.pointer-that-is-the-part-that", p.stderr, "nor switch it off")

    def test_a_voice_config_in_the_working_folder_cannot_relax_the_hook(self):
        # I075: PR #3 merged ./voice_config.json onto the chat surface; the hook must never read it
        work = os.path.join(self.tmp.name, "relaxed")
        os.makedirs(work)
        json.dump({"remove_banned_phrases": ["pointer-that-is-the-part-that"], "banned_phrases": []},
                  open(os.path.join(work, "voice_config.json"), "w"))
        t = self.transcript(self.user("go"), self.assistant({"type": "text", "text": self.BAD}))
        p = self.run_hook({"transcript_path": t, "stop_hook_active": False}, {"PHERKAD_SURFACES": ""}, cwd=work)
        self.assertEqual(p.returncode, 2)

    def test_a_reply_cannot_exempt_itself(self):
        for text in (self.BAD + " <!-- voicelint: ignore-line -->", "> " + self.BAD):
            with self.subTest(text=text):
                t = self.transcript(self.user("go"), self.assistant({"type": "text", "text": text}))
                self.assertEqual(self.run_hook({"transcript_path": t, "stop_hook_active": False}).returncode, 2)

    def test_a_directive_named_in_code_is_not_one(self):
        # naming the syntax in backticks is the safe way to mention it
        for text in ("Every directive begins `<!-- voicelint`.", "```\n<!-- voicelint: ignore-line -->\n```"):
            with self.subTest(text=text):
                t = self.transcript(self.user("go"), self.assistant({"type": "text", "text": text}))
                self.assertEqual(self.run_hook({"transcript_path": t, "stop_hook_active": False}).returncode, 0)

    def test_a_long_reply_passes_with_a_length_notice(self):
        t = self.transcript(self.user("status?"), self.assistant({"type": "text", "text": LONG}))
        p = self.run_hook({"transcript_path": t, "stop_hook_active": False})
        self.assertEqual(p.returncode, 0)
        self.assertIn("length: 240 words against a budget of 154 (a 1-word question)",
                      json.loads(p.stdout)["systemMessage"])

    def test_the_budget_scales_with_the_question_and_ignores_reminders(self):
        ask = " ".join(["word"] * 30) + " <system-reminder>" + " ".join(["noise"] * 200) + "</system-reminder>"
        t = self.transcript(self.user(ask), self.assistant({"type": "text", "text": LONG}))
        p = self.run_hook({"transcript_path": t, "stop_hook_active": False})
        self.assertEqual((p.returncode, p.stdout), (0, ""))  # 150 + 4 * 30 = 270 >= 240

    def test_the_length_notice_can_be_turned_off(self):
        t = self.transcript(self.user("status?"), self.assistant({"type": "text", "text": LONG}))
        p = self.run_hook({"transcript_path": t, "stop_hook_active": False}, env={"REPLYCHECK_LENGTH": "0"})
        self.assertEqual((p.returncode, p.stdout), (0, ""))


# 20 clean sentences of 12 words: 240 prose words
LONG = " ".join(["The build finished and the suite ran on the first try today."] * 20)


class Length(unittest.TestCase):
    def test_prose_words_masks_code(self):
        self.assertEqual(replycheck.prose_words("Run `make test now please` then\n```\na b c d\n```\ncommit."), 3)

    def test_default_budget_without_a_question(self):
        code, out, _ = run(["--no-structure", "-"], LONG)
        self.assertEqual(code, 0)
        self.assertNotIn("length:", out)  # 240 is under the default 250

    def test_over_budget_is_advisory_never_fix(self):
        code, out, _ = run(["--no-structure", "--question", "status?", "-"], LONG)
        self.assertEqual(code, 0)
        self.assertIn("[advisory] length: 240 words against a budget of 154 (a 1-word question)", out)
        code, out, _ = run(["--no-structure", "--strict", "--question", "status?", "-"], LONG)
        self.assertEqual(code, 0)  # strict makes warnings fail, not length

    def test_budget_is_capped(self):
        r = replycheck.length_check("x", {"base": 150, "per_question_word": 4, "max": 600}, " ".join(["q"] * 500))
        self.assertEqual(r["budget"], 600)

    def test_question_may_be_a_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write("status?")
        try:
            out = run(["--no-structure", "--question", fh.name, "-"], LONG)[1]
        finally:
            os.unlink(fh.name)
        self.assertIn("budget of 154", out)

    def test_json_carries_the_length(self):
        r = json.loads(run(["--json", "--no-structure", "-"], LONG)[1])
        self.assertEqual(r["length"], {"words": 240, "budget": 250, "question_words": None, "over": False})


if __name__ == "__main__":
    unittest.main()
