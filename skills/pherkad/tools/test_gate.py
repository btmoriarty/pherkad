#!/usr/bin/env python3
"""Tests for gate.py: what each tool carries, the path rule, the verdicts, failing open."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gate  # noqa: E402

BAD = "The honest answer is that we ship on Friday."
GOOD = "We ship on Friday."
GMAIL = "mcp__aaaa-gmail__create_draft"


def make_cfg(tmp: str, **extra) -> dict:
    cfg = {
        "log_dir": os.path.join(tmp, "gate"),
        "servers": {"docs-server": "claude-docs"},
        "paths": {
            "extensions": [".md", ".txt", ".html"],
            "include_roots": [os.path.join(tmp, "Documents") + "/"],
            "code_root": os.path.join(tmp, "code") + "/",
            "code_folders": ["deliverables", "lectures"],
            "exclude_names": ["CLAUDE.md", "HANDOFF.md"],
            "exclude": ["*/.claude/*", "*/tests/*"],
            "routes": [{"prefix": os.path.join(tmp, "saga", "canon") + "/",
                        "config": os.path.join(HERE, "surfaces", "fiction.json")}],
        },
        "private": {"words": ["ProjectX"], "paths": ["projectx"], "recipients": ["@secret.org"]},
    }
    cfg.update(extra)
    return cfg


class Extraction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = make_cfg(self.tmp)

    def test_gmail_subject_and_body(self):
        it = gate.classify(self.cfg, GMAIL, {"to": ["a@b.c"], "subject": "Plan", "body": GOOD})
        self.assertEqual(it["kind"], "gmail")
        self.assertEqual(it["surface"], "email")
        self.assertIn("Plan", it["text"])
        self.assertIn(GOOD, it["text"])
        self.assertEqual(it["recipients"], ["a@b.c"])

    def test_gmail_html_only(self):
        it = gate.classify(self.cfg, "mcp__x__reply", {"messageId": "m1", "htmlBody": "<p>Hi all,</p><p>" + GOOD + "</p>"})
        self.assertIn(GOOD, it["text"])
        self.assertNotIn("<p>", it["text"])
        self.assertEqual(it["target"], "m1")

    def test_slack_message_and_canvas(self):
        it = gate.classify(self.cfg, "mcp__s__slack_send_message", {"channel_id": "C1", "message": GOOD})
        self.assertEqual((it["kind"], it["surface"], it["target"]), ("slack", "email", "C1"))
        it = gate.classify(self.cfg, "mcp__s__slack_update_canvas",
                           {"canvas_id": "F1", "sections": [{"edit_type": "append", "content": "One."}, {"content": "Two."}]})
        self.assertEqual(it["surface"], "post")
        self.assertIn("One.", it["text"])
        self.assertIn("Two.", it["text"])

    def test_drive_text_and_base64(self):
        import base64
        it = gate.classify(self.cfg, "mcp__d__create_file", {"title": "T", "textContent": GOOD, "contentMimeType": "text/plain"})
        self.assertEqual(it["text"], GOOD)
        it = gate.classify(self.cfg, "mcp__d__update_file", {"fileId": "f", "contentMimeType": "text/markdown",
                                                             "base64Content": base64.b64encode(GOOD.encode()).decode()})
        self.assertEqual(it["text"], GOOD)
        self.assertIsNone(gate.classify(self.cfg, "mcp__d__create_file", {"title": "folder"}))

    def test_gdocs_inserted_text(self):
        it = gate.classify(self.cfg, "mcp__g__update_doc", {"documentId": "d", "requests": [
            {"insertText": {"text": GOOD, "location": {"index": 1}}},
            {"replaceAllText": {"replaceText": "Two.", "containsText": {"text": "x"}}},
            {"updateTextStyle": {"fields": "bold"}}]})
        self.assertIn(GOOD, it["text"])
        self.assertIn("Two.", it["text"])

    def test_generic_names_only_on_mapped_servers(self):
        self.assertIsNone(gate.classify(self.cfg, "mcp__other__create", {"text": GOOD}))
        it = gate.classify(self.cfg, "mcp__docs-server__update", {"payload": {"markdown": GOOD}})
        self.assertEqual(it["kind"], "claude-docs")

    def test_artifact_publish_reads_the_file(self):
        p = os.path.join(self.tmp, "page.html")
        with open(p, "w") as fh:
            fh.write("<html><body><h1>Title</h1><p>" + GOOD + "</p><script>var x='the honest answer'</script></body></html>")
        it = gate.classify(self.cfg, "Artifact", {"file_path": p})
        self.assertIn(GOOD, it["text"])
        self.assertNotIn("honest", it["text"])
        self.assertIsNone(gate.classify(self.cfg, "Artifact", {"action": "read", "url": "u"}))
        self.assertIsNone(gate.classify(self.cfg, "Artifact", {"file_path": p, "asset": True, "url": "u"}))

    def test_unrelated_tools_pass_untouched(self):
        self.assertIsNone(gate.classify(self.cfg, "Bash", {"command": "echo"}))
        self.assertIsNone(gate.classify(self.cfg, "mcp__x__search_threads", {"query": "x"}))


class PathRule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = make_cfg(self.tmp)

    def p(self, *parts):
        return os.path.join(self.tmp, *parts)

    def test_gated(self):
        self.assertEqual(gate.path_rule(self.cfg, self.p("Documents", "letter.md"))["surface"], "post")
        self.assertIsNotNone(gate.path_rule(self.cfg, self.p("code", "course", "lectures", "w1", "notes.md")))
        self.assertEqual(gate.path_rule(self.cfg, self.p("code", "tool", "README.md"))["surface"], "technical")

    def test_not_gated(self):
        self.assertIsNone(gate.path_rule(self.cfg, self.p("code", "tool", "src", "notes.md")))
        self.assertIsNone(gate.path_rule(self.cfg, self.p("Documents", "script.py")))
        self.assertIsNone(gate.path_rule(self.cfg, self.p("Documents", "CLAUDE.md")))
        self.assertIsNone(gate.path_rule(self.cfg, self.p("Documents", ".claude", "memory", "x.md")))
        self.assertIsNone(gate.path_rule(self.cfg, self.p("code", "c", "lectures", "tests", "x.md")))

    def test_saga_routed_to_its_own_overlay(self):
        r = gate.path_rule(self.cfg, self.p("saga", "canon", "vignettes", "a.md"))
        self.assertTrue(r["config"].endswith("fiction.json"))

    def test_only_added_lines_are_checked(self):
        f = self.p("Documents", "old.md")
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, "w") as fh:
            fh.write(BAD + "\n")
        it = gate.classify(self.cfg, "Write", {"file_path": f, "content": BAD + "\n" + GOOD + "\n"})
        self.assertEqual(it["text"].strip(), GOOD)
        it = gate.classify(self.cfg, "Edit", {"file_path": f, "old_string": BAD, "new_string": BAD + "\nNew line."})
        self.assertEqual(it["text"].strip(), "New line.")

    def test_headless_runs_skip_file_writes_not_sends(self):
        f = self.p("Documents", "x.md")
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}):
            self.assertIsNone(gate.classify(self.cfg, "Write", {"file_path": f, "content": BAD}))
            self.assertIsNotNone(gate.classify(self.cfg, GMAIL, {"body": BAD}))


class Verdicts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = make_cfg(self.tmp)

    def payload(self, body, target="m1"):
        return {"hook_event_name": "PreToolUse", "session_id": "s", "tool_use_id": "t1",
                "tool_name": "mcp__x__reply", "tool_input": {"messageId": target, "body": body}}

    def test_pass_is_silent_and_logged(self):
        self.assertIsNone(gate.pre(self.cfg, self.payload(GOOD)))
        log = gate.recent_log(self.cfg)
        self.assertEqual(log[-1]["verdict"], "pass")
        self.assertEqual(log[-1]["text"], GOOD)

    def test_error_denies_with_findings(self):
        out = gate.pre(self.cfg, self.payload(BAD))
        h = out["hookSpecificOutput"]
        self.assertEqual(h["permissionDecision"], "deny")
        self.assertIn("honest", h["permissionDecisionReason"].lower())
        self.assertEqual(gate.recent_log(self.cfg)[-1]["verdict"], "block")

    def test_third_refusal_asks_brian(self):
        for _ in range(2):
            self.assertEqual(gate.pre(self.cfg, self.payload(BAD))["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(gate.pre(self.cfg, self.payload(BAD))["hookSpecificOutput"]["permissionDecision"], "ask")
        # another target starts its own count
        self.assertEqual(gate.pre(self.cfg, self.payload(BAD, "m2"))["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_private_flag(self):
        gate.pre(self.cfg, {"hook_event_name": "PreToolUse", "tool_name": GMAIL,
                            "tool_input": {"to": ["x@secret.org"], "body": GOOD}})
        self.assertTrue(gate.recent_log(self.cfg)[-1]["private"])
        gate.pre(self.cfg, self.payload("About ProjectX: " + GOOD, "m9"))
        self.assertTrue(gate.recent_log(self.cfg)[-1]["private"])

    def test_post_records_returned_ids(self):
        gate.post(self.cfg, {"hook_event_name": "PostToolUse", "tool_use_id": "t1", "tool_name": GMAIL,
                             "tool_input": {"body": GOOD},
                             "tool_response": [{"type": "text", "text": json.dumps({"id": "d1", "threadId": "th1"})}]})
        e = gate.recent_log(self.cfg)[-1]
        self.assertEqual((e["type"], e["result"]["threadId"], e["result"]["id"]), ("result", "th1", "d1"))


class FailOpen(unittest.TestCase):
    def run_hook(self, payload, *args, env=None):
        e = dict(os.environ)
        e.pop("PHERKAD_GATE_CONFIG", None)
        e.update(env or {})
        t0 = time.time()
        r = subprocess.run([sys.executable, os.path.join(HERE, "gate.py"), *args], input=json.dumps(payload),
                           capture_output=True, text=True, env=e, timeout=30)
        return r, time.time() - t0

    def test_no_config_lets_the_call_through_loudly(self):
        r, _ = self.run_hook({"tool_name": GMAIL, "tool_input": {"body": BAD}})
        self.assertEqual(r.returncode, 0)
        self.assertIn("did not run", json.loads(r.stdout)["systemMessage"])

    def test_broken_overlay_fails_open_and_is_logged(self):
        tmp = tempfile.mkdtemp()
        cfg = make_cfg(tmp)
        cfg["paths"]["routes"][0]["config"] = os.path.join(tmp, "missing.json")
        cp = os.path.join(tmp, "gate.json")
        with open(cp, "w") as fh:
            json.dump(cfg, fh)
        f = os.path.join(tmp, "saga", "canon", "a.md")
        r, _ = self.run_hook({"tool_name": "Write", "tool_input": {"file_path": f, "content": BAD}}, "--config", cp,
                             env={"CLAUDE_CODE_ENTRYPOINT": "cli"})
        self.assertEqual(r.returncode, 0)
        self.assertIn("unchecked", r.stdout)
        self.assertEqual(gate.recent_log(cfg)[-1]["verdict"], "error")

    def test_speed(self):
        tmp = tempfile.mkdtemp()
        cp = os.path.join(tmp, "gate.json")
        with open(cp, "w") as fh:
            json.dump(make_cfg(tmp), fh)
        _, ungated = self.run_hook({"tool_name": "Write", "tool_input": {"file_path": "/x/y.py", "content": "x"}}, "--config", cp)
        _, gated = self.run_hook({"tool_name": GMAIL, "tool_input": {"body": GOOD}}, "--config", cp)
        # budgets from the design are 20 ms and 300 ms of hook work; a process start is
        # most of either, so the bound here is loose enough for a loaded machine
        self.assertLess(ungated, 1.0)
        self.assertLess(gated, 2.0)


if __name__ == "__main__":
    unittest.main()
