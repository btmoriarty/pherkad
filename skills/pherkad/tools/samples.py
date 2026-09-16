#!/usr/bin/env python3
"""samples.py: the author's own writing, with provenance, for the measured profile.

A samples folder lives in the author's private repository, never in Pherkad.
Every sample carries a manifest line (id, file, provenance, surface, date,
words, sha256, source, note); nothing enters unlabelled and the tool never
guesses a provenance or a surface.

Provenance:
  hand      typed by the author, no model in the loop; builds the profile
  captured  the author's words recorded by an assistant with minimal shaping
            (the saga captures); admitted at a lower weight, own register
  approved  AI-assisted, author-edited; kept for testing only, never built from

Usage:
  samples.py add FILE... --dir DIR --provenance hand --surface email [--date D] [--source S] [--note N]
  samples.py list --dir DIR
  samples.py import-captured CAPTURED.md --dir DIR        # the saga's verbatim author items
  samples.py import-mbox FILE.mbox --dir DIR --from ADDR   # sent mail the author exported himself
  samples.py verify --dir DIR                              # every file present and matching its hash

Stdlib only.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

PROVENANCE = ("hand", "captured", "approved")
MANIFEST = "samples.json"
SCHEMA = 1


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load(dir_: str) -> dict:
    p = os.path.join(dir_, MANIFEST)
    if not os.path.exists(p):
        return {"schema": SCHEMA, "samples": []}
    with open(p, encoding="utf-8") as fh:
        m = json.load(fh)
    if m.get("schema") != SCHEMA:
        sys.exit(f"samples: {p} has schema {m.get('schema')!r}; this tool reads {SCHEMA}")
    return m


def save(dir_: str, m: dict) -> None:
    os.makedirs(dir_, exist_ok=True)
    with open(os.path.join(dir_, MANIFEST), "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _record(m: dict, dir_: str, text: str, provenance: str, surface: str, date: str, source: str, note: str) -> dict | None:
    """Write text as a sample file and add its manifest line; None if it is already there."""
    text = text.rstrip() + "\n"
    sha = _sha(text)
    if any(s["sha256"] == sha for s in m["samples"]):
        return None
    sid = f"{surface}-{sha[:8]}"
    sub = os.path.join(dir_, provenance, surface)
    os.makedirs(sub, exist_ok=True)
    rel = os.path.join(provenance, surface, sid + ".md")
    with open(os.path.join(dir_, rel), "w", encoding="utf-8") as fh:
        fh.write(text)
    rec = {"id": sid, "file": rel, "provenance": provenance, "surface": surface, "date": date or "",
           "words": len(text.split()), "sha256": sha, "source": source or "", "note": note or "",
           "added": datetime.date.today().isoformat()}
    m["samples"].append(rec)
    return rec


def cmd_add(args) -> int:
    m = load(args.dir)
    n = 0
    for path in args.files:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            sys.stderr.write(f"samples: {exc}\n")
            return 2
        if len(text.split()) < args.min_words:
            print(f"skipped (under {args.min_words} words): {path}")
            continue
        rec = _record(m, args.dir, text, args.provenance, args.surface, args.date, args.source or os.path.abspath(path), args.note)
        if rec is None:
            print(f"already recorded: {path}")
            continue
        n += 1
        print(f"added {rec['id']}  {rec['provenance']}/{rec['surface']}  {rec['words']} words")
    save(args.dir, m)
    print(f"samples: {n} added; {len(m['samples'])} in {os.path.join(args.dir, MANIFEST)}")
    return 0


def cmd_list(args) -> int:
    m = load(args.dir)
    by = {}
    for s in m["samples"]:
        by.setdefault((s["provenance"], s["surface"]), []).append(s)
    for (prov, surf), rows in sorted(by.items()):
        words = sum(r["words"] for r in rows)
        print(f"{prov:9} {surf:12} {len(rows):4} sample(s) {words:7} words")
        if args.verbose:
            for r in rows:
                print(f"    {r['id']}  {r['words']:5}  {r['date'] or '-':10}  {r['source'][:60]}")
    total = sum(s["words"] for s in m["samples"])
    hand = sum(s["words"] for s in m["samples"] if s["provenance"] == "hand")
    print(f"samples: {len(m['samples'])} in all, {total} words; {hand} words of hand provenance build the profile")
    return 0


def cmd_verify(args) -> int:
    m = load(args.dir)
    bad = 0
    for s in m["samples"]:
        p = os.path.join(args.dir, s["file"])
        if not os.path.exists(p):
            print(f"missing: {s['file']}")
            bad += 1
            continue
        with open(p, encoding="utf-8") as fh:
            if _sha(fh.read()) != s["sha256"]:
                print(f"changed: {s['file']}")
                bad += 1
    print(f"samples: {len(m['samples']) - bad} verified, {bad} problem(s)")
    return 1 if bad else 0


# --- the saga captures -------------------------------------------------------
# CAPTURED.md is mostly the assistant's prose around the author's verbatim
# items. Only the marked verbatim material is his: bold-quoted list items
# (**"..."**) and `Verbatim:` blocks. Each becomes one short `captured` sample.
# An item never contains an asterisk (that would be the engine's bold or italic
# prose) and a bold-quoted item sits on one line; a Verbatim block may wrap.
_VERBATIM_BLOCK = re.compile(r'Verbatim[^*\n]*\*\*\s*\*?"([^*]+?)"\*?\s*\*\*|\*\*Verbatim[^*]*\*\*\s*\*"([^*]+?)"\*')
_BOLD_QUOTE = re.compile(r'\*\*"([^*\n]+?)"\*\*')
_DATE_HEAD = re.compile(r"^## (\d{4}-\d{2}-\d{2})", re.M)


def captured_items(text: str) -> list[tuple[str, str]]:
    """(date, item) for every verbatim author item, date from the nearest heading above."""
    dates = [(m.start(), m.group(1)) for m in _DATE_HEAD.finditer(text)]

    def date_at(pos):
        d = ""
        for start, val in dates:
            if start <= pos:
                d = val
            else:
                break
        return d

    items = []
    seen = set()
    for rx in (_VERBATIM_BLOCK, _BOLD_QUOTE):
        for m in rx.finditer(text):
            item = next(g for g in m.groups() if g)
            item = " ".join(item.split())
            if len(item.split()) < 3 or item in seen:
                continue
            seen.add(item)
            items.append((date_at(m.start()), item))
    return items


def cmd_import_captured(args) -> int:
    try:
        with open(args.file, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        sys.stderr.write(f"samples: {exc}\n")
        return 2
    m = load(args.dir)
    items = captured_items(text)
    n = 0
    for date, item in items:
        if len(item.split()) < args.min_words:
            continue
        rec = _record(m, args.dir, item, "captured", args.surface, date, os.path.abspath(args.file), "verbatim author item")
        if rec:
            n += 1
    save(args.dir, m)
    print(f"samples: {len(items)} verbatim item(s) found, {n} added as captured/{args.surface} "
          f"(items under {args.min_words} words skipped); {len(m['samples'])} in the manifest")
    return 0


# --- sent mail ----------------------------------------------------------------
_QUOTE_LINE = re.compile(r"^\s*>")
_REPLY_HEAD = re.compile(r"^(On .{5,120} wrote:|From: .*|-----Original Message-----|Sent from my .*|________+)\s*$")
_SIG = re.compile(r"^-- ?$")


def strip_reply(body: str) -> str:
    """The author's own lines of a message: cut quoted replies, reply headers, and the signature."""
    out = []
    for line in body.replace("\r\n", "\n").split("\n"):
        if _QUOTE_LINE.match(line) or _REPLY_HEAD.match(line.strip()) or _SIG.match(line):
            break
        out.append(line)
    text = "\n".join(out).strip()
    # collapse three or more blank lines
    return re.sub(r"\n{3,}", "\n\n", text)


def _body_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get("Content-Disposition", "").startswith("attachment"):
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode(msg.get_content_charset() or "utf-8", errors="replace") if payload else ""


def cmd_import_mbox(args) -> int:
    import mailbox
    from email.utils import parseaddr, parsedate_to_datetime
    path = args.file
    # Apple Mail's "Export Mailbox" writes a folder named X.mbox with the mbox file inside it
    if os.path.isdir(path) and os.path.exists(os.path.join(path, "mbox")):
        path = os.path.join(path, "mbox")
    try:
        box = mailbox.mbox(path)
    except OSError as exc:
        sys.stderr.write(f"samples: {exc}\n")
        return 2
    m = load(args.dir)
    seen = added = 0
    want = args.sender.lower()
    for msg in box:
        sender = parseaddr(msg.get("From", ""))[1].lower()
        if want and sender != want:
            continue
        seen += 1
        text = strip_reply(_body_text(msg))
        if len(text.split()) < args.min_words:
            continue
        try:
            date = parsedate_to_datetime(msg.get("Date", "")).date().isoformat()
        except (TypeError, ValueError):
            date = ""
        subject = " ".join((msg.get("Subject") or "").split())
        rec = _record(m, args.dir, text, "hand", "email", date, f"mbox: {subject[:80]}", "sent mail, quoted replies and signature stripped")
        if rec:
            added += 1
    save(args.dir, m)
    print(f"samples: {seen} message(s) from {args.sender or 'any sender'}, {added} added as hand/email "
          f"(under {args.min_words} words skipped, duplicates skipped); {len(m['samples'])} in the manifest")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="the author's own writing, with provenance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="record files as samples")
    a.add_argument("files", nargs="+")
    a.add_argument("--dir", required=True)
    a.add_argument("--provenance", required=True, choices=PROVENANCE)
    a.add_argument("--surface", required=True)
    a.add_argument("--date", default="")
    a.add_argument("--source", default="")
    a.add_argument("--note", default="")
    a.add_argument("--min-words", type=int, default=20)
    a.set_defaults(fn=cmd_add)
    ls = sub.add_parser("list")
    ls.add_argument("--dir", required=True)
    ls.add_argument("-v", "--verbose", action="store_true")
    ls.set_defaults(fn=cmd_list)
    v = sub.add_parser("verify")
    v.add_argument("--dir", required=True)
    v.set_defaults(fn=cmd_verify)
    ic = sub.add_parser("import-captured", help="the saga's verbatim author items")
    ic.add_argument("file")
    ic.add_argument("--dir", required=True)
    ic.add_argument("--surface", default="narrative")
    ic.add_argument("--min-words", type=int, default=6)
    ic.set_defaults(fn=cmd_import_captured)
    im = sub.add_parser("import-mbox", help="sent mail from an mbox export")
    im.add_argument("file")
    im.add_argument("--dir", required=True)
    im.add_argument("--from", dest="sender", default="", help="only messages from this address")
    im.add_argument("--min-words", type=int, default=60)
    im.set_defaults(fn=cmd_import_mbox)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
