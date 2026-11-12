#!/usr/bin/env python3
"""capture: learn from the author's edits and comments, with no model call.

The author corrects drafts in four places: he pastes a draft back into chat with
his changes made in place, he comments on a deck a session sent him and hands it
back, he edits a file a session wrote, and he edits an email draft before sending
it. This reads each, pairs what the session wrote with what the author made of
it, and turns the changed phrases into candidates for the corrections ledger.
Nothing reaches the ledger until the author accepts it, and nothing becomes a
rule until he promotes it. Design: docs/outbound-gate.md, section 2.

    capture.py run      --config gate.json [--since 2026-09-13] [--dry-run]
    capture.py prompt   --config gate.json        # UserPromptSubmit hook: copy comments out of attached decks
    capture.py report   --config gate.json [--days 7] [--json]   # for the daily page
    capture.py accept   --config gate.json ID|GROUP ...   # into the ledger, then trial
    capture.py reject   --config gate.json ID|GROUP ... [--reason "..."]

Sources, in order (the author, 2026-11-12: "most of the input for training will
be my edits and comments"):

    chat      Claude Code transcripts of both seats. A message that pastes back the
              assistant's text with changes (two sentences matching at 0.6 word
              overlap or more, one of them changed) under a lead-in naming an edit,
              or with no lead-in; a `change "X" to "Y"` line in his own typed text.
    comments  Comments by the author in .key and .pptx decks (decks a session sent
              him and he handed back; Google Slides exports), and chat messages that
              comment on a named slide. Sorted wording, fact, design or content;
              only wording becomes a candidate (a judgment record).
    slides    A deck the author saved by hand (pptx revision above its build
              snapshot, or a .key matched to one) diffed slide by slide.
    files     Gate-logged file writes whose file the author changed afterwards.
    gmail     Gate-logged Gmail drafts paired with the sent message, read from the
              nightly Google session's transcript (tool results are verbatim there).

Everything lands in the config's ``log_dir`` (ignored by git): candidates.jsonl,
comments.jsonl, capture-runs.jsonl (counts per source per run, "failed" when a
reader broke), capture-state.json. Accepted candidates go to the ledger, or to the
private ledger when their source matches the config's private markers.

Stdlib only.
"""
from __future__ import annotations
import argparse
import datetime
import difflib
import glob
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import corrections  # noqa: E402
import decks  # noqa: E402
import gate  # noqa: E402

SOURCES = ("chat", "comments", "slides", "files", "gmail")
COMMENT_ROUTES = ("returned", "pptx", "google-live", "chat")
KINDS = ("wording", "fact", "design", "content")

_REM = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
_TAGS = re.compile(r"<(command-[a-z-]+|local-command-[a-z]+|ide_[a-z_]+)>.*?</\1>", re.S)
_PASTED = re.compile(r"<pasted_content[^>]*>(.*?)</pasted_content[^>]*>", re.S)
_PASTE_TAG = re.compile(r"</?pasted_content[^>]*>")
_WORD = re.compile(r"\w+")
_QUOTES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})
LEAD_EDIT = re.compile(r"\b(revis|rev\b|edit|version|final|i sent|sent this|like this|closer|use this|"
                       r"my changes|changes|rewr|tweak|go back to|mine:)", re.I)
LEAD_OTHER = re.compile(r"\b(feedback|comments?\b|review|adjustments|came back with|what is this|"
                        r"check (this|for)|recommend)", re.I)
NOT_PROSE = re.compile(r"\]\(https?://|^\s*\S+@\S+:\S*\$ |^MacBook|\$ git |^Traceback", re.M)
SLIDE_REF = re.compile(r"\b(?:slides?\s+(\d+)|S(\d{1,2})\b(?=:)|(title|first|last|retro|opening)\s+slide)", re.I)
INSTRUCTION = re.compile(r"""\b(?:change|replace)\s+["“'`](.{2,120}?)["”'`]\s+(?:to|with)\s+["“'`](.{1,160}?)["”'`]"""
                         r"""|["“'`](.{2,120}?)["”'`]\s*(?:->|→)\s*["“'`](.{0,160}?)["”'`]""", re.I)
GREETING = re.compile(r"^\s*(hi|hello|dear|hey)\b", re.I)

SORT_RULES = (
    ("wording", re.compile(r"\b(?:word|wording|worded|words|term|phras\w*|language|wordy|obtuse|cheesy|confus\w*|"
                           r"sounds? like ai|ai speak|ai voice|ai phrase|reads? (?:like|as)|would (?:i )?say|"
                           r"strange|weird|clunky|jargon|tone|voice pass|makes? (?:no )?sense|literally mean|"
                           r"what does this (?:even )?mean|meaning\?|know what \w+ means|instruction for me|"
                           r"state[d]? (?:these |this )?(?:better|more clearly)|change this to|twice in a row|"
                           r"use \w+ if possible|as category\?)", re.I)),
    ("fact", re.compile(r"\b(accura\w*|wrong|incorrect|correct\b|source|data\b|number|is this actually|true\?|"
                        r"does .* work|will not have)\b", re.I)),
    ("design", re.compile(r"\b(table|matrix|callout|layout|box(es)?|visual|colou?r|font|diagram|align\w*|"
                          r"chart placement|missing a side|qr)\b", re.I)),
)


def sort_comment(text: str) -> str:
    for kind, rx in SORT_RULES:
        if rx.search(text):
            return kind
    return "content"


def norm(t: str) -> str:
    t = t.translate(_QUOTES)
    t = re.sub(r"(?m)^\s*>+\s?", "", t)
    return t.replace("**", "")


def wset(s: str) -> frozenset:
    return frozenset(w.lower() for w in _WORD.findall(s))


def ov(a, b) -> float:
    return len(a & b) / max(1, len(a | b))


def sentences(text: str) -> list[str]:
    return [s for s in corrections._sentences(text) if len(wset(s)) >= 3]


def _hash(*parts) -> str:
    return hashlib.sha1("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def _junk(c: dict) -> bool:
    both = c["before"] + " " + c["after"]
    return bool(re.search(r"\]\(|`|^#|\*\*", both)) or c["before"].translate(_QUOTES) == c["after"].translate(_QUOTES)


def pair_changes(draft: str, final: str) -> list[tuple[str, str]]:
    """Sentence pairs whose word overlap is 0.6 or more and below 1: the sentences the
    author changed. Each final sentence is used once."""
    ds = [(s, wset(norm(s))) for s in sentences(norm(draft))]
    out, used = [], set()
    for s in sentences(norm(final)):
        w = wset(s)
        best, bi = 0.0, -1
        for i, (d, dw) in enumerate(ds):
            o = ov(w, dw)
            if o > best:
                best, bi = o, i
        if 0.6 <= best < 1.0 and bi not in used and ds[bi][0].strip() != s.strip():
            used.add(bi)
            out.append((ds[bi][0], s))
    return out


def phrase_candidates(pairs: list[tuple[str, str]]) -> list[dict]:
    out = []
    for a, b in pairs:
        for c in corrections.mine_pairs(a, b):
            if not _junk(c):
                out.append(c)
    return out


def distance(a: str, b: str) -> float:
    return round(1 - difflib.SequenceMatcher(a=a, b=b, autojunk=False).ratio(), 3)


# --- storage --------------------------------------------------------------------------------

class Store:
    def __init__(self, cfg: dict, dry: bool = False):
        self.cfg, self.dry = cfg, dry
        self.dir = cfg["log_dir"]
        os.makedirs(self.dir, exist_ok=True)
        self.cand_path = os.path.join(self.dir, "candidates.jsonl")
        self.comm_path = os.path.join(self.dir, "comments.jsonl")
        self.cands = _read_jsonl(self.cand_path)
        self.comments = _read_jsonl(self.comm_path)
        self.cand_ids = {c["id"] for c in self.cands}
        self.comm_ids = {c["id"] for c in self.comments}
        self.new_cands: list[dict] = []
        self.new_comments: list[dict] = []
        sp = os.path.join(self.dir, "capture-state.json")
        self.state_path = sp
        self.state = {"files": {}, "decks": {}}
        if os.path.exists(sp):
            with open(sp, encoding="utf-8") as fh:
                self.state = json.load(fh)

    def add_candidate(self, source: str, group: str, c: dict, **meta) -> bool:
        cid = "k-" + _hash(source, c["before"], c["after"], c.get("context", ""))[:10]
        if cid in self.cand_ids:
            return False
        rec = {"id": cid, "group": group, "source": source, "date": datetime.date.today().isoformat(),
               "before": c["before"], "after": c["after"], "context": c.get("context", ""),
               "kind": c.get("kind", ""), "status": "pending"}
        rec.update(meta)
        self.cand_ids.add(cid)
        self.new_cands.append(rec)
        return True

    def add_comment(self, rec: dict) -> bool:
        cid = "m-" + _hash(rec.get("deck_family") or rec.get("session"), rec.get("slide_text", "")[:200], rec["text"])[:10]
        if cid in self.comm_ids:
            return False
        rec["id"] = cid
        self.comm_ids.add(cid)
        self.new_comments.append(rec)
        return True

    def save(self):
        if self.dry:
            return
        _append_jsonl(self.cand_path, self.new_cands)
        _append_jsonl(self.comm_path, self.new_comments)
        with open(self.state_path, "w") as fh:
            json.dump(self.state, fh)


def _read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def _append_jsonl(path: str, rows: list[dict]) -> None:
    if rows:
        with open(path, "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _write_jsonl(path: str, rows: list[dict]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


# --- transcripts ------------------------------------------------------------------------------

def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def read_session(path: str, since: str = "") -> tuple[list[tuple], str]:
    """The interactive rows of one transcript: ('u'|'a'|'tool', text, timestamp, extra), and the
    session's cwd. Headless and sdk-origin rows are left out; tool rows carry Bash commands."""
    rows, cwd = [], ""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not _ROW.search(line[:400]) and not _ROW.search(line):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("isSidechain"):
                continue
            if d.get("entrypoint") not in ("claude-desktop", "cli"):
                return [], ""
            cwd = cwd or d.get("cwd") or ""
            ts = d.get("timestamp", "")
            c = (d.get("message") or {}).get("content")
            if d.get("type") == "user":
                if d.get("isMeta") or d.get("turnOrigin") not in (None, "human"):
                    continue
                if isinstance(c, list) and c and all(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                    continue
                raw = _TAGS.sub("", _REM.sub("", _text_of(c))).strip()
                if raw and not raw.startswith("This session is being continued"):
                    rows.append(("u", raw, ts, d.get("uuid")))
            else:
                txt = _text_of(c).strip()
                if txt:
                    rows.append(("a", txt, ts, None))
                if isinstance(c, list):
                    for b in c:
                        if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Bash":
                            rows.append(("tool", (b.get("input") or {}).get("command", ""), ts, None))
    return rows, cwd


def chat_source(cfg: dict, store: Store, since: str, snaps: list[dict], stats: dict) -> None:
    for root in cfg.get("transcripts", []):
        for f in glob.glob(os.path.join(root, "*", "*.jsonl")):
            try:
                mt = os.path.getmtime(f)
                if os.path.getsize(f) < 2000:
                    continue
            except OSError:
                continue
            prev = store.state["files"].get(f) or {}
            if since and datetime.datetime.fromtimestamp(mt).isoformat() < since:
                continue
            if prev and mt <= prev.get("mtime", 0):
                continue
            rows, cwd = read_session(f)
            if not rows:
                store.state["files"][f] = {"mtime": mt, "ts": prev.get("ts", "")}
                continue
            _chat_session(cfg, store, f, cwd, rows, since, prev.get("ts", ""), snaps, stats)
            newest = max((r[2] for r in rows if r[0] == "u"), default=prev.get("ts", ""))
            store.state["files"][f] = {"mtime": mt, "ts": newest}


def _chat_session(cfg, store, f, cwd, rows, since, done, snaps, stats):
    asent: list[tuple] = []
    blocks: list[str] = []
    tool_text = []
    fiction_path = "el-loco-lobo" in f or "el_loco_lobo" in f
    for kind, txt, ts, uid in rows:
        if kind == "a":
            blocks.append(txt)
            for s in sentences(norm(txt)):
                asent.append((wset(s), s, len(blocks) - 1))
            asent = asent[-2000:]
            continue
        if kind == "tool":
            tool_text.append(txt)
            continue
        if (since and ts[:10] < since[:10]) or (done and ts <= done):
            continue
        stats["messages"] += 1
        own = _PASTED.sub(" ", txt)
        full = _PASTE_TAG.sub("", txt)
        group = "g-" + _hash(f, uid or ts)[:8]
        private = gate.is_private(cfg, full, cwd, f)
        fiction = fiction_path or bool(re.search(r"(?m)^(Yours|Mine):", full))
        origin = {"transcript": f, "ts": ts, "cwd": cwd}
        # 1. paste-back with edits
        us = sentences(norm(full))
        matched = []
        for i, s in enumerate(us):
            w = wset(s)
            best, bb, bs = 0.0, None, ""
            for aw, a_s, bi in asent:
                o = ov(w, aw)
                if o > best:
                    best, bb, bs = o, bi, a_s
            if best >= 0.6:
                matched.append((i, best, bs))
        changed = [m for m in matched if m[1] < 0.999]
        if len(matched) >= 2 and changed and not fiction:
            first = matched[0][0]
            full_n = " ".join(norm(full).split())
            probe = " ".join(us[first].split())[:40]
            lead_txt = full_n[: full_n.find(probe)] if probe in full_n else ""
            lead_txt = lead_txt[-300:]
            lead = "other" if LEAD_OTHER.search(lead_txt) else "edit" if LEAD_EDIT.search(lead_txt) else "none"
            span = "\n".join(us[matched[0][0]: matched[-1][0] + 1])
            if lead != "other" and not (lead == "none" and NOT_PROSE.search(full)):
                pairs = [(bs, us[i]) for i, o, bs in changed]
                surface = "slides" if SLIDE_REF.search(own) else ("email" if GREETING.search(span) else "post")
                n = 0
                for c in phrase_candidates(pairs):
                    n += store.add_candidate("chat", group, c, surface=surface, lead=lead, private=private,
                                             origin=origin, distance=distance(" ".join(p[0] for p in pairs),
                                                                              " ".join(p[1] for p in pairs)))
                stats["pastebacks"] += 1
                stats["candidates"] += n
            continue
        # 2. an instruction in his own words
        for m in INSTRUCTION.finditer(own):
            x, y = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            if x and any(x.lower() in b.lower() for b in blocks[-30:]):
                ctx = next((s for _, s, _ in reversed(asent) if x.lower() in s.lower()), x)
                if store.add_candidate("chat", group, {"before": x, "after": y or "", "context": ctx, "kind": ""},
                                       surface="post", lead="instruction", private=private, origin=origin):
                    stats["candidates"] += 1
        # 3. a comment on a named slide, without text pasted back
        sm = SLIDE_REF.search(own)
        if sm and len(own.split()) <= 120 and not fiction:
            n_slide = int(sm.group(1) or sm.group(2)) if (sm.group(1) or sm.group(2)) else None
            before, after, deck = _slide_from_snapshots(snaps, tool_text, ts, n_slide)
            rec = {"route": "chat", "text": own.strip(), "kind": sort_comment(own), "slide": n_slide,
                   "slide_text": before, "response_text": after, "deck": deck, "session": f, "ts": ts,
                   "author": "", "private": private}
            if store.add_comment(rec):
                stats["comments"] += 1
                if rec["kind"] == "wording":
                    store.add_candidate("comments", group, {"before": before or own.strip(), "after": after,
                                                            "context": before, "kind": "judgment"},
                                        surface="slides", lead="comment", private=private, origin=origin,
                                        comment=own.strip(), route="chat")


def _slide_from_snapshots(snaps, tool_text, ts, n):
    """The named slide before and after a chat comment, from builds of a deck whose path the
    session's own Bash calls mention."""
    if not n or not snaps:
        return "", "", ""
    joined = "\n".join(tool_text)
    mine = [s for s in snaps if os.path.basename(s["path"]) in joined or os.path.dirname(s["path"]) in joined]
    if not mine:
        return "", "", ""
    when = _ts_epoch(ts)
    before = [s for s in mine if s["t"] <= when]
    after = [s for s in mine if s["t"] > when]
    get = lambda s: next((x["text"] for x in s["slides"] if x["n"] == n), "") if s else ""  # noqa: E731
    b = before[-1] if before else None
    a = after[0] if after else None
    return get(b), get(a), (b or a)["path"]


def _ts_epoch(ts: str) -> float:
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


# --- decks: comments and hand-saved edits ---------------------------------------------------

_FAMILY = re.compile(r"(?i)(?:[ _-]*comments?|[ _-]*brian-edits.*|[ _-]\d{4}-\d{2}-\d{2}\w*|\s*\(\d+\)|[ _]\d{1,2})+$")
_ROW = re.compile(r'"type":\s*"(?:user|assistant)"')


def family(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    return _FAMILY.sub("", stem).strip().lower()


def find_decks(cfg: dict) -> list[str]:
    out = []
    skip = {"node_modules", ".git", ".venv", "worktrees", "site-packages", "_to_delete", "outputs"}
    for root in cfg.get("deck_roots", []):
        if not os.path.isdir(root):
            continue
        os.listdir(root)  # a root the job may not read (macOS privacy) fails the source instead of looking empty
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d not in skip and not d.endswith((".key", ".app"))]
            if "/.claude/sessions" in dp or "/Index" in dp:
                continue
            for f in fn:
                if f.lower().endswith((".pptx", ".key")) and not f.startswith("~$"):
                    p = os.path.join(dp, f)
                    try:
                        if os.path.getsize(p) > 500:
                            out.append(p)
                    except OSError:
                        pass
    return out


def _git_versions(path: str) -> list[tuple[float, str, str]]:
    """(commit time, commit, repo-relative path) for every commit of a tracked file."""
    import subprocess
    d = os.path.dirname(path)
    try:
        top = subprocess.run(["git", "-C", d, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             timeout=20).stdout.strip()
        if not top:
            return []
        rel = os.path.relpath(path, top)
        log = subprocess.run(["git", "-C", top, "log", "--format=%ct %h", "--", rel], capture_output=True,
                             text=True, timeout=20).stdout.split("\n")
    except (OSError, subprocess.SubprocessError):
        return []
    return [(float(t), h, rel) for t, h in (ln.split() for ln in log if ln.strip())]


def _deck_at(path: str, commit: str, rel: str) -> dict | None:
    import subprocess
    import tempfile
    top = subprocess.run(["git", "-C", os.path.dirname(path), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, timeout=20).stdout.strip()
    data = subprocess.run(["git", "-C", top, "show", f"{commit}:{rel}"], capture_output=True, timeout=60).stdout
    if not data:
        return None
    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(path)[1])
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return decks.read(tmp)
    except (OSError, ValueError, KeyError):
        return None
    finally:
        os.unlink(tmp)


def next_version(deck_path: str, mtime: float, all_decks: list[str], cache: dict) -> tuple[dict | None, str]:
    """The next build of the deck this file came from: a builder output of the same family in a
    repository, at the first commit after ``mtime``, else its current file when newer; else the
    newest other deck of the family. Returns (deck, label)."""
    fam = family(deck_path)
    same = [p for p in all_decks if p != deck_path and family(p) == fam]
    for p in sorted(same, key=lambda p: "/code/" not in p):
        if "/code/" not in p:
            break
        key = ("git", p)
        if key not in cache:
            cache[key] = _git_versions(p)
        later = sorted(v for v in cache[key] if v[0] > mtime)
        if later:
            t, h, rel = later[0]
            k2 = ("at", p, h)
            if k2 not in cache:
                cache[k2] = _deck_at(p, h, rel)
            if cache[k2]:
                return cache[k2], f"{os.path.basename(p)} at {h}"
        if os.path.getmtime(p) > mtime:
            try:
                return decks.read(p), os.path.basename(p) + " (current)"
            except (OSError, ValueError, KeyError):
                pass
    newer = [p for p in same if os.path.getmtime(p) > mtime]
    if newer:
        p = max(newer, key=os.path.getmtime)
        try:
            return decks.read(p), os.path.basename(p)
        except (OSError, ValueError, KeyError):
            return None, ""
    return None, ""


def comments_source(cfg: dict, store: Store, since: str, stats: dict, paths: list[str] | None = None) -> None:
    authors = set(cfg.get("author_names", ["Brian Moriarty"]))
    all_decks = find_decks(cfg) if paths is None else paths
    cache: dict = {}
    for p in all_decks:
        try:
            mt = os.path.getmtime(p)
            sig = f"{mt}:{os.path.getsize(p)}"
        except OSError:
            continue
        if store.state["decks"].get(p) == sig:
            continue
        try:
            doc = decks.read(p)
        except Exception:  # an unreadable deck is counted, never fatal
            stats["unreadable"] += 1
            continue
        store.state["decks"][p] = sig
        mine = [c for c in doc["comments"] if c["author"] in authors and c["text"]]
        if not mine:
            continue
        route = "pptx" if doc["format"] == "pptx" and doc.get("google") else "returned"
        stats["decks_with_comments"] += 1
        nxt, label = next_version(p, mt, all_decks, cache)
        private = gate.is_private(cfg, p)
        group = "g-" + _hash(family(p), "comments")[:8]
        for c in mine:
            resp = ""
            if nxt and c["slide_text"]:
                i, o = decks.best_match(c["slide_text"], nxt["slides"])
                resp = nxt["slides"][i]["text"] if i >= 0 and o >= 0.3 else ""
            rec = {"route": route, "text": c["text"], "kind": sort_comment(c["text"]), "slide": c["slide"],
                   "slide_text": c["slide_text"], "response_text": resp, "response_deck": label,
                   "deck": p, "deck_family": family(p), "deck_sha256": _file_sha(p),
                   "ts": datetime.datetime.fromtimestamp(mt).isoformat(timespec="seconds"),
                   "author": c["author"], "private": private}
            if not store.add_comment(rec):
                continue
            stats["comments"] += 1
            stats["kind_" + rec["kind"]] += 1
            if rec["kind"] == "wording":
                if store.add_candidate("comments", group, {"before": c["slide_text"][:400] or c["text"],
                                                           "after": resp[:400], "context": c["slide_text"][:400],
                                                           "kind": "judgment"},
                                       surface="slides", lead="comment", private=private, comment=c["text"],
                                       route=route, origin={"deck": p, "slide": c["slide"]}):
                    stats["candidates"] += 1
        _hand_edits(cfg, store, p, doc, mt, stats, private)


def _file_sha(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _hand_edits(cfg, store, path, doc, mtime, stats, private):
    """Slides source: a deck the author saved by hand, against the snapshot of the deck as sent."""
    import deckcheck
    snaps = [s for s in deckcheck.all_snapshots(cfg) if s["t"] < mtime]
    if not snaps:
        return
    if doc["format"] == "pptx":
        own = [s for s in snaps if s["path"] == os.path.abspath(path)]
        if not own or doc["revision"] <= max(s.get("revision", 1) for s in own):
            return
        base = own[-1]
    else:  # a returned .key: the snapshot sharing most slide text
        def score(s):
            return sum(decks.best_match(x["text"], s["slides"])[1] for x in doc["slides"][:12])
        base = max(snaps, key=score)
        if score(base) / max(1, min(12, len(doc["slides"]))) < 0.5:
            return
    group = "g-" + _hash(path, "edits", mtime)[:8]
    pairs = []
    for s in doc["slides"]:
        i, o = decks.best_match(s["text"], base["slides"])
        if i >= 0 and 0.6 <= o < 1.0:
            pairs.extend(pair_changes(base["slides"][i]["text"], s["text"]))
    for c in phrase_candidates(pairs):
        if store.add_candidate("slides", group, c, surface="slides", lead="edit", private=private,
                               origin={"deck": path, "snapshot": base["path"]}):
            stats["candidates"] += 1
    stats["hand_saved"] += 1


# --- files and gmail from the gate log ------------------------------------------------------

def files_source(cfg: dict, store: Store, log: list[dict], stats: dict) -> None:
    last: dict = {}
    for e in log:
        if e.get("type") == "gate" and e.get("kind") == "file" and e.get("verdict") in ("pass", "ask"):
            last[e["target"]] = e
    for path, e in last.items():
        key = "file:" + path
        if store.state["files"].get(key) == e["t"]:
            continue
        try:
            if os.path.getmtime(path) <= e["t"] + 1:
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                now = fh.read()
        except OSError:
            continue
        store.state["files"][key] = e["t"]
        pairs = pair_changes(e.get("text", ""), now)
        if not pairs:
            continue
        group = "g-" + _hash(path, e["t"])[:8]
        for c in phrase_candidates(pairs):
            if store.add_candidate("files", group, c, surface=e.get("surface") or "post", lead="edit",
                                   private=bool(e.get("private")), origin={"path": path, "ts": e.get("ts")},
                                   distance=distance(e.get("text", ""), now)):
                stats["candidates"] += 1
        stats["edited"] += 1


def google_results(cfg: dict) -> list[dict]:
    """Tool results from the nightly Google session: transcripts whose first user message carries
    the marker. Returned verbatim: [{'tool', 'input', 'result', 'ts'}]."""
    marker = cfg.get("google_session_marker", "pherkad-google-capture")
    out = []
    for root in cfg.get("transcripts", []):
        for f in glob.glob(os.path.join(root, "*", "*.jsonl")):
            try:
                if time.time() - os.path.getmtime(f) > 3 * 86400:
                    continue
                with open(f, encoding="utf-8", errors="replace") as fh:
                    head = fh.read(200_000)
                if marker not in head or not _opens_with(f, marker):
                    continue
                calls, rows = {}, []
                with open(f, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        try:
                            d = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        for b in (d.get("message") or {}).get("content") or []:
                            if not isinstance(b, dict):
                                continue
                            if b.get("type") == "tool_use":
                                calls[b.get("id")] = (b.get("name"), b.get("input"))
                            elif b.get("type") == "tool_result" and b.get("tool_use_id") in calls:
                                name, inp = calls[b["tool_use_id"]]
                                rows.append({"tool": name, "input": inp, "result": b.get("content"),
                                             "ts": d.get("timestamp", "")})
                out.extend(rows)
            except OSError:
                continue
    return out


def _opens_with(path: str, marker: str) -> bool:
    """Whether the session's first user message starts with the marker (a session that only
    talks about the marker does not count)."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not _ROW.search(line):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") == "user":
                return _text_of((d.get("message") or {}).get("content")).lstrip().startswith(marker)
    return False


def _result_json(res):
    if isinstance(res, list):
        res = "\n".join(b.get("text", "") for b in res if isinstance(b, dict))
    if isinstance(res, str):
        try:
            return json.loads(res)
        except json.JSONDecodeError:
            return res
    return res


def _sent_bodies(obj, out: list) -> None:
    """Every sent message in a get_thread result: {'threadId', 'body', 'date'}."""
    if isinstance(obj, dict):
        labels = obj.get("labelIds") or obj.get("labels") or []
        body = obj.get("plaintextBody") or obj.get("body") or obj.get("text")
        if body and isinstance(body, str) and ("SENT" in labels or obj.get("isSent")):
            out.append({"threadId": obj.get("threadId"), "body": body, "date": obj.get("date") or obj.get("internalDate")})
        for v in obj.values():
            _sent_bodies(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _sent_bodies(v, out)


def gmail_source(cfg: dict, store: Store, log: list[dict], stats: dict, results: list[dict]) -> None:
    import samples
    drafts = {}
    by_use = {e.get("tool_use_id"): e for e in log if e.get("type") == "gate" and e.get("kind") == "gmail"}
    for e in log:
        if e.get("type") == "result" and e.get("tool_use_id") in by_use:
            th = (e.get("result") or {}).get("threadId")
            if th:
                drafts[th] = by_use[e["tool_use_id"]]
    if not drafts:
        return
    sent = []
    for r in results:
        if (r.get("tool") or "").endswith("get_thread"):
            _sent_bodies(_result_json(r.get("result")), sent)
    for m in sent:
        e = drafts.get(m.get("threadId"))
        if not e or ("gmail:" + m["threadId"]) in store.state["files"]:
            continue
        store.state["files"]["gmail:" + m["threadId"]] = e["t"]
        body = samples.strip_reply(m["body"])
        draft = e.get("text", "")
        pairs = pair_changes(draft, body)
        group = "g-" + _hash("gmail", m["threadId"])[:8]
        for c in phrase_candidates(pairs):
            if store.add_candidate("gmail", group, c, surface="email", lead="edit", private=bool(e.get("private")),
                                   origin={"threadId": m["threadId"]}, distance=distance(draft, body)):
                stats["candidates"] += 1
        stats["paired"] += 1


def google_comments(cfg: dict, store: Store, stats: dict, results: list[dict]) -> None:
    """Live Google Slides comments from read_file_content(includeComments) results. The text
    format is the connector's and may change; a result with comment markers that yields
    nothing is counted as a parse failure."""
    for r in results:
        if not (r.get("tool") or "").endswith("read_file_content"):
            continue
        res = _result_json(r.get("result"))
        text = res if isinstance(res, str) else json.dumps(res)
        found = 0
        for m in re.finditer(r"(?im)^\s*(?:comment|\[comment[^\]]*\])\s*(?:by\s+)?([^:\n]{0,60}):\s*(.+)$", text):
            who, body = m.group(1).strip(), m.group(2).strip()
            if who and who not in cfg.get("author_names", ["Brian Moriarty"]):
                continue
            rec = {"route": "google-live", "text": body, "kind": sort_comment(body), "slide": None, "slide_text": "",
                   "response_text": "", "deck": (r.get("input") or {}).get("fileId", ""), "ts": r.get("ts"),
                   "author": who, "private": gate.is_private(cfg, text[:2000])}
            if store.add_comment(rec):
                found += 1
                stats["comments"] += 1
        if "comment" in text.lower() and not found:
            stats["parse_misses"] += 1


# --- the run --------------------------------------------------------------------------------

def run(cfg: dict, since: str = "", dry: bool = False, only: tuple = SOURCES) -> dict:
    import deckcheck
    store = Store(cfg, dry)
    snaps = deckcheck.all_snapshots(cfg)
    log = gate.recent_log(cfg, max_bytes=50_000_000)
    out = {"date": datetime.date.today().isoformat(), "t": time.time(), "since": since, "sources": {}}
    readers = {
        "chat": lambda st: chat_source(cfg, store, since, snaps, st),
        "comments": lambda st: comments_source(cfg, store, since, st),
        "slides": lambda st: None,  # hand-saved decks are diffed inside the comments pass, which reads every deck
        "files": lambda st: files_source(cfg, store, log, st),
        "gmail": None,
    }
    results = None
    for src in SOURCES:
        if src not in only:
            continue
        st: dict = {}
        from collections import Counter
        st = Counter()
        try:
            if src == "gmail":
                results = google_results(cfg) if results is None else results
                gmail_source(cfg, store, log, st, results)
                google_comments(cfg, store, st, results)
            else:
                readers[src](st)
            out["sources"][src] = {"status": "ok", **st}
        except Exception as exc:  # a broken reader shows as failed, never as zero
            out["sources"][src] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    # candidates from hand-saved decks are filed under slides even though one pass found them
    out["sources"].setdefault("slides", {"status": "ok"})
    out["sources"]["slides"]["candidates"] = sum(1 for c in store.new_cands if c["source"] == "slides")
    out["sources"]["slides"]["hand_saved"] = out["sources"].get("comments", {}).get("hand_saved", 0)
    if "comments" in out["sources"] and out["sources"]["comments"].get("status") == "ok":
        out["sources"]["comments"]["candidates"] = sum(1 for c in store.new_cands if c["source"] == "comments")
    out["new_candidates"] = len(store.new_cands)
    out["new_comments"] = len(store.new_comments)
    store.save()
    if not dry:
        _append_jsonl(os.path.join(cfg["log_dir"], "capture-runs.jsonl"), [out])
    return out


# --- the prompt hook ------------------------------------------------------------------------

_AT_PATH = re.compile(r"""@"([^"]+\.(?:key|pptx))"|@(/\S+\.(?:key|pptx))\b""", re.I)


def prompt_hook(cfg: dict, payload: dict) -> int:
    """UserPromptSubmit: copy the comments and slide text out of every deck the message
    attaches by @-path, before the file in Downloads can be cleaned away."""
    text = payload.get("prompt") or ""
    paths = [a or b for a, b in _AT_PATH.findall(text)]
    if not paths:
        return 0
    store = Store(cfg)
    st = {"comments": 0, "candidates": 0, "decks_with_comments": 0, "unreadable": 0, "hand_saved": 0}
    from collections import Counter
    st = Counter(st)
    existing = [p for p in paths if os.path.exists(p)]
    comments_source(cfg, store, "", st, paths=existing)
    os.makedirs(os.path.join(cfg["log_dir"], "returned"), exist_ok=True)
    for p in existing:
        try:
            doc = decks.read(p)
            with open(os.path.join(cfg["log_dir"], "returned", _file_sha(p)[:16] + ".json"), "w", encoding="utf-8") as fh:
                json.dump({"path": p, "t": time.time(), "session": payload.get("session_id"), "message": text[:500],
                           "slides": doc["slides"], "comments": doc["comments"]}, fh, ensure_ascii=False)
        except Exception:
            continue
    store.save()
    return 0


# --- accept, reject, report -------------------------------------------------------------------

def _select(cands: list[dict], ids: list[str]) -> list[dict]:
    want = set(ids)
    return [c for c in cands if c["id"] in want or c["group"] in want]


def accept(cfg: dict, ids: list[str], trial: bool = True) -> list[str]:
    path = os.path.join(cfg["log_dir"], "candidates.jsonl")
    cands = _read_jsonl(path)
    chosen = [c for c in _select(cands, ids) if c["status"] == "pending"]
    added = []
    for ledger_key in ("ledger", "private_ledger"):
        batch = [c for c in chosen if bool(c.get("private")) == (ledger_key == "private_ledger")]
        if not batch:
            continue
        lp = cfg[ledger_key]
        records = corrections.load_ledger(lp)
        for c in batch:
            if any(r["before"].lower() == c["before"].lower() and r.get("status") not in ("retired", "rejected")
                   for r in records):
                c["status"] = "duplicate"
                continue
            guess = c["kind"] or corrections.classify(c["before"], c["after"], c["context"])
            kind = c["kind"] if c["kind"] in ("judgment", "structural") else ""
            src = f"capture {c['source']} {c['group']} ({c['date']})"
            r = {"id": corrections._new_id(records), "date": corrections._today(), "before": c["before"],
                 "after": c["after"], "context": c["context"], "source": src, "surface": c.get("surface", ""),
                 "kind": kind, "suggested_kind": guess, "rationale": c.get("comment", ""), "status": "pending",
                 "rule_id": "", "supersedes": "", "history": []}
            corrections._note(r, f"accepted from capture candidate {c['id']}")
            records.append(r)
            c["status"] = "accepted"
            c["ledger_id"] = r["id"]
            added.append((lp, r["id"], guess, kind))
        corrections.save_ledger(lp, records)
    _write_jsonl(path, cands)
    if trial:
        corpus = cfg.get("corpus") or {}
        for lp, rid, guess, kind in added:
            if kind or guess not in corrections.RULE_KINDS or not corpus.get("dirs"):
                continue
            args = ["trial", "--ledger", lp, rid, *corpus["dirs"], "--kind", guess]
            if corpus.get("config"):
                args += ["--config", corpus["config"]]
            if corpus.get("exclude"):
                args += ["--exclude", corpus["exclude"]]
            try:
                corrections.main(args)
            except SystemExit:
                pass
    return [rid for _, rid, _, _ in added]


def reject(cfg: dict, ids: list[str], reason: str = "") -> int:
    path = os.path.join(cfg["log_dir"], "candidates.jsonl")
    cands = _read_jsonl(path)
    n = 0
    for c in _select(cands, ids):
        if c["status"] == "pending":
            c["status"] = "rejected"
            c["reason"] = reason
            n += 1
    _write_jsonl(path, cands)
    return n


def report(cfg: dict, days: int = 7) -> dict:
    """Everything the daily page needs: pending candidates grouped for section 1, pending ledger
    records with their commands, and the per-day counts for section 5."""
    d = cfg["log_dir"]
    cands = _read_jsonl(os.path.join(d, "candidates.jsonl"))
    comments = _read_jsonl(os.path.join(d, "comments.jsonl"))
    runs = _read_jsonl(os.path.join(d, "capture-runs.jsonl"))
    log = gate.recent_log(cfg, max_bytes=50_000_000)
    tool = os.path.join(HERE, "capture.py")
    groups: dict = {}
    for c in cands:
        if c["status"] != "pending":
            continue
        g = groups.setdefault(c["group"], {"group": c["group"], "source": c["source"], "lead": c.get("lead"),
                                           "private": bool(c.get("private")), "surface": c.get("surface"),
                                           "comment": c.get("comment", ""), "items": []})
        g["items"].append({"id": c["id"], "before": c["before"], "after": c["after"], "kind": c["kind"]})
    for g in groups.values():
        g["accept"] = f"python3 {tool} accept --config {cfg['_path']} {g['group']}"
        g["reject"] = f"python3 {tool} reject --config {cfg['_path']} {g['group']}"
    ledger_rows = []
    for key in ("ledger", "private_ledger"):
        lp = cfg.get(key)
        if not lp or not os.path.exists(lp):
            continue
        for r in corrections.load_ledger(lp):
            if r.get("status") not in ("pending", "trialled"):
                continue
            t = r.get("trial") or {}
            cmd = (f"python3 {os.path.join(HERE, 'corrections.py')} promote --ledger {lp} {r['id']} "
                       f"--overlay {os.path.join(HERE, 'voice_config.json')} --prose {os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), 'voice-rules.md')}")
            ledger_rows.append({"id": r["id"], "before": r["before"], "after": r["after"], "kind": r.get("kind") or r.get("suggested_kind", ""),
                                "status": r["status"], "private": key == "private_ledger", "source": r.get("source", ""),
                                "trial": {"hits": t.get("hits"), "per_1k_words": t.get("per_1k_words"),
                                          "problems": len(t.get("example_problems") or [])} if t else None,
                                "promote": cmd,
                                "retire": f"python3 {os.path.join(HERE, 'corrections.py')} retire --ledger {lp} {r['id']} --reason \"...\""})
    today = datetime.date.today()
    per_day = []
    for k in range(days):
        day = (today - datetime.timedelta(days=k)).isoformat()
        g = [e for e in log if e.get("type") in ("gate", "deck") and (e.get("ts") or "")[:10] == day]
        row = {"date": day, "gated": len(g), "passed": sum(e.get("verdict") == "pass" for e in g),
               "blocked": sum(e.get("verdict") == "block" for e in g), "asked": sum(e.get("verdict") == "ask" for e in g),
               "failed": sum(e.get("verdict") == "error" for e in g)}
        run_today = [r for r in runs if r.get("date") == day]
        for src in SOURCES:
            if not run_today:
                row[src] = None
            else:
                s = run_today[-1]["sources"].get(src) or {}
                row[src] = "failed" if s.get("status") == "failed" else sum(
                    c["source"] == src and c["date"] == day for c in cands)
        row["accepted"] = sum(c["status"] == "accepted" and c.get("date") == day for c in cands)
        dist = [c["distance"] for c in cands if c.get("date") == day and isinstance(c.get("distance"), float)]
        row["mean_distance"] = round(sum(dist) / len(dist), 3) if dist else None
        per_day.append(row)
    ckinds = {route: {k: sum(1 for c in comments if c.get("route") == route and c.get("kind") == k) for k in KINDS}
              for route in COMMENT_ROUTES}
    return {"groups": sorted(groups.values(), key=lambda g: (g["source"], g["lead"] != "edit")),
            "pending_candidates": sum(len(g["items"]) for g in groups.values()),
            "ledger": ledger_rows, "per_day": per_day, "comments_by_route": ckinds,
            "last_run": runs[-1] if runs else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="learn from the author's edits and comments")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "prompt", "report", "accept", "reject"):
        p = sub.add_parser(name)
        p.add_argument("--config")
        if name == "run":
            p.add_argument("--since", default="", help="ISO date: read nothing older (the backfill window)")
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--only", default=",".join(SOURCES))
        if name == "report":
            p.add_argument("--days", type=int, default=7)
            p.add_argument("--json", action="store_true")
        if name in ("accept", "reject"):
            p.add_argument("ids", nargs="+")
        if name == "accept":
            p.add_argument("--no-trial", action="store_true")
        if name == "reject":
            p.add_argument("--reason", default="")
    args = ap.parse_args(argv)
    if args.cmd == "prompt":
        try:
            cfg = gate.load_config(args.config)
            return prompt_hook(cfg, json.load(sys.stdin))
        except Exception as exc:  # fail open, loudly
            print(json.dumps({"systemMessage": f"capture did not copy the attached deck's comments: {type(exc).__name__}: {exc}"}))
            return 0
    cfg = gate.load_config(args.config)
    if args.cmd == "run":
        out = run(cfg, args.since, args.dry_run, tuple(s for s in args.only.split(",") if s))
        print(json.dumps(out, indent=2))
        return 1 if any(s.get("status") == "failed" for s in out["sources"].values()) else 0
    if args.cmd == "report":
        r = report(cfg, args.days)
        if args.json:
            print(json.dumps(r, indent=2, ensure_ascii=False))
        else:
            print(f"{r['pending_candidates']} pending candidate(s) in {len(r['groups'])} group(s); "
                  f"{len(r['ledger'])} ledger record(s) awaiting a decision")
            for g in r["groups"][:20]:
                print(f"  {g['group']} {g['source']} lead={g['lead']} items={len(g['items'])}"
                      + (" private" if g["private"] else ""))
        return 0
    if args.cmd == "accept":
        ids = accept(cfg, args.ids, trial=not args.no_trial)
        print(f"accepted {len(ids)} into the ledger: {', '.join(ids)}" if ids else "nothing pending matched")
        return 0
    n = reject(cfg, args.ids, args.reason)
    print(f"rejected {n} candidate(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
