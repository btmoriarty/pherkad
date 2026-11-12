#!/usr/bin/env python3
"""Tests for capture.py on fixture transcripts, decks and gate logs built in the test."""
from __future__ import annotations
import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capture  # noqa: E402
import corrections  # noqa: E402
import deckcheck  # noqa: E402
import gate  # noqa: E402
from test_decks import make_key, make_pptx  # noqa: E402

DRAFT = ("The retrospective is graded pass or fail this week. Most students will finish the first part in class. "
         "Bring your laptop and the dataset you picked last week.")


def row(kind, text, ts, entry="claude-desktop", origin="human", uid=None, cwd="/Users/x/code/course", **extra):
    if kind == "a":
        d = {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}
    else:
        d = {"type": "user", "message": {"content": text}, "turnOrigin": origin, "uuid": uid or ts}
    d.update({"timestamp": ts, "entrypoint": entry, "cwd": cwd})
    d.update(extra)
    return json.dumps(d)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "projects", "-p")
        os.makedirs(self.proj)
        self.cfg = {"log_dir": os.path.join(self.tmp, "gate"), "_path": os.path.join(self.tmp, "gate.json"),
                    "ledger": os.path.join(self.tmp, "ledger.jsonl"),
                    "private_ledger": os.path.join(self.tmp, "private.jsonl"),
                    "transcripts": [os.path.join(self.tmp, "projects")], "deck_roots": [os.path.join(self.tmp, "decks")],
                    "private": {"words": ["ProjectX"], "paths": ["projectx"]}, "author_names": ["Brian Moriarty"]}
        os.makedirs(self.cfg["deck_roots"][0])

    def session(self, name, rows):
        p = os.path.join(self.proj, name + ".jsonl")
        with open(p, "w") as fh:
            fh.write("\n".join(rows) + "\n" + json.dumps({"type": "summary", "pad": "x" * 2100}) + "\n")
        return p

    def cands(self):
        return capture._read_jsonl(os.path.join(self.cfg["log_dir"], "candidates.jsonl"))

    def comments(self):
        return capture._read_jsonl(os.path.join(self.cfg["log_dir"], "comments.jsonl"))

    def run_capture(self, only=capture.SOURCES):
        return capture.run(self.cfg, only=only)


class Chat(Base):
    def test_pasteback_with_edit_lead_in(self):
        edited = DRAFT.replace("Most students will finish", "Most students should finish")
        self.session("a", [row("u", "draft the note", "2026-11-11T10:00:00Z"), row("a", DRAFT, "2026-11-11T10:01:00Z"),
                           row("u", "I revised:\n\n" + edited, "2026-11-11T10:05:00Z")])
        out = self.run_capture(("chat",))
        c = self.cands()
        self.assertTrue(c, out)
        self.assertEqual({x["lead"] for x in c}, {"edit"})
        self.assertIn(("will", "should"), [(x["before"], x["after"]) for x in c])
        self.assertEqual(out["sources"]["chat"]["pastebacks"], 1)

    def test_pasted_review_does_not_count(self):
        edited = DRAFT.replace("Most students will finish", "Most students should finish")
        self.session("b", [row("a", DRAFT, "2026-11-11T10:01:00Z"),
                           row("u", "more feedback from the reviewer:\n\n" + edited, "2026-11-11T10:05:00Z")])
        self.run_capture(("chat",))
        self.assertEqual(self.cands(), [])

    def test_verbatim_quote_and_curly_quotes_only(self):
        self.session("c", [row("a", DRAFT + " Don't forget it.", "2026-11-11T10:01:00Z"),
                           row("u", "why this? " + DRAFT, "2026-11-11T10:05:00Z"),
                           row("u", "edit: " + DRAFT + " Don’t forget it.", "2026-11-11T10:06:00Z")])
        self.run_capture(("chat",))
        self.assertEqual(self.cands(), [])

    def test_headless_compaction_and_fiction_are_skipped(self):
        edited = DRAFT.replace("Most students", "Most of you")
        self.session("d", [row("a", DRAFT, "t1", entry="sdk-cli"), row("u", "I revised: " + edited, "t2", entry="sdk-cli")])
        self.session("e", [row("a", DRAFT, "2026-11-11T10:01:00Z"),
                           row("u", "This session is being continued from a previous conversation. " + edited, "2026-11-11T10:05:00Z")])
        self.session("f", [row("a", DRAFT, "2026-11-11T10:01:00Z"),
                           row("u", "Yours: " + DRAFT + "\nMine: " + edited, "2026-11-11T10:05:00Z")])
        self.run_capture(("chat",))
        self.assertEqual(self.cands(), [])

    def test_instruction_in_his_own_words_only(self):
        a = "The deck says the walk the one pager step comes first."
        self.session("g", [row("a", a, "2026-11-11T10:01:00Z"),
                           row("u", 'change "walk the one pager" to "read the one-page summary"', "2026-11-11T10:02:00Z"),
                           row("u", '<pasted_content id="1">replace "comes first" with "opens the class"</pasted_content> thoughts?',
                               "2026-11-11T10:03:00Z")])
        self.run_capture(("chat",))
        c = self.cands()
        self.assertEqual([(x["before"], x["after"], x["lead"]) for x in c],
                         [("walk the one pager", "read the one-page summary", "instruction")])

    def test_slide_comment_is_a_wording_comment(self):
        self.session("h", [row("a", "Built the deck.", "2026-11-11T10:01:00Z"),
                           row("u", "slide 5 is too wordy and sounds like AI", "2026-11-11T10:02:00Z"),
                           row("u", "slide 7 needs the enrollment data", "2026-11-11T10:03:00Z")])
        self.run_capture(("chat",))
        kinds = sorted((m["slide"], m["kind"]) for m in self.comments())
        self.assertEqual(kinds, [(5, "wording"), (7, "fact")])
        self.assertEqual([x["kind"] for x in self.cands()], ["judgment"])

    def test_private_session(self):
        edited = DRAFT.replace("Most students will finish", "Most students should finish")
        self.session("i", [row("a", DRAFT, "2026-11-11T10:01:00Z", cwd="/Users/x/code/projectx-team"),
                           row("u", "edit:\n" + edited, "2026-11-11T10:05:00Z", cwd="/Users/x/code/projectx-team")])
        self.run_capture(("chat",))
        self.assertTrue(self.cands())
        self.assertTrue(all(x["private"] for x in self.cands()))

    def test_second_run_adds_nothing(self):
        edited = DRAFT.replace("Most students will finish", "Most students should finish")
        self.session("j", [row("a", DRAFT, "2026-11-11T10:01:00Z"), row("u", "edit:\n" + edited, "2026-11-11T10:05:00Z")])
        self.run_capture(("chat",))
        n = len(self.cands())
        out = self.run_capture(("chat",))
        self.assertEqual(len(self.cands()), n)
        self.assertEqual(out["new_candidates"], 0)


class Comments(Base):
    def test_returned_keynote_paired_with_next_build(self):
        d = self.cfg["deck_roots"][0]
        k = os.path.join(d, "week-04-deck-comments.key")
        make_key(k, ["How the retrospective is graded pass or fail", "Bring your laptop and dataset"],
                 {0: ["Obtuse wording", "Update the dates"]})
        os.utime(k, (time.time() - 3600, time.time() - 3600))
        nxt = os.path.join(d, "week-04-deck.pptx")
        make_pptx(nxt, [["How the retrospective is graded: pass or fail, decided by Friday"], ["Bring your laptop"]])
        out = self.run_capture(("comments",))
        cm = {m["text"]: m for m in self.comments()}
        self.assertEqual(cm["Obtuse wording"]["kind"], "wording")
        self.assertEqual(cm["Update the dates"]["kind"], "content")
        self.assertIn("decided by Friday", cm["Obtuse wording"]["response_text"])
        self.assertEqual(cm["Obtuse wording"]["route"], "returned")
        c = self.cands()
        self.assertEqual(len(c), 1)
        self.assertEqual((c[0]["kind"], c[0]["comment"]), ("judgment", "Obtuse wording"))
        self.assertEqual(out["sources"]["comments"]["comments"], 2)

    def test_other_authors_dropped_and_google_route(self):
        p = os.path.join(self.cfg["deck_roots"][0], "Talk_ v2.pptx")
        make_pptx(p, [["Alpha"]], comments={1: [("0", "Change term"), ("1", "Change term please")]}, google=True)
        self.run_capture(("comments",))
        self.assertEqual([(m["text"], m["route"]) for m in self.comments()], [("Change term", "pptx")])

    def test_hand_saved_pptx_against_its_snapshot(self):
        p = os.path.join(self.cfg["deck_roots"][0], "built.pptx")
        make_pptx(p, [["Plan"], ["Most students will finish the first part in class this week."]], revision=1)
        deckcheck.write_snapshot(self.cfg, p, capture.decks.read(p), when=time.time() - 60)
        make_pptx(p, [["Plan"], ["Most of you should finish the first part in class this week."]], revision=3,
                  comments={2: [("0", "Better")]})
        out = self.run_capture(("comments", "slides"))
        s = [c for c in self.cands() if c["source"] == "slides"]
        self.assertTrue(s, out)
        self.assertEqual(out["sources"]["slides"]["candidates"], len(s))


class FilesAndGmail(Base):
    def test_file_edited_after_the_session_wrote_it(self):
        p = os.path.join(self.tmp, "letter.md")
        with open(p, "w") as fh:
            fh.write("Most of you should finish the first part in class this week.\n")
        gate.append_log(self.cfg, {"type": "gate", "t": time.time() - 100, "ts": "2026-11-11T10:00:00", "kind": "file",
                                   "target": p, "verdict": "pass", "surface": "post",
                                   "text": "Most students will finish the first part in class this week."})
        self.run_capture(("files",))
        c = self.cands()
        self.assertTrue(c)
        self.assertEqual(c[0]["source"], "files")

    def test_gmail_draft_paired_with_sent_message_from_google_session(self):
        gate.append_log(self.cfg, {"type": "gate", "t": time.time() - 100, "ts": "2026-11-11T10:00:00", "kind": "gmail",
                                   "tool_use_id": "tu1", "target": "s", "verdict": "pass",
                                   "text": "Plan\n\nHi all,\n\nMost students will finish the first part in class this week.\n\nBrian"})
        gate.append_log(self.cfg, {"type": "result", "t": time.time() - 99, "tool_use_id": "tu1", "result": {"threadId": "th9"}})
        thread = {"messages": [{"threadId": "th9", "labelIds": ["SENT"],
                                "plaintextBody": "Hi all,\n\nMost of you should finish the first part in class this week.\n\nBrian"}]}
        self.session("google", [
            row("u", "pherkad-google-capture: read sent threads", "2026-11-12T04:00:00Z"),
            json.dumps({"type": "assistant", "entrypoint": "claude-desktop", "timestamp": "2026-11-12T04:01:00Z",
                        "message": {"content": [{"type": "tool_use", "id": "x1", "name": "mcp__g__get_thread", "input": {"threadId": "th9"}}]}}),
            json.dumps({"type": "user", "entrypoint": "claude-desktop", "timestamp": "2026-11-12T04:01:05Z",
                        "message": {"content": [{"type": "tool_result", "tool_use_id": "x1",
                                                 "content": [{"type": "text", "text": json.dumps(thread)}]}]}})])
        out = self.run_capture(("gmail",))
        c = self.cands()
        self.assertTrue(c, out)
        self.assertEqual(c[0]["source"], "gmail")


class AcceptRejectReport(Base):
    def seed(self, private=False):
        edited = DRAFT.replace("Most students will finish", "Most students should finish") if not private else \
            DRAFT.replace("Bring your laptop", "Bring a laptop")
        cwd = "/Users/x/projectx" if private else "/Users/x/course"
        self.session("s" + str(private), [row("a", DRAFT, "2026-11-11T10:01:00Z", cwd=cwd),
                                          row("u", "edit:\n" + edited, "2026-11-11T10:05:00Z", cwd=cwd)])
        self.run_capture(("chat",))

    def test_accept_goes_to_the_right_ledger_and_report_lists_it(self):
        self.seed(private=False)
        self.seed(private=True)
        groups = {c["group"]: c["private"] for c in self.cands()}
        pub = next(g for g, p in groups.items() if not p)
        priv = next(g for g, p in groups.items() if p)
        with redirect_stdout(io.StringIO()):
            capture.accept(self.cfg, [pub, priv], trial=False)
        self.assertTrue(corrections.load_ledger(self.cfg["ledger"]))
        self.assertTrue(corrections.load_ledger(self.cfg["private_ledger"]))
        r = capture.report(self.cfg)
        self.assertTrue(r["ledger"])
        self.assertIn("promote", r["ledger"][0]["promote"])
        self.assertEqual(r["pending_candidates"], 0)

    def test_reject_and_counts_zero_not_missing(self):
        self.seed()
        g = self.cands()[0]["group"]
        self.assertGreater(capture.reject(self.cfg, [g], "not mine"), 0)
        r = capture.report(self.cfg, days=2)
        today = r["per_day"][0]
        for src in capture.SOURCES:
            self.assertIsNotNone(today[src], src)
            self.assertNotEqual(today[src], "failed")
        self.assertEqual(today["slides"], 0)

    def test_a_broken_reader_shows_failed(self):
        self.cfg["deck_roots"] = None  # find_decks iterates it and raises
        out = self.run_capture(("comments",))
        self.assertEqual(out["sources"]["comments"]["status"], "failed")
        self.assertEqual(capture.report(self.cfg, 1)["per_day"][0]["comments"], "failed")


class PromptHook(Base):
    def test_attached_keynote_comments_copied_at_once(self):
        k = os.path.join(self.tmp, "Downloads", "week-11-stevens.key")
        os.makedirs(os.path.dirname(k))
        make_key(k, ["Step 4: run it and mark the findings"], {0: ["Obtuse wording"]})
        capture.prompt_hook(self.cfg, {"prompt": f'here are the comments @"{k}"', "session_id": "s1"})
        self.assertEqual([m["text"] for m in self.comments()], ["Obtuse wording"])
        self.assertEqual(len(os.listdir(os.path.join(self.cfg["log_dir"], "returned"))), 1)

    def test_sort_comment(self):
        cases = {"Obtuse wording": "wording", "AI speak": "wording", "Meaning?": "wording",
                 "Check this data accuracy": "fact", "Make these slides into a table": "design", "Update": "content"}
        for t, k in cases.items():
            self.assertEqual(capture.sort_comment(t), k, t)

    def test_family(self):
        self.assertEqual(capture.family("/d/week-04-critique-redesign-stevens-comments.key"), "week-04-critique-redesign-stevens")
        self.assertEqual(capture.family("/d/week-11-capstone-launch-stevens 2.key"), "week-11-capstone-launch-stevens")
        self.assertEqual(capture.family("/d/Brian Moriarty_ IEEE Syscon 2026(3).pptx"), "brian moriarty_ ieee syscon 2026")


if __name__ == "__main__":
    unittest.main()
