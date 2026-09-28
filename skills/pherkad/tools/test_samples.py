#!/usr/bin/env python3
"""Tests for samples.py. Run from anywhere: python3 /path/to/test_samples.py"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import samples  # noqa: E402


class Manifest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = os.path.join(self.tmp.name, "samples")
        self.src = os.path.join(self.tmp.name, "note.md")
        open(self.src, "w").write("I wrote this one by hand. " * 8 + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_records_provenance_surface_and_hash(self):
        code = samples.main(["add", self.src, "--dir", self.d, "--provenance", "hand", "--surface", "email", "--date", "2026-01-02"])
        self.assertEqual(code, 0)
        m = json.load(open(os.path.join(self.d, "samples.json")))
        self.assertEqual(len(m["samples"]), 1)
        s = m["samples"][0]
        self.assertEqual((s["provenance"], s["surface"], s["date"], s["words"]), ("hand", "email", "2026-01-02", 48))
        self.assertTrue(os.path.exists(os.path.join(self.d, s["file"])))
        self.assertTrue(s["file"].startswith("hand/email/"))
        # the same text again is not a second sample
        samples.main(["add", self.src, "--dir", self.d, "--provenance", "hand", "--surface", "email"])
        self.assertEqual(len(json.load(open(os.path.join(self.d, "samples.json")))["samples"]), 1)
        self.assertEqual(samples.main(["verify", "--dir", self.d]), 0)
        open(os.path.join(self.d, s["file"]), "a").write("tampered\n")
        self.assertEqual(samples.main(["verify", "--dir", self.d]), 1)

    def test_provenance_is_required_and_closed(self):
        with self.assertRaises(SystemExit):
            samples.main(["add", self.src, "--dir", self.d, "--surface", "email"])
        with self.assertRaises(SystemExit):
            samples.main(["add", self.src, "--dir", self.d, "--provenance", "guess", "--surface", "email"])


class Captured(unittest.TestCase):
    SWEEP = ("### 2026-07-22 13:55 · session `a0b114e6` · 11 words\n\n"
             "The bus came late again. Nobody minded.\n\nIt was raining anyway.\n\n")
    TEXT = (
        "## 2026-08-16 · A DROP (author drop)\n\n"
        "The engine's own prose about the drop, which is not the author's.\n\n"
        '    1. **"the assistant quoting the author with a change or two."** [a bold quotation in analysis]\n'
        "## 2026-08-17 · ANOTHER\n\n"
        'Verbatim: **"the kettle went cold before anyone\nremembered it was on."**\n\n'
        "## 2026-08-26 · AUTOMATED CAPTURE SWEEP · 2 DROPS, 14 WORDS\n\n"
        "**Written by `tools/capture-sweep.py`, not by a session.** Verbatim.\n\n"
        + SWEEP
        + "### 2026-07-23 09:00 · session `a0b114e6` · 3 words\n\nok do it\n\n"
        "---\n\n## 2026-08-27 · AUTOMATED CAPTURE SWEEP · 1 DROPS, 11 WORDS\n\n" + SWEEP
    )
    KETTLE = "the kettle went cold before anyone remembered it was on."
    BUS = "The bus came late again. Nobody minded.\n\nIt was raining anyway."

    def test_only_verbatim_blocks_and_sweep_entries_are_taken(self):
        """I193, I194: a bold quotation in the assistant's analysis is not his; the sweep's drops are."""
        items = samples.captured_items(self.TEXT)
        texts = [t for _, t in items]
        self.assertIn(self.KETTLE, texts, "a Verbatim block may wrap a line")
        self.assertIn(self.BUS, texts, "a sweep entry keeps its paragraphs")
        self.assertEqual(texts.count(self.BUS), 1, "a sweep block appended twice is taken once")
        self.assertIn("ok do it", texts, "found; the import's --min-words drops it")
        self.assertFalse(any("assistant quoting" in t or "engine's own prose" in t for t in texts))
        dates = {t: d for d, t in items}
        self.assertEqual(dates[self.KETTLE], "2026-08-17")
        self.assertEqual(dates[self.BUS], "2026-07-22")

    def test_import_writes_only_what_the_author_accepts(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as tmp:
            f = os.path.join(tmp, "CAPTURED.md")
            open(f, "w").write(self.TEXT)
            d = os.path.join(tmp, "samples")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(samples.main(["import-captured", f, "--dir", d, "--min-words", "6"]), 0)
            self.assertIn("nothing written", buf.getvalue())
            self.assertFalse(os.path.exists(os.path.join(d, "samples.json")))
            ids = [ln.split()[0] for ln in buf.getvalue().splitlines() if ln.startswith("  narrative-")]
            self.assertEqual(len(ids), 2)
            self.assertEqual(samples.main(["import-captured", f, "--dir", d, "--accept", "narrative-00000000"]), 2)
            self.assertEqual(samples.main(["import-captured", f, "--dir", d, "--accept", ids[0]]), 0)
            m = json.load(open(os.path.join(d, "samples.json")))
            self.assertEqual([s["id"] for s in m["samples"]], [ids[0]])
            self.assertEqual(samples.main(["import-captured", f, "--dir", d, "--accept", "all"]), 0)
            m = json.load(open(os.path.join(d, "samples.json")))
            self.assertEqual({s["provenance"] for s in m["samples"]}, {"captured"})
            self.assertEqual({s["surface"] for s in m["samples"]}, {"narrative"})
            self.assertEqual(len(m["samples"]), 2)


class Mail(unittest.TestCase):
    def test_machine_bodies_and_link_targets(self):
        self.assertTrue(samples.machine_generated("Hi there,\n\nBrian Moriarty is inviting you to a scheduled Zoom meeting.\n"))
        self.assertFalse(samples.machine_generated("Hi all,\n\nTwo things before Friday.\n"))
        self.assertEqual(samples.strip_reply("See the form<https://forms.office.com/x> and reply.\n"), "See the form and reply.")

    def test_html_only_bodies_are_read_down_to_text(self):
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["From"] = "me@example.org"
        msg.set_content("<div>Hi Larry,</div><div><br></div><div>Two &amp; three.</div>", subtype="html")
        text, bad = samples._body_text(msg)
        self.assertEqual((text.strip().split("\n"), bad), (["Hi Larry,", "", "Two & three."], 0))
        self.assertEqual(samples.html_to_text("<p>a</p><p>b</p>").split(), ["a", "b"])

    def test_a_mislabelled_charset_keeps_its_quotes(self):
        """I119: cp1252 or UTF-8 bytes under a latin-1 or ascii label are read as what they are."""
        cp = "I don’t know “why” — yet.".encode("cp1252")
        self.assertEqual(samples.decode_bytes(cp, "iso-8859-1"), ("I don’t know “why” — yet.", 0))
        self.assertEqual(samples.decode_bytes(cp, "us-ascii")[0], "I don’t know “why” — yet.")
        self.assertEqual(samples.decode_bytes("café ’".encode("utf-8"), "us-ascii"), ("café ’", 0))
        self.assertEqual(samples.decode_bytes("café".encode("latin-1"), "iso-8859-1"), ("café", 0))
        self.assertEqual(samples.decode_bytes(b"ok", "no-such-charset"), ("ok", 0))
        # 0x81 is undefined in cp1252: counted, not silently replaced
        self.assertEqual(samples.decode_bytes(b"a\x81\x93b\x94", "iso-8859-1")[1], 1)

    def test_strip_reply_keeps_only_the_authors_lines(self):
        body = ("Hi all,\n\nTwo things before Friday.\n\nBrian\n\n-- \nBrian Moriarty\n"
                "On Mon, Sep 1, 2026 at 9:00 AM Someone <s@x.org> wrote:\n> the quoted thread\n")
        self.assertEqual(samples.strip_reply(body), "Hi all,\n\nTwo things before Friday.\n\nBrian")

    def test_import_mbox_filters_sender_and_length(self):
        import mailbox
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sent.mbox")
            box = mailbox.mbox(path)
            from email.message import EmailMessage
            long = "This is a sentence the author typed. " * 20
            for frm, body in (("me@example.org", long), ("other@example.org", long), ("me@example.org", "too short"),
                              ("me@example.org", "Brian is inviting you to a scheduled Zoom meeting. " * 20),
                              ("me@example.org", "A pasted report. " * 500)):
                msg = EmailMessage()
                msg["From"] = frm
                msg["To"] = "you@example.org"
                msg["Subject"] = "Plan"
                msg["Date"] = "Mon, 01 Sep 2026 09:00:00 -0400"
                msg.set_content(body + "\n\n> quoted\n")
                box.add(msg)
            box.flush()
            d = os.path.join(tmp, "samples")
            # an Apple Mail export folder (Sent.mbox/mbox) is accepted as the file
            apple = os.path.join(tmp, "Exported.mbox")
            os.makedirs(apple)
            os.rename(path, os.path.join(apple, "mbox"))
            self.assertEqual(samples.main(["import-mbox", apple, "--dir", d, "--from", "me@example.org",
                                           "--provenance", "hand", "--surface", "email"]), 0)
            m = json.load(open(os.path.join(d, "samples.json")))
            self.assertEqual(len(m["samples"]), 1)
            s = m["samples"][0]
            self.assertEqual((s["provenance"], s["surface"], s["date"], s["sender"]), ("hand", "email", "2026-09-01", "me@example.org"))
            self.assertNotIn("quoted", open(os.path.join(d, s["file"])).read())

    def _mbox(self, tmp, msgs):
        import mailbox
        path = os.path.join(tmp, "sent.mbox")
        box = mailbox.mbox(path)
        for msg in msgs:
            box.add(msg)
        box.flush()
        return path

    def _msg(self, frm="me@example.org", subject="Plan", body="", **headers):
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["From"] = frm
        msg["To"] = "you@example.org"
        msg["Subject"] = subject
        msg["Date"] = "Mon, 01 Sep 2026 09:00:00 -0400"
        for k, v in headers.items():
            msg[k.replace("_", "-")] = v
        msg.set_content(body or "This is a sentence the author typed. " * 20)
        return msg

    def test_import_mbox_needs_the_authors_address(self):
        """I195: without --from every sender's mail would be filed as his hand."""
        with tempfile.TemporaryDirectory() as tmp:
            path = self._mbox(tmp, [self._msg()])
            with self.assertRaises(SystemExit):
                samples.main(["import-mbox", path, "--dir", os.path.join(tmp, "s"), "--provenance", "hand", "--surface", "email"])
            with self.assertRaises(SystemExit):
                samples.main(["import-mbox", path, "--dir", os.path.join(tmp, "s"), "--from", "me@example.org"])

    def test_import_mbox_takes_aliases_and_skips_what_he_did_not_type(self):
        """I142, I143: +tags and aliases are his; auto-replies, invitations and forwarded parts are not."""
        from email.message import EmailMessage
        with tempfile.TemporaryDirectory() as tmp:
            fwd = self._msg(body="Here is the note I mentioned, with my thoughts below it. " * 8)
            inner = EmailMessage()
            inner["From"] = "someone@example.org"
            inner.set_content("Words someone else wrote in the forwarded message. " * 20)
            fwd.add_attachment(inner)
            cal = self._msg(subject="Planning")
            cal.add_attachment("BEGIN:VCALENDAR\nEND:VCALENDAR\n", subtype="calendar")
            msgs = [self._msg("Me <me+lists@example.org>", body="An alias with a tag is still the author writing. " * 10),
                    self._msg("me@work.example.org", body="The second address is his too, and he typed this. " * 10),
                    self._msg(subject="Automatic reply: Plan"),
                    self._msg(Auto_Submitted="auto-replied", body="Away until Monday, typed once and sent by a rule. " * 10),
                    self._msg(Precedence="bulk", body="A list digest in his name, not his words today. " * 10),
                    cal, fwd]
            path = self._mbox(tmp, msgs)
            d = os.path.join(tmp, "s")
            self.assertEqual(samples.main(["import-mbox", path, "--dir", d, "--from", "me@example.org", "--from", "me@work.example.org",
                                           "--provenance", "hand", "--surface", "email", "--min-words", "20"]), 0)
            m = json.load(open(os.path.join(d, "samples.json")))
            texts = [open(os.path.join(d, s["file"])).read() for s in m["samples"]]
            self.assertEqual(len(texts), 3, texts)
            self.assertFalse(any("someone else wrote" in t for t in texts), "a forwarded message/rfc822 part is not his")
            self.assertEqual({s["sender"] for s in m["samples"]}, {"me@example.org", "me@work.example.org"})

    def test_reply_heads_quotes_and_signatures(self):
        """I142: other people's words end where any common attribution starts; his interleaved lines stay."""
        for head in ("Jane Doe <jane@example.org> wrote:", "Quoting Jane Doe <jane@example.org>:", "Le lun. 1 sept. 2026, Jane a écrit :",
                     "Am Mo., 1. Sept. 2026 um 09:00 schrieb Jane:", "---------- Forwarded message ---------", "Get Outlook for iOS"):
            self.assertEqual(samples.strip_reply(f"My own line.\n\n{head}\nTheir line.\n"), "My own line.", head)
        self.assertEqual(samples.strip_reply("> their question\nMy answer to it.\n> their second\nMy second answer.\n"),
                         "My answer to it.\nMy second answer.")
        self.assertEqual(samples.strip_reply("Two things before Friday.\n\nThanks,\nBrian Moriarty\nTeaching Professor\n"),
                         "Two things before Friday.")
        html = ('<div>My reply is short.</div><div class="gmail_quote"><div>On Mon, Jane wrote:</div>'
                "<blockquote>Their long message.</blockquote></div>")
        self.assertEqual(samples.html_to_text(html).strip(), "My reply is short.")
        self.assertEqual(samples.html_to_text('<p>Mine.</p><div id="divRplyFwdMsg">From: Jane</div><p>Theirs.</p>').strip(), "Mine.")


if __name__ == "__main__":
    unittest.main()
