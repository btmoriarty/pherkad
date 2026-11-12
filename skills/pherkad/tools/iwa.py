#!/usr/bin/env python3
"""iwa: read the text and comments out of a Keynote (.key) file with the standard library.

A Keynote file is a zip of ``Index/*.iwa`` parts. Each part is a run of chunks
(a 0 byte, a 3-byte little-endian length, then a snappy block with no CRC); the
decompressed bytes are a sequence of objects, each a varint-length ArchiveInfo
protobuf (field 1 the object id, field 2 repeated MessageInfo with field 1 the
message type and field 3 the payload length) followed by the payloads.

Two message types matter here, found by reading real files (2026-11-12):

    2001   TSWP.StorageArchive, a text storage: slide titles, bodies, notes
    3056   TSD.CommentStorageArchive: field 1 the comment text, field 3 a
           reference whose field 1 is the object id of the author, whose first
           string is the author's name

Nothing here interprets the rest of the format; ``strings`` pulls every
printable UTF-8 field out of a payload, which is enough for text and comments.

    iwa.py comments FILE.key     # one line per comment: part, author, text
    iwa.py slides FILE.key       # one line per slide part: its text

Stdlib only.
"""
from __future__ import annotations
import re
import sys
import zipfile

TEXT_STORAGE = 2001
COMMENT_STORAGE = 3056
_STYLE_NAMES = re.compile(r"^(Title Text|Body Level|Text \d|Notes|Body)\b")


def snappy(buf: bytes) -> bytes:
    """Decompress one raw snappy block."""
    i = n = shift = 0
    while True:
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << shift
        shift += 7
        if b < 0x80:
            break
    out = bytearray()
    while i < len(buf):
        tag = buf[i]
        i += 1
        kind = tag & 3
        if kind == 0:
            ln = tag >> 2
            if ln >= 60:
                k = ln - 59
                ln = int.from_bytes(buf[i:i + k], "little")
                i += k
            ln += 1
            out += buf[i:i + ln]
            i += ln
            continue
        if kind == 1:
            ln = ((tag >> 2) & 7) + 4
            off = ((tag >> 5) << 8) | buf[i]
            i += 1
        elif kind == 2:
            ln = (tag >> 2) + 1
            off = int.from_bytes(buf[i:i + 2], "little")
            i += 2
        else:
            ln = (tag >> 2) + 1
            off = int.from_bytes(buf[i:i + 4], "little")
            i += 4
        start = len(out) - off
        if off <= 0 or start < 0:
            raise ValueError("bad snappy copy")
        for k in range(ln):
            out.append(out[start + k])
    return bytes(out)


def unframe(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i + 4 <= len(data):
        ln = int.from_bytes(data[i + 1:i + 4], "little")
        out += snappy(data[i + 4:i + 4 + ln])
        i += 4 + ln
    return bytes(out)


def _varint(b: bytes, i: int) -> tuple[int, int]:
    n = shift = 0
    while True:
        c = b[i]
        i += 1
        n |= (c & 0x7F) << shift
        shift += 7
        if c < 0x80:
            return n, i


def fields(b: bytes) -> list[tuple[int, int, object]]:
    """A protobuf message as (field number, wire type, value) triples."""
    i = 0
    out = []
    while i < len(b):
        key, i = _varint(b, i)
        f, w = key >> 3, key & 7
        if w == 0:
            v, i = _varint(b, i)
        elif w == 1:
            v = b[i:i + 8]
            i += 8
        elif w == 2:
            ln, i = _varint(b, i)
            v = b[i:i + ln]
            i += ln
        elif w == 5:
            v = b[i:i + 4]
            i += 4
        else:
            raise ValueError(f"wire type {w}")
        out.append((f, w, v))
    return out


def objects(raw: bytes):
    """Yield (object id, message type, payload) for every object in a part."""
    i = 0
    while i < len(raw):
        ln, i = _varint(raw, i)
        info = fields(raw[i:i + ln])
        i += ln
        oid = next((v for f, w, v in info if f == 1), None)
        for f, w, v in info:
            if f != 2:
                continue
            mi = fields(v)
            typ = next((x for g, _, x in mi if g == 1), None)
            plen = next((x for g, _, x in mi if g == 3), 0)
            yield oid, typ, raw[i:i + plen]
            i += plen


def strings(b: bytes, depth: int = 0) -> list[str]:
    """Every printable UTF-8 length-delimited field in a payload, nested messages included."""
    out: list[str] = []
    try:
        fs = fields(b)
    except (ValueError, IndexError):
        return out
    for f, w, v in fs:
        if w != 2 or not v:
            continue
        try:
            s = v.decode("utf-8")
            if (sum(ch.isprintable() or ch in "\n\t " for ch in s) / len(s) > 0.97
                    and any(ch.isalpha() for ch in s)):
                out.append(s)
                continue
        except UnicodeDecodeError:
            pass
        if depth < 6:
            out.extend(strings(v, depth + 1))
    return out


def parts(path: str):
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.endswith(".iwa"):
                yield n, unframe(z.read(n))


def _part_key(name: str) -> tuple:
    m = re.search(r"Slide-(\d+)", name)
    return (int(m.group(1)) if m else 0, name)


def read(path: str) -> dict:
    """{'slides': [{'part', 'text'}], 'comments': [{'part', 'author', 'text', 'slide_text'}]}.
    Slides are slide parts in object-id order, which is creation order, close to but not
    always the presentation order."""
    objs: dict = {}
    part_text: dict = {}
    raw_comments = []
    for name, raw in parts(path):
        for oid, typ, payload in objects(raw):
            objs[oid] = (typ, payload)
            if typ == TEXT_STORAGE and "/Slide-" in name:
                part_text.setdefault(name, []).extend(
                    s for s in strings(payload)[:3] if not _STYLE_NAMES.match(s))
            elif typ == COMMENT_STORAGE:
                raw_comments.append((name, payload))
    slides = [{"part": n, "text": re.sub(r"\s+", " ", " ".join(part_text[n])).strip()}
              for n in sorted(part_text, key=_part_key)]
    by_part = {s["part"]: s["text"] for s in slides}
    comments = []
    for name, payload in raw_comments:
        fs = fields(payload)
        text = next((v.decode("utf-8", "replace") for g, w, v in fs if g == 1 and w == 2), "")
        author = ""
        ref = next((v for g, w, v in fs if g == 3 and w == 2), None)
        if ref:
            aid = next((x for g, _, x in fields(ref) if g == 1), None)
            if aid in objs:
                names = strings(objs[aid][1])
                author = names[0] if names else ""
        comments.append({"part": name, "author": author, "text": text.strip(),
                         "slide_text": by_part.get(name, "")})
    return {"slides": slides, "comments": comments}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("comments", "slides"):
        sys.stderr.write(__doc__)
        return 2
    doc = read(argv[1])
    if argv[0] == "comments":
        for c in doc["comments"]:
            print(f"{c['part']}\t{c['author']}\t{c['text']}")
    else:
        for s in doc["slides"]:
            print(f"{s['part']}\t{s['text'][:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
