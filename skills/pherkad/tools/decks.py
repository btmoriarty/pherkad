#!/usr/bin/env python3
"""decks: slide text, speaker notes and comments out of .pptx, .key and HTML decks.

One reader for the deck check (deckcheck.py) and the edit capture (capture.py):

    read(path) -> {"format", "revision", "slides": [{"n", "text", "notes"}],
                   "comments": [{"slide", "author", "text", "slide_text"}]}

.pptx is read as the zip it is: slide text from ``ppt/slides/slideN.xml``, notes
through each slide's relationship to ``ppt/notesSlides``, comments from the
legacy ``ppt/comments/commentN.xml`` with ``ppt/commentAuthors.xml`` and the
modern ``ppt/comments/modernComment_*.xml`` with ``ppt/authors.xml``, each mapped
to its slide through the slide relationships. ``revision`` is ``cp:revision``,
which PowerPoint raises on every save and the deck libraries leave at 1.

.key goes through iwa.py. HTML decks split on ``<section>`` elements, or on
elements whose class names a slide, with ``<aside class="notes">`` as notes.

Stdlib only.
"""
from __future__ import annotations
import html as htmlmod
import os
import re
import zipfile
from html.parser import HTMLParser

import iwa

_A_T = re.compile(r"<a:t>([^<]*)</a:t>")
_WORD = re.compile(r"\w+")


def words(s: str) -> set:
    return {w.lower() for w in _WORD.findall(s)}


def overlap(a: str, b: str) -> float:
    x, y = words(a), words(b)
    return len(x & y) / max(1, len(x | y))


def best_match(text: str, pool: list) -> tuple[int, float]:
    """Index and overlap of the slide in ``pool`` (dicts with 'text') closest to ``text``."""
    best, idx = 0.0, -1
    for i, s in enumerate(pool):
        o = overlap(text, s["text"])
        if o > best:
            best, idx = o, i
    return idx, best


def _clean(x: str) -> str:
    return re.sub(r"\s+", " ", htmlmod.unescape(x)).strip()


def _pptx(path: str) -> dict:
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        rd = lambda n: z.read(n).decode("utf-8", "replace")  # noqa: E731
        core = rd("docProps/core.xml") if "docProps/core.xml" in names else ""
        m = re.search(r"<cp:revision>(\d+)</cp:revision>", core)
        revision = int(m.group(1)) if m else 0
        nums = sorted(int(m.group(1)) for n in names for m in [re.match(r"ppt/slides/slide(\d+)\.xml$", n)] if m)
        authors = {}
        for an in ("ppt/commentAuthors.xml", "ppt/authors.xml"):
            if an in names:
                for mm in re.finditer(r"<p\d*:?(?:cmAuthor|author)\b([^>]*)>", rd(an)):
                    attrs = dict(re.findall(r'(\w+)="([^"]*)"', mm.group(1)))
                    authors[attrs.get("id")] = htmlmod.unescape(attrs.get("name", ""))
        slides, comment_parts = [], {}
        for k in nums:
            text = _clean(" ".join(_A_T.findall(rd(f"ppt/slides/slide{k}.xml"))))
            notes = ""
            rel = f"ppt/slides/_rels/slide{k}.xml.rels"
            if rel in names:
                r = rd(rel)
                nm = re.search(r'Target="\.\./notesSlides/(notesSlide\d+\.xml)"', r)
                if nm and "ppt/notesSlides/" + nm.group(1) in names:
                    raw = rd("ppt/notesSlides/" + nm.group(1))
                    # the notes body, not the slide-number placeholder
                    notes = _clean(" ".join(t for t in _A_T.findall(raw) if not re.fullmatch(r"\d+", t.strip())))
                for t in re.findall(r'Target="\.\./comments/([^"]+)"', r):
                    comment_parts["ppt/comments/" + t] = k
            slides.append({"n": k, "text": text, "notes": notes})
        comments = []
        by_n = {s["n"]: s["text"] for s in slides}
        for cf in sorted(n for n in names if re.match(r"ppt/comments/(comment|modernComment_)[^/]*\.xml$", n)):
            k = comment_parts.get(cf)
            for mm in re.finditer(r"<p\d*:?cm\b([^>]*)>(.*?)</p\d*:?cm>", rd(cf), re.S):
                attrs = dict(re.findall(r'(\w+)="([^"]*)"', mm.group(1)))
                body = mm.group(2)
                t = re.search(r"<p:text>(.*?)</p:text>", body, re.S)
                t = _clean(t.group(1)) if t else _clean(" ".join(_A_T.findall(body)))
                comments.append({"slide": k, "author": authors.get(attrs.get("authorId"), ""),
                                 "text": t, "slide_text": by_n.get(k, ""),
                                 "date": attrs.get("dt", attrs.get("created", ""))})
    return {"format": "pptx", "revision": revision, "slides": slides, "comments": comments,
            "google": "docProps/app.xml" not in names}


def _key(path: str) -> dict:
    doc = iwa.read(path)
    slides = [{"n": i + 1, "part": s["part"], "text": s["text"], "notes": ""} for i, s in enumerate(doc["slides"])]
    n_of = {s["part"]: s["n"] for s in slides}
    comments = [{"slide": n_of.get(c["part"]), "author": c["author"], "text": c["text"],
                 "slide_text": c["slide_text"], "date": ""} for c in doc["comments"]]
    return {"format": "key", "revision": 0, "slides": slides, "comments": comments, "google": False}


class _SlideHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.slides, self.depth, self.cur, self.notes_depth = [], 0, None, 0
        self.stack = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").lower()
        is_slide = tag == "section" or re.search(r"\bslide\b", cls) is not None
        is_notes = tag == "aside" and "notes" in cls
        self.stack.append((tag, is_slide, is_notes))
        if is_slide and self.cur is None:
            self.cur = {"text": [], "notes": []}
            self.depth = len(self.stack)
        if is_notes:
            self.notes_depth = len(self.stack)

    def handle_endtag(self, tag):
        while self.stack:
            t, _, _ = self.stack.pop()
            if self.notes_depth and len(self.stack) < self.notes_depth:
                self.notes_depth = 0
            if self.cur is not None and len(self.stack) < self.depth:
                self.slides.append(self.cur)
                self.cur = None
            if t == tag:
                break

    def handle_data(self, data):
        if self.cur is None or any(t in ("script", "style") for t, _, _ in self.stack):
            return
        (self.cur["notes"] if self.notes_depth else self.cur["text"]).append(data)


def _html(path: str) -> dict:
    with open(path, encoding="utf-8", errors="replace") as fh:
        src = fh.read()
    p = _SlideHTML()
    p.feed(src)
    if p.cur is not None:
        p.slides.append(p.cur)
    slides = [{"n": i + 1, "text": _clean(" ".join(s["text"])), "notes": _clean(" ".join(s["notes"]))}
              for i, s in enumerate(p.slides)]
    slides = [s for s in slides if s["text"] or s["notes"]]
    if not slides:  # not a slide deck by its markup: the whole page is one slide
        body = re.sub(r"<(script|style)\b.*?</\1>", " ", src, flags=re.S | re.I)
        slides = [{"n": 1, "text": _clean(re.sub(r"<[^>]+>", " ", body)), "notes": ""}]
    return {"format": "html", "revision": 0, "slides": slides, "comments": [], "google": False}


def read(path: str) -> dict:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pptx":
        return _pptx(path)
    if ext == ".key":
        return _key(path)
    if ext in (".html", ".htm"):
        return _html(path)
    raise ValueError(f"not a deck this reader knows: {path}")
