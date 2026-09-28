#!/usr/bin/env python3
"""samples.py: the author's own writing, with provenance, for the measured profile.

A samples folder lives in the author's private repository, never in Pherkad.
Every sample carries a manifest line (id, file, provenance, surface, date,
words, sha256, source, note); nothing enters unlabelled and the tool never
guesses a provenance or a surface.

Provenance:
  hand      typed by the author, no model in the loop; builds the profile
  captured  the author's words recorded by an assistant with minimal shaping
            (the saga captures); built from at the same weight as hand, so
            it belongs on its own surface (import-captured files it as narrative)
  approved  AI-assisted, author-edited; kept for testing only, never built from

Usage:
  samples.py add FILE... --dir DIR --provenance hand --surface email [--date D] [--source S] [--note N]
  samples.py list --dir DIR
  samples.py import-captured CAPTURED.md --dir DIR [--accept ID,...|all]   # lists the verbatim items; writes only accepted ones
  samples.py import-mbox FILE.mbox --dir DIR --from ADDR [--from ALIAS] --provenance hand --surface email
                                                         # sent mail the author exported himself
  samples.py verify --dir DIR                              # every file present and matching its hash

Stdlib only.
"""
from __future__ import annotations
import argparse
import codecs
import datetime
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statefile  # noqa: E402

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
    statefile.write_json(os.path.join(dir_, MANIFEST), m, indent=2, sort_keys=True, ensure_ascii=True)


def _record(m: dict, dir_: str, text: str, provenance: str, surface: str, date: str, source: str, note: str,
            sender: str = "") -> dict | None:
    """Write text as a sample file and add its manifest line; None if it is already there."""
    text = text.rstrip() + "\n"
    sha = _sha(text)
    if any(s["sha256"] == sha for s in m["samples"]):
        return None
    sid = f"{surface}-{sha[:8]}"
    sub = os.path.join(dir_, provenance, surface)
    os.makedirs(sub, exist_ok=True)
    rel = os.path.join(provenance, surface, sid + ".md")
    statefile.write_text(os.path.join(dir_, rel), text)
    rec = {"id": sid, "file": rel, "provenance": provenance, "surface": surface, "date": date or "",
           "words": len(text.split()), "sha256": sha, "source": source or "", "note": note or "",
           "added": datetime.date.today().isoformat()}
    if sender:
        rec["sender"] = sender  # whose mail this was, so the claim that it is the author's can be checked (I195)
    m["samples"].append(rec)
    return rec


def cmd_add(args) -> int:
    m = load(args.dir)
    n = 0
    for path in args.files:
        try:
            with open(path, "rb") as fh:
                text, bad = decode_bytes(fh.read())
            text = text.replace("\r\n", "\n").replace("\r", "\n")  # as text mode read it, so hashes still match
        except OSError as exc:
            sys.stderr.write(f"samples: {exc}\n")
            return 2
        if bad:
            sys.stderr.write(f"samples: {bad} unreadable byte(s) replaced in {path}\n")
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
# items. Only two kinds of passage are his as written (I193, I194):
#   - a block labelled Verbatim (`Verbatim: **"..."**` or `**Verbatim** *"..."*`),
#     which may wrap across lines; and
#   - an entry of the capture sweep's drop log (`### <date> ... · session `id` ·
#     N words`), which capture-sweep.py writes unedited, up to the next heading or rule.
# A bold quotation elsewhere is the assistant quoting him inside its own
# analysis, sometimes with changes, and is not taken. Nothing is written until
# the author has read the candidates and accepted them by id.
_VERBATIM_BLOCK = re.compile(r'Verbatim[^*\n]*\*\*\s*\*?"([^*]+?)"\*?\s*\*\*|\*\*Verbatim[^*]*\*\*\s*\*"([^*]+?)"\*')
_SWEEP_ENTRY = re.compile(r"^### (\d{4}-\d{2}-\d{2})[^\n]*· session `[0-9a-f]+` · \d+ words[ \t]*$", re.M)
_ENTRY_END = re.compile(r"^(?:#{1,6} |---[ \t]*$)", re.M)
_DATE_HEAD = re.compile(r"^## (\d{4}-\d{2}-\d{2})", re.M)


def captured_items(text: str) -> list[tuple[str, str]]:
    """(date, item) for every verbatim author item, date from the nearest
    heading above; duplicates (the sweep has appended some blocks twice) once."""
    dates = [(m.start(), m.group(1)) for m in _DATE_HEAD.finditer(text)]

    def date_at(pos):
        d = ""
        for start, val in dates:
            if start <= pos:
                d = val
            else:
                break
        return d

    found = []
    for m in _VERBATIM_BLOCK.finditer(text):
        found.append((m.start(), date_at(m.start()), " ".join(next(g for g in m.groups() if g).split())))
    for m in _SWEEP_ENTRY.finditer(text):
        end = _ENTRY_END.search(text, m.end())
        body = text[m.end():end.start() if end else len(text)].strip()
        body = re.sub(r"\n{3,}", "\n\n", "\n".join(ln.rstrip() for ln in body.split("\n")))
        found.append((m.start(), m.group(1), body))
    items, seen = [], set()
    for _, date, item in sorted(found):
        key = " ".join(item.split())
        if len(key.split()) < 3 or key in seen:
            continue
        seen.add(key)
        items.append((date, item))
    return items


def cmd_import_captured(args) -> int:
    try:
        with open(args.file, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        sys.stderr.write(f"samples: {exc}\n")
        return 2
    m = load(args.dir)
    have = {s["sha256"] for s in m["samples"]}
    items = captured_items(text)
    cands = []
    for date, item in items:
        body = item.rstrip() + "\n"
        if len(item.split()) >= args.min_words and _sha(body) not in have:
            cands.append((f"{args.surface}-{_sha(body)[:8]}", date, item))
    if not args.accept:
        for cid, date, item in cands:
            print(f"  {cid}  {date or '----------'}  {len(item.split()):>5}w  {' '.join(item.split())[:70]}")
        print(f"samples: {len(items)} verbatim item(s) found, {len(cands)} new at {args.min_words} words or more; nothing written. "
              "Read them, then rerun with --accept ID,ID,... or --accept all.")
        return 0
    want = {x.strip() for x in args.accept.split(",") if x.strip()}
    unknown = sorted(want - {c[0] for c in cands} - {"all"})
    if unknown:
        sys.stderr.write(f"samples: --accept names id(s) that are not new candidates here: {', '.join(unknown)}\n")
        return 2
    n = 0
    for cid, date, item in cands:
        if "all" in want or cid in want:
            if _record(m, args.dir, item, "captured", args.surface, date, os.path.abspath(args.file), "verbatim author item, accepted by id"):
                n += 1
    save(args.dir, m)
    print(f"samples: {n} of {len(cands)} candidate(s) added as captured/{args.surface}; {len(m['samples'])} in the manifest")
    return 0


# --- sent mail ----------------------------------------------------------------
_QUOTE_LINE = re.compile(r"^\s*>")
# where someone else's words begin: a reply attribution in any common form
# ("On ... wrote:", "... wrote:", "Quoting ...:", and the French, German,
# Spanish and Dutch ones), a forwarded or Outlook header, a mobile footer
_REPLY_HEAD = re.compile(r"^(?:.{0,200}\bwrote:|On .{5,200} wrote:?|Quoting .*:|Le .{5,200} a [ée]crit ?:|Am .{5,200} schrieb .*:|"
                         r"El .{5,200} escribi[óo]:|Op .{5,200} schreef .*:|(?:From|De|Von|Da|Van) ?: .*|"
                         r"-{2,} ?(?:Original Message|Forwarded message|Mensaje original|Message d'origine|Urspr[üu]ngliche Nachricht) ?-{2,}|"
                         r"Begin forwarded message:|Sent from my .*|Get Outlook for .*|________+)\s*$", re.I)
_SIG = re.compile(r"^-- ?$")


_MACHINE = re.compile(r"is inviting you to a scheduled Zoom meeting|Join Zoom Meeting|Microsoft Teams meeting|"
                      r"You have been invited to|Automatic reply:|This is an automated", re.I)
_MACHINE_SUBJECT = re.compile(r"^(?:Automatic reply|Auto(?:matic)?[- ]?(?:reply|response)|Out of (?:the )?office|Accepted|Declined|"
                              r"Tentative(?:ly accepted)?|(?:Updated )?invitation|Canceled|Cancelled|Delivery Status Notification|"
                              r"Undeliverable|Read:)\b", re.I)
_ANGLE_URL = re.compile(r"<(?:https?://|mailto:|tel:)[^>]*>")
_BARE_URL = re.compile(r"https?://\S+")


def machine_generated(body: str) -> bool:
    """A calendar invitation, an auto-reply, or another body the author did not type."""
    return bool(_MACHINE.search(body[:1500]))


def machine_message(msg) -> bool:
    """A message the author did not type, read from its headers and parts as
    well as its body: Auto-Submitted, X-Autoreply, a bulk or auto-reply
    Precedence, an auto-reply or calendar Subject, or a text/calendar part (I142)."""
    auto = str(msg.get("Auto-Submitted") or "").strip().lower()
    if auto and auto != "no":
        return True
    if msg.get("X-Autoreply") or msg.get("X-Autorespond"):
        return True
    if str(msg.get("Precedence") or "").strip().lower() in ("bulk", "junk", "list", "auto_reply"):
        return True
    if _MACHINE_SUBJECT.match(" ".join(str(msg.get("Subject") or "").split())):
        return True
    return any(p.get_content_type() == "text/calendar" for p in _parts(msg))


def _signature_tail(lines: list[str]) -> int:
    """How many trailing lines are a sign-off or signature block: the last
    paragraph, when it has two or more lines of six words or fewer and none
    of them ends a sentence (a name, a title, a phone number, "Thanks,")."""
    end = len(lines)
    while end and not lines[end - 1].strip():
        end -= 1
    start = end
    while start and lines[start - 1].strip():
        start -= 1
    block = [ln.strip() for ln in lines[start:end]]
    if len(block) >= 2 and all(len(ln.split()) <= 6 and not ln.endswith((".", "?", "!")) for ln in block):
        return len(lines) - start
    return 0


def strip_reply(body: str) -> str:
    """The author's own lines of a message: quoted lines skipped (an
    interleaved reply keeps his lines between them), everything from a reply
    header or signature marker on cut, a trailing signature block dropped, and
    the link targets Outlook appends in angle brackets removed."""
    out = []
    for line in body.replace("\r\n", "\n").split("\n"):
        if _REPLY_HEAD.match(line.strip()) or _SIG.match(line):
            break
        if _QUOTE_LINE.match(line):
            continue
        line = _ANGLE_URL.sub("", line)
        line = _BARE_URL.sub("", line)
        out.append(line.rstrip())
    cut = _signature_tail(out)
    if cut:
        out = out[:-cut]
    text = "\n".join(out).strip()
    # collapse three or more blank lines
    return re.sub(r"\n{3,}", "\n\n", text)


_TAG = re.compile(r"<[^>]+>")
_BLOCK_TAG = re.compile(r"</?(?:div|p|br|tr|li|h[1-6]|blockquote)\b[^>]*>", re.I)
# the opening of a quoted thread in HTML mail: Gmail, Outlook, Apple Mail, Thunderbird
_HTML_QUOTE = re.compile(r"<blockquote\b|<div[^>]*\bclass=\"[^\"]*\bgmail_quote\b|<[^>]*\bid=\"(?:divRplyFwdMsg|appendonsend)\"|"
                         r"<[^>]*\btype=\"cite\"|<[^>]*\bclass=\"[^\"]*\bmoz-cite-prefix\b", re.I)


def html_to_text(html: str) -> str:
    """A plain reading of an HTML-only body: everything from the first quoted
    thread on is cut (I142), block tags become line breaks, other tags go,
    entities are decoded."""
    import html as htmlmod
    q = _HTML_QUOTE.search(html)
    if q:
        html = html[:q.start()]
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    text = _BLOCK_TAG.sub("\n", text)
    text = _TAG.sub("", text)
    text = htmlmod.unescape(text).replace("\xa0", " ")
    return re.sub(r"\n{3,}", "\n\n", text)


def decode_bytes(data: bytes, charset: str | None = None) -> tuple[str, int]:
    """Bytes as text, and how many bytes could not be read. The declared charset
    goes first, then UTF-8, then Windows-1252. Mail labelled latin-1 or ascii is
    often one of the other two in fact, and latin-1 reads 0x80 to 0x9F, where
    cp1252 keeps its curly quotes and dashes, as invisible controls, so a
    latin-1 label on those bytes is not believed."""
    try:
        declared = codecs.lookup(charset or "utf-8").name
    except LookupError:
        declared = "utf-8"
    mislabelled = declared in ("iso8859-1", "ascii") and re.search(rb"[\x80-\x9f]", data) is not None
    for cs in ([] if mislabelled else [declared]) + ["utf-8", "cp1252"]:
        try:
            return data.decode(cs), 0
        except UnicodeDecodeError:
            continue
    text = data.decode("cp1252" if mislabelled else declared, errors="replace")
    return text, text.count("�")


def _parts(msg):
    """The leaf parts of a message, never walking into an attached or
    forwarded message (message/rfc822), whose words are someone else's (I142)."""
    if not msg.is_multipart():
        yield msg
        return
    for sub in msg.get_payload():
        if sub.get_content_type() == "message/rfc822":
            continue
        yield from _parts(sub)


def _decoded(part) -> tuple[str, int]:
    payload = part.get_payload(decode=True)
    return decode_bytes(payload, part.get_content_charset()) if payload else ("", 0)


def _body_text(msg) -> str:
    """The message body as text, and its unreadable byte count: the text/plain
    part when there is one, else the text/html part read down to text."""
    plain = html = ("", 0)
    for part in _parts(msg):
        if part.get("Content-Disposition", "").startswith("attachment"):
            continue
        ctype = part.get_content_type()
        if ctype == "text/plain" and not plain[0]:
            plain = _decoded(part)
        elif ctype == "text/html" and not html[0]:
            html = _decoded(part)
    if plain[0].strip():
        return plain
    return (html_to_text(html[0]), html[1]) if html[0] else ("", 0)


def _address(raw: str) -> str:
    """An address for comparison: lower case, any +tag dropped."""
    from email.utils import parseaddr
    addr = parseaddr(raw)[1].lower()
    local, at, domain = addr.partition("@")
    return (local.split("+", 1)[0] + at + domain) if at else addr


def cmd_import_mbox(args) -> int:
    import mailbox
    from email import policy
    from email.parser import BytesParser
    from email.utils import parsedate_to_datetime
    path = args.file
    # Apple Mail's "Export Mailbox" writes a folder named X.mbox with the mbox file inside it
    if os.path.isdir(path) and os.path.exists(os.path.join(path, "mbox")):
        path = os.path.join(path, "mbox")
    if not os.path.exists(path):
        sys.stderr.write(f"samples: no mailbox at {path}\n")
        return 2
    want = {_address(a) for a in args.sender if a.strip()}
    if not want:
        sys.stderr.write("samples: --from needs the author's address; without it every sender's mail would be filed as his hand\n")
        return 2
    try:
        # the default policy decodes 8-bit and RFC 2047 headers to str (I143)
        box = mailbox.mbox(path, factory=lambda fh: BytesParser(policy=policy.default).parse(fh))
    except OSError as exc:
        sys.stderr.write(f"samples: {exc}\n")
        return 2
    m = load(args.dir)
    counts = dict.fromkeys(("seen", "added", "other_sender", "machine", "short", "long", "duplicate", "failed", "unreadable"), 0)
    try:
        for msg in box:
            counts["seen"] += 1
            try:
                sender = _address(str(msg.get("From") or ""))
                if sender not in want:
                    counts["other_sender"] += 1
                    continue
                if machine_message(msg):
                    counts["machine"] += 1
                    continue
                raw, bad = _body_text(msg)
                if machine_generated(raw):
                    counts["machine"] += 1
                    continue
                subject = " ".join(str(msg.get("Subject") or "").split())
                if bad:
                    counts["unreadable"] += 1
                    sys.stderr.write(f"samples: {bad} unreadable byte(s) replaced in \"{subject[:60]}\"\n")
                text = strip_reply(raw)
                n_words = len(text.split())
                if n_words < args.min_words:
                    counts["short"] += 1
                    continue
                if n_words > args.max_words:
                    counts["long"] += 1  # a pasted document or a forwarded report, not an email the author typed
                    continue
                try:
                    date = parsedate_to_datetime(str(msg.get("Date") or "")).date().isoformat()
                except (TypeError, ValueError, IndexError):
                    date = ""
                rec = _record(m, args.dir, text, args.provenance, args.surface, date, f"mbox: {subject[:80]}",
                              "sent mail, quoted replies and signature stripped", sender=sender)
                counts["added" if rec else "duplicate"] += 1
            except (LookupError, UnicodeError, AttributeError, ValueError, TypeError) as exc:
                counts["failed"] += 1
                sys.stderr.write(f"samples: message {counts['seen']} not read ({type(exc).__name__}: {exc})\n")
    finally:
        save(args.dir, m)  # every file written so far has its manifest line, even if the loop stops
    c = counts
    print(f"samples: {c['seen']} message(s) read; {c['added']} added as {args.provenance}/{args.surface}; skipped "
          f"{c['other_sender']} from other senders, {c['machine']} machine-generated, {c['short']} under {args.min_words} words, "
          f"{c['long']} over {args.max_words} words, {c['duplicate']} duplicates, {c['failed']} unreadable; "
          f"{len(m['samples'])} in the manifest")
    if c["unreadable"]:
        print(f"samples: {c['unreadable']} message(s) had bytes no charset could read; check them before building")
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
    ic.add_argument("--accept", default="", help="comma-separated candidate ids, or 'all', to write; without it the candidates are listed and nothing is written")
    ic.set_defaults(fn=cmd_import_captured)
    im = sub.add_parser("import-mbox", help="sent mail from an mbox export")
    im.add_argument("file")
    im.add_argument("--dir", required=True)
    im.add_argument("--from", dest="sender", action="append", required=True,
                    help="the author's address; repeat for aliases (a +tag is ignored). Mail from anyone else is skipped")
    im.add_argument("--provenance", required=True, choices=PROVENANCE, help="hand for mail he typed; the tool never guesses")
    im.add_argument("--surface", required=True, help="the register this mail is (email, email-personal, ...); the tool never guesses")
    im.add_argument("--min-words", type=int, default=60)
    im.add_argument("--max-words", type=int, default=800, help="longer bodies are pasted documents, not typed mail")
    im.set_defaults(fn=cmd_import_mbox)
    args = ap.parse_args(argv)
    if args.fn in (cmd_add, cmd_import_captured, cmd_import_mbox):
        with statefile.locked(os.path.join(args.dir, MANIFEST)):  # one load-change-save at a time
            return args.fn(args)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
