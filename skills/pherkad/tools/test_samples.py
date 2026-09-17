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
    TEXT = (
        "## 2026-08-16 · A DROP (author drop)\n\n"
        "The engine's own prose about the drop, which is not the author's.\n\n"
        '- *The capture (his items, verbatim):*\n'
        '    1. **"when you\'re notion of exotic travel is Tionesta, PA."** [Verbatim incl. "you\'re".]\n'
        '    2. **"fried and water."** [too short]\n'
        "## 2026-08-17 · ANOTHER\n\n"
        'Verbatim: **"lived experience is immutable. It only changes due to the fallibility of the human mind."**\n'
    )

    def test_only_verbatim_items_are_taken(self):
        items = samples.captured_items(self.TEXT)
        texts = [t for _, t in items]
        self.assertIn("when you're notion of exotic travel is Tionesta, PA.", texts)
        self.assertIn("lived experience is immutable. It only changes due to the fallibility of the human mind.", texts)
        self.assertIn("fried and water.", texts, "found; the import's --min-words drops it")
        self.assertFalse(any("engine's own prose" in t for t in texts))
        dates = {t: d for d, t in items}
        self.assertEqual(dates["lived experience is immutable. It only changes due to the fallibility of the human mind."], "2026-08-17")
        self.assertEqual(dates["when you're notion of exotic travel is Tionesta, PA."], "2026-08-16")

    def test_import_records_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = os.path.join(tmp, "CAPTURED.md")
            open(f, "w").write(self.TEXT)
            d = os.path.join(tmp, "samples")
            self.assertEqual(samples.main(["import-captured", f, "--dir", d, "--min-words", "6"]), 0)
            m = json.load(open(os.path.join(d, "samples.json")))
            self.assertEqual({s["provenance"] for s in m["samples"]}, {"captured"})
            self.assertEqual({s["surface"] for s in m["samples"]}, {"narrative"})
            self.assertEqual(len(m["samples"]), 2)


class Mail(unittest.TestCase):
    def test_machine_bodies_and_link_targets(self):
        self.assertTrue(samples.machine_generated("Hi there,\n\nBrian Moriarty is inviting you to a scheduled Zoom meeting.\n"))
        self.assertFalse(samples.machine_generated("Hi all,\n\nTwo things before Friday.\n"))
        self.assertEqual(samples.strip_reply("See the form<https://forms.office.com/x> and reply.\n"), "See the form and reply.")

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
            self.assertEqual(samples.main(["import-mbox", apple, "--dir", d, "--from", "me@example.org"]), 0)
            m = json.load(open(os.path.join(d, "samples.json")))
            self.assertEqual(len(m["samples"]), 1)
            s = m["samples"][0]
            self.assertEqual((s["provenance"], s["surface"], s["date"]), ("hand", "email", "2026-09-01"))
            self.assertNotIn("quoted", open(os.path.join(d, s["file"])).read())


if __name__ == "__main__":
    unittest.main()
