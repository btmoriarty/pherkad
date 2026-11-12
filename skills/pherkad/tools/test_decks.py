#!/usr/bin/env python3
"""Tests for decks.py, iwa.py and deckcheck.py, on decks built inside the test."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import decks  # noqa: E402
import deckcheck  # noqa: E402
import iwa  # noqa: E402

NS = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'


def slide_xml(*texts):
    runs = "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in texts)
    return f'<?xml version="1.0"?><p:sld {NS}><p:cSld><p:spTree><p:sp><p:txBody>{runs}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>'


def make_pptx(path, slides, notes=None, comments=None, modern=None, revision=1, google=False):
    """slides: list of text lists; notes: {n: text}; comments: {n: [(author_id, text)]}."""
    notes, comments, modern = notes or {}, comments or {}, modern or {}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("docProps/core.xml", f'<cp:coreProperties xmlns:cp="x"><cp:revision>{revision}</cp:revision></cp:coreProperties>')
        if not google:
            z.writestr("docProps/app.xml", "<Properties><Application>Microsoft Office PowerPoint</Application></Properties>")
        z.writestr("ppt/commentAuthors.xml", f'<p:cmAuthorLst {NS}><p:cmAuthor id="0" name="Brian Moriarty"/><p:cmAuthor id="1" name="Someone Else"/></p:cmAuthorLst>')
        z.writestr("ppt/authors.xml", '<p188:authorLst xmlns:p188="y"><p188:author id="{A1}" name="Brian Moriarty"/></p188:authorLst>')
        for i, texts in enumerate(slides, 1):
            z.writestr(f"ppt/slides/slide{i}.xml", slide_xml(*texts))
            rels = []
            if i in notes:
                z.writestr(f"ppt/notesSlides/notesSlide{i}.xml", slide_xml(notes[i], str(i)))
                rels.append(f'<Relationship Target="../notesSlides/notesSlide{i}.xml"/>')
            if i in comments:
                cms = "".join(f'<p:cm authorId="{a}" dt="2026-08-09T10:00:00"><p:text>{t}</p:text></p:cm>' for a, t in comments[i])
                z.writestr(f"ppt/comments/comment{i}.xml", f"<p:cmLst {NS}>{cms}</p:cmLst>")
                rels.append(f'<Relationship Target="../comments/comment{i}.xml"/>')
            if i in modern:
                cms = "".join(f'<p188:cm authorId="{{A1}}" created="2026-11-11"><p188:txBody><a:p><a:r><a:t>{t}</a:t></a:r></a:p></p188:txBody></p188:cm>' for t in modern[i])
                z.writestr(f"ppt/comments/modernComment_{i}.xml", f'<p188:cmLst xmlns:p188="y" {NS}>{cms}</p188:cmLst>')
                rels.append(f'<Relationship Target="../comments/modernComment_{i}.xml"/>')
            z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", "<Relationships>" + "".join(rels) + "</Relationships>")


# --- a Keynote file built by hand: protobuf, snappy literals, IWA framing -------------------

def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _field(f, v):
    if isinstance(v, int):
        return _varint(f << 3) + _varint(v)
    if isinstance(v, str):
        v = v.encode()
    return _varint((f << 3) | 2) + _varint(len(v)) + v


def _object(oid, typ, payload):
    info = _field(1, oid) + _field(2, _field(1, typ) + _field(3, len(payload)))
    return _varint(len(info)) + info + payload


def _snappy_literal(data):
    out = bytearray(_varint(len(data)))
    i = 0
    while i < len(data):
        chunk = data[i:i + 60]
        out.append((len(chunk) - 1) << 2)
        out += chunk
        i += 60
    return bytes(out)


def _iwa(raw):
    block = _snappy_literal(raw)
    return b"\x00" + len(block).to_bytes(3, "little") + block


def make_key(path, slides, comments):
    """slides: list of slide texts; comments: {slide index: [text]}; all by Brian."""
    author = _object(9000, 212, _field(1, "Brian Moriarty"))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Index/Document.iwa", _iwa(author))
        oid = 100
        for i, text in enumerate(slides):
            raw = _object(oid, iwa.TEXT_STORAGE, _field(3, text))
            for c in comments.get(i, []):
                oid += 1
                raw += _object(oid, iwa.COMMENT_STORAGE, _field(1, c) + _field(3, _field(1, 9000)))
            z.writestr(f"Index/Slide-{600 + i}-2.iwa", _iwa(raw))
            oid += 1


class Pptx(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_text_notes_revision(self):
        p = os.path.join(self.tmp, "d.pptx")
        make_pptx(p, [["Title one", "Body one."], ["Title two"]], notes={1: "Say this first."}, revision=4)
        d = decks.read(p)
        self.assertEqual(d["revision"], 4)
        self.assertEqual([s["text"] for s in d["slides"]], ["Title one Body one.", "Title two"])
        self.assertEqual(d["slides"][0]["notes"], "Say this first.")
        self.assertEqual(d["slides"][1]["notes"], "")

    def test_legacy_and_modern_comments_with_authors(self):
        p = os.path.join(self.tmp, "c.pptx")
        make_pptx(p, [["Alpha"], ["Beta"]], comments={1: [("0", "Change term"), ("1", "Not mine")]},
                  modern={2: ["Obtuse wording"]}, google=True)
        d = decks.read(p)
        got = {(c["slide"], c["author"], c["text"]) for c in d["comments"]}
        self.assertIn((1, "Brian Moriarty", "Change term"), got)
        self.assertIn((1, "Someone Else", "Not mine"), got)
        self.assertIn((2, "Brian Moriarty", "Obtuse wording"), got)
        self.assertTrue(d["google"])
        self.assertEqual(next(c for c in d["comments"] if c["text"] == "Change term")["slide_text"], "Alpha")


class Keynote(unittest.TestCase):
    def test_comments_author_and_slide_text(self):
        p = os.path.join(tempfile.mkdtemp(), "deck.key")
        long_text = "A slide title that runs on " * 5  # longer than one snappy literal
        make_key(p, ["First slide text", long_text], {1: ["Obtuse wording", "Is this actually present?"]})
        d = decks.read(p)
        self.assertEqual(d["format"], "key")
        self.assertEqual(len(d["slides"]), 2)
        self.assertEqual(d["slides"][1]["text"], " ".join(long_text.split()))
        self.assertEqual([(c["slide"], c["author"], c["text"]) for c in d["comments"]],
                         [(2, "Brian Moriarty", "Obtuse wording"), (2, "Brian Moriarty", "Is this actually present?")])

    def test_snappy_copies(self):
        # literal "abcd", then a 1-byte-offset copy of length 4 at offset 4 -> "abcdabcd"
        block = _varint(8) + bytes([3 << 2]) + b"abcd" + bytes([((4 - 4) << 2) | 1 | (0 << 5), 4])
        self.assertEqual(iwa.snappy(block), b"abcdabcd")


class Html(unittest.TestCase):
    def test_sections_and_notes(self):
        p = os.path.join(tempfile.mkdtemp(), "d.html")
        with open(p, "w") as fh:
            fh.write('<html><body><section><h1>One</h1><p>First.</p><aside class="notes">Say one.</aside></section>'
                     '<div class="slide"><h1>Two</h1><script>var x="no";</script></div></body></html>')
        d = decks.read(p)
        self.assertEqual([(s["text"], s["notes"]) for s in d["slides"]], [("One First.", "Say one."), ("Two", "")])


class DeckCheck(unittest.TestCase):
    def test_error_fails_the_build_and_snapshot_is_written(self):
        tmp = tempfile.mkdtemp()
        bad = os.path.join(tmp, "bad.pptx")
        make_pptx(bad, [["Plan"], ["The honest answer is that it works."]], notes={1: "Fine notes."})
        cfg = {"log_dir": os.path.join(tmp, "gate")}
        cp = os.path.join(tmp, "gate.json")
        with open(cp, "w") as fh:
            json.dump(cfg, fh)
        r = subprocess.run([sys.executable, os.path.join(HERE, "deckcheck.py"), "--config", cp, bad],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("slide 2", r.stdout)
        snaps = deckcheck.snapshots(cfg, bad)
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0]["slides"][0]["notes"], "Fine notes.")
        with open(os.path.join(cfg["log_dir"], "gate-log.jsonl")) as fh:
            self.assertEqual(json.loads(fh.readlines()[-1])["verdict"], "block")

    def test_clean_deck_passes_without_config(self):
        p = os.path.join(tempfile.mkdtemp(), "ok.pptx")
        make_pptx(p, [["Plan"], ["We ship on Friday."]])
        env = dict(os.environ)
        env.pop("PHERKAD_GATE_CONFIG", None)
        r = subprocess.run([sys.executable, os.path.join(HERE, "deckcheck.py"), p],
                           capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
