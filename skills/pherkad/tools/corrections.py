#!/usr/bin/env python3
"""corrections: from "X -> Y" to a tested, counted rule, with one approval.

Roadmap item 10. The author's corrections arrive as terse edits and were
transcribed by hand into the mined-corrections sections of voice-rules.md;
some of them later became config rules, most did not, and none carried a
count. This is the ledger and the pipeline.

    corrections.py add     --ledger F --before "X" --after "Y" [--context "..."] [--source "..."]
                           [--surface S] [--kind K] [--rationale "..."] [--severity warning|error]
    corrections.py mine    DRAFT EDITED --ledger F [--source "..."] [--surface S] [--dry-run]
    corrections.py trial   --ledger F ID DIR... [--config OVERLAY] [--contexts N]
    corrections.py promote --ledger F ID --overlay OVERLAY.json [--prose voice-rules.md] [--source "..."]
    corrections.py list    --ledger F [--status S]
    corrections.py show    --ledger F ID
    corrections.py retire  --ledger F ID --reason "..."

The ledger is a JSONL file, one record per correction, project-owned and
never part of this repository. A record:

    {"id": "c-20260915-a1b2", "date": "...", "before": "X", "after": "Y",
     "context": "the sentence it was in", "source": "email to Steve, 2026-09-15",
     "surface": "email", "kind": "literal", "rationale": "...",
     "field": "soft_phrases", "matcher": "x", "severity": "warning",
     "fires": [...], "clean": [...], "status": "pending", "rule_id": "",
     "trial": {...}, "supersedes": "", "history": [...]}

Kinds, and what promote does with each:
    literal     a phrase; becomes a banned (error) or soft (warning) entry
    templated   a phrase with [word]/[verb]/[det] slots or a re: regex; the same
    structural  a shape with no string; goes to prose only, marked for structlint
    judgment    a recast of meaning or register; prose only, judgment-only
    preference  a positive wording preference ("reusable instrument" over
                "reusable surface"); prose only, never a ban
    factual     a fact was wrong; never a style rule, prose only if asked
    exception   a literal use that should not fire; prose only, and the
                per-occurrence answer is pherkad.py decide

The invariant: nothing is promoted to a rule without a trial. ``trial`` runs
the candidate matcher over a corpus (corpusscan under the hood), stores hits,
files, rate per 1,000 words, and sampled contexts on the record, and checks
that every ``fires`` example fires and every ``clean`` example does not.
``promote`` refuses a record that has not been trialled, and refuses a rule
for a factual correction however often it recurs. The one required decision
is the author's: read the trial, then promote, narrow, or mark judgment-only.

``promote`` writes three things from one record: the overlay entry (an
``add_<field>`` object with id, pattern, rationale, since, fires, clean), the
fixtures (those same examples, which ``pherkad.py check-overlay`` runs), and
the mined-corrections line in the prose file. The prose is generated from the
record; the record is the transaction log.

Stdlib only.
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import voicelint  # noqa: E402
import statefile  # noqa: E402
import corpusscan  # noqa: E402

KINDS = ("literal", "templated", "structural", "judgment", "preference", "factual", "exception")
RULE_KINDS = ("literal", "templated")
STATUSES = ("pending", "trialled", "promoted", "judgment-only", "preference", "rejected", "retired")
_FIELD_FOR = {"error": "banned_phrases", "warning": "soft_phrases"}


def _today() -> str:
    return datetime.date.today().isoformat()


def _fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    sys.stderr.write(f"corrections: {msg}\n")
    sys.exit(2)


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------
def load_ledger(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                _fail(f"{path}:{n} is not valid JSON: {exc}")
    seen = set()
    for r in out:  # two records under one id made find() return whichever came first (I184)
        if r.get("id") in seen:
            _fail(f"{path}: two records share the id {r['id']!r}; give one a new id by hand")
        seen.add(r.get("id"))
    return out


def save_ledger(path: str, records: list[dict]) -> None:
    statefile.write_text(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    real = os.path.realpath(path)
    if real != os.path.abspath(path):
        # the ledger is a link into another repository; the write lands there, and so must the commit (I008)
        sys.stderr.write(f"corrections: the ledger is {real}; commit it in that repository\n")


def find(records: list[dict], rid: str) -> dict:
    for r in records:
        if r["id"] == rid:
            return r
    _fail(f"no record {rid!r} in the ledger")


def _new_id(records: list[dict]) -> str:
    """c-<date>-<n>, the next free number for the day. A hash of the phrase and the
    date collided when the same phrase was corrected twice in one day (I184)."""
    day = _today().replace("-", "")
    taken = {r.get("id") for r in records}
    n = 1
    while f"c-{day}-{n:03d}" in taken:
        n += 1
    return f"c-{day}-{n:03d}"


def _matcher_sha(r: dict) -> str:
    """What a trial counted: the field, the matcher and the severity."""
    return hashlib.sha1(f"{r.get('field')}|{r.get('matcher')}|{r.get('severity')}".encode("utf-8")).hexdigest()[:12]


def _note(r: dict, what: str) -> None:
    r.setdefault("history", []).append({"date": _today(), "event": what})


# ---------------------------------------------------------------------------
# Classification and proposal
# ---------------------------------------------------------------------------
def classify(before: str, after: str, context: str = "") -> str:
    """A first guess at the kind; --kind overrides it. Short phrase -> literal;
    slots or re: -> templated; a whole sentence recast -> judgment; a swap of
    digits or dates only -> factual."""
    if before.startswith("re:") or re.search(r"\[(word|verb|det|adj)\]", before):
        return "templated"
    b_words = re.findall(r"\w+", before)
    if not b_words:
        return "judgment"
    if after and re.sub(r"[\d./-]+", "#", before) == re.sub(r"[\d./-]+", "#", after) and before != after:
        return "factual"
    if after and _one_fact_swapped(before, after):
        return "factual"
    if len(b_words) <= 6:
        return "literal"
    return "judgment"


_FACT_WORDS = frozenset(
    "monday tuesday wednesday thursday friday saturday sunday january february march april may june july "
    "august september october november december one two three four five six seven eight nine ten eleven "
    "twelve twenty thirty forty fifty hundred thousand million first second third fourth fifth".split())


def _one_fact_swapped(before: str, after: str) -> bool:
    """One word swapped for one other, where both are a name (capitalised, not the
    first word), a weekday, a month, a number word or a single letter: a fact
    corrected, not a phrasing (I036). "Tuesday" -> "Wednesday" is never a rule."""
    tb, ta = re.findall(r"\w+", before), re.findall(r"\w+", after)
    if len(tb) != len(ta):
        return False
    diff = [(x, y) for x, y in zip(tb, ta) if x != y]
    if len(diff) != 1:
        return False
    k = next(i for i, (x, y) in enumerate(zip(tb, ta)) if x != y)
    fact = lambda w: (w.lower() in _FACT_WORDS or len(w) == 1 or (k > 0 and w[:1].isupper()))  # noqa: E731
    return fact(diff[0][0]) and fact(diff[0][1])


def propose(r: dict) -> dict:
    """Fill matcher, field, fires, clean from the record when they are missing."""
    if r["kind"] in RULE_KINDS:
        r.setdefault("matcher", r["before"].strip().lower() if r["kind"] == "literal" else r["before"].strip())
        r.setdefault("severity", "warning")
        r.setdefault("field", _FIELD_FOR[r["severity"]])
        ctx = (r.get("context") or "").strip()
        if not r.get("fires"):
            if r["kind"] == "templated":
                r["fires"] = [ctx] if ctx else []  # a pattern is not a sentence; only the context can be an example
            else:
                # the context, when the phrase is in it; with no context the phrase itself.
                # A context that does not hold the phrase gives no example, so the trial
                # reports it instead of passing on the phrase alone (I186).
                r["fires"] = [ctx] if ctx and r["before"].lower() in ctx.lower() else ([] if ctx else [r["before"]])
        if not r.get("clean"):
            # the context with the author's fix in it is a near-miss; the bare after-text
            # ("cut", "and stops there.") tested nothing, so there is no fallback to it (I091)
            if ctx and r["before"].lower() in ctx.lower() and r.get("after"):
                r["clean"] = [re.sub(re.escape(r["before"]), r["after"], ctx, count=1, flags=re.I)]
            else:
                r["clean"] = []
    return r


def rule_entry(r: dict) -> dict:
    """The overlay entry a promoted record becomes."""
    e = {"id": r.get("rule_id") or voicelint._derive_id(r["field"], r["matcher"]),
         "pattern": r["matcher"], "rationale": r.get("rationale") or f"{r['before']} -> {r['after']}",
         "since": _today()}
    if r.get("fires"):
        e["fires"] = list(r["fires"])
    if r.get("clean"):
        e["clean"] = list(r["clean"])
    return e


def solo_config(cfg: dict, r: dict) -> tuple[dict, str]:
    """The effective config with every phrase list emptied but the candidate,
    so a trial counts the pattern itself. Under the full config an overlapping
    shipped rule wins the collapse on a tie and the candidate looks silent."""
    solo = json.loads(json.dumps(cfg))
    for field in voicelint._LIST_FIELDS:
        solo[field] = []
    solo["watch_words"] = {}
    for k in ("no_dashes", "load_bearing_literal_only", "no_honest_framing", "flag_loaded_quietly"):
        solo[k] = False
    cand, ids = corpusscan.config_with_candidates(solo, [{"field": r["field"], "pattern": r["matcher"],
                                                           "id": r.get("rule_id") or None}])
    return cand, ids[0]


def covering_rules(cfg: dict, r: dict) -> list[str]:
    """Shipped rules whose pattern contains, or is contained by, the candidate's."""
    m = r["matcher"].lower()
    out = []
    for field in voicelint._LIST_FIELDS:
        for e in voicelint.rule_entries(cfg, field):
            p = e["pattern"].lower()
            if p.startswith("re:") or m.startswith("re:"):
                continue
            if p == m or p in m or m in p:
                out.append(e["id"])
    return out


def examples_hold(r: dict, cfg: dict) -> list[str]:
    """Problems with the record's examples under the candidate alone; empty when all hold."""
    cand, rid = solo_config(cfg, r)
    problems = []
    if not r.get("fires"):
        problems.append("no fires example: the phrase is not in the context it was recorded with")
    if not r.get("clean"):
        problems.append("no clean example: give a near-miss sentence that must not fire (add --clean)")
    for text in r.get("fires", []):
        if rid not in {f.rule_id for f in voicelint.check(text, cand)}:
            problems.append(f"fires example does not fire: {text!r}")
    for text in r.get("clean", []):
        if rid in {f.rule_id for f in voicelint.check(text, cand)}:
            problems.append(f"clean example fires: {text!r}")
    return problems


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def _ledger_exists_or_init(args) -> None:
    """A mistyped --ledger used to start a new, empty ledger beside the real one,
    and the correction went where nobody reads it (I016)."""
    if not os.path.exists(args.ledger) and not getattr(args, "init", False):
        _fail(f"no ledger at {args.ledger}; pass --init to start one there")


def cmd_add(args) -> int:
    _ledger_exists_or_init(args)
    records = load_ledger(args.ledger)
    before = args.before.strip()
    if not before:
        _fail("--before is required and must not be empty")
    kind = args.kind or classify(before, args.after or "", args.context or "")
    r = {"id": _new_id(records), "date": _today(), "before": before, "after": (args.after or "").strip(),
         "context": (args.context or "").strip(), "source": (args.source or "").strip(),
         "surface": args.surface or "", "kind": kind, "rationale": (args.rationale or "").strip(),
         "status": "pending", "rule_id": "", "supersedes": args.supersedes or "", "history": []}
    if kind in RULE_KINDS:
        if args.fires:
            r["fires"] = list(args.fires)
        if args.clean:
            r["clean"] = list(args.clean)
        if args.severity:
            r["severity"] = args.severity
        if args.field:
            r["field"] = args.field
        if args.matcher:
            r["matcher"] = args.matcher
        propose(r)
        if r["field"] not in voicelint._LIST_FIELDS:
            _fail(f"--field must be one of {', '.join(voicelint._LIST_FIELDS)}")
    if any(x["before"].lower() == before.lower() and x["status"] not in ("retired", "rejected") for x in records):
        sys.stderr.write(f"corrections: note: {before!r} is already in the ledger; adding anyway as a new record\n")
    _note(r, f"added ({kind})" + (f", proposed {r.get('field')} {r.get('matcher')!r}" if kind in RULE_KINDS else ""))
    records.append(r)
    save_ledger(args.ledger, records)
    print(f"added {r['id']}  kind={kind}  {before!r} -> {r['after']!r}")
    if kind in RULE_KINDS:
        print(f"  proposed: {r['field']} {r['matcher']!r} ({r['severity']}); fires {r['fires']}; clean {r['clean']}")
        print(f"  next: corrections.py trial --ledger {args.ledger} {r['id']} <corpus dir> [--config overlay]")
    elif kind == "factual":
        print("  a factual correction; it will never become a style rule (promote writes prose only)")
    else:
        print(f"  {kind}: no regex; promote writes the prose line and marks it {('judgment-only' if kind in ('judgment', 'structural', 'exception') else 'preference')}")
    return 0


def _set_kind(r: dict, kind: str | None) -> None:
    """A mined record has no kind until the author gives one (I036)."""
    if kind:
        r["kind"] = kind
        _note(r, f"kind set to {kind} by the author")
    elif not r.get("kind"):
        _fail(f"{r['id']} has no kind; a mined record waits for the author: pass --kind "
              f"({', '.join(KINDS)}); the tool's guess was {r.get('suggested_kind') or 'none'}")


def cmd_trial(args) -> int:
    records = load_ledger(args.ledger)
    r = find(records, args.id)
    _set_kind(r, getattr(args, "kind", None))
    if r["kind"] not in RULE_KINDS:
        _fail(f"{r['id']} is {r['kind']}; only literal and templated corrections are trialled as rules")
    if r["status"] in ("promoted", "retired", "rejected"):
        _fail(f"{r['id']} is {r['status']}; nothing to trial")
    propose(r)
    if r["matcher"].startswith("re:"):
        try:
            re.compile(r["matcher"][3:])
        except re.error as exc:
            _fail(f"{r['id']}: the matcher {r['matcher']!r} is not a valid regex: {exc}")
    cfg = voicelint.load_config(args.config)
    problems = examples_hold(r, cfg)
    files = corpusscan.collect_files(args.paths, exclude=args.exclude)
    if not files:
        _fail("no corpus files found")
    cand, rid = solo_config(cfg, r)
    ids = [rid]
    covered = covering_rules(cfg, r)
    result = corpusscan.run_corpus(files, cand)
    s = corpusscan.summarize(result, args.paths, set(ids), args.contexts, 1)
    row = s["rules"][0] if s["rules"] else {"hits": 0, "files": 0, "per_1k_words": 0.0, "contexts": []}
    r["trial"] = {"date": _today(), "corpus": [os.path.abspath(p) for p in args.paths], "files": s["files"],
                  "words": s["words"], "overlay": args.config or "", "overlay_sha256": corpusscan._sha(args.config),
                  "base_sha256": corpusscan._sha(voicelint.DEFAULTS_PATH),
                  "hits": row["hits"], "files_hit": row["files"], "per_1k_words": row["per_1k_words"],
                  "contexts": row.get("contexts", []), "example_problems": problems,
                  "covered_by": covered, "matcher_sha": _matcher_sha(r)}
    r["status"] = "trialled"
    _note(r, f"trialled: {row['hits']} hit(s) in {row['files']} file(s), {len(problems)} example problem(s)")
    save_ledger(args.ledger, records)
    print(f"trial {r['id']}  {r['field']} {r['matcher']!r} ({r['severity']}) on {s['files']} file(s), {s['words']:,} words")
    print(f"  {row['hits']} hit(s) in {row['files']} file(s), {row['per_1k_words']} per 1,000 words. Raw hits, not confirmed violations.")
    for c in row.get("contexts", []):
        print(f"    {c['file']}:{c['line']}  {c['text']}")
    for p in problems:
        print(f"  example problem: {p}")
    if covered:
        print(f"  overlaps shipped rule(s): {', '.join(covered)}; a promoted rule would collapse with them on shared spans")
    print("  next: read the contexts, then promote, narrow the matcher (add again with --matcher), or retire")
    return 1 if problems else 0


def _append_prose(prose_path: str, source: str, line: str) -> None:
    """Append a bullet under a '## Mined corrections (<date>, <source>)' heading,
    creating the heading at the end when today's is not there."""
    statefile.write_text(prose_path, _prose_with(prose_path, source, line))


def _prose_with(prose_path: str, source: str, line: str) -> str:
    """The prose file's text with the bullet added, built in memory."""
    heading = f"## Mined corrections ({_today()}, {source})" if source else f"## Mined corrections ({_today()})"
    try:
        text = open(prose_path, encoding="utf-8").read() if os.path.exists(prose_path) else ""
    except (OSError, UnicodeDecodeError) as exc:
        _fail(f"cannot read the prose file {prose_path}: {exc}")
    if heading in text:
        head, tail = text.split(heading, 1)
        # insert after the heading's section: find the next '## ' or the end
        m = re.search(r"\n## ", tail)
        if m:
            sec, rest = tail[:m.start()], tail[m.start():]
            text = head + heading + sec.rstrip("\n") + "\n" + line + "\n" + rest
        else:
            text = head + heading + tail.rstrip("\n") + "\n" + line + "\n"
    else:
        text = text.rstrip("\n") + ("\n\n" if text else "") + heading + "\n\n" + line + "\n"
    return text


def prose_line(r: dict) -> str:
    left = f'"{r["before"]}"' if r["kind"] not in ("templated",) else f"`{r['before']}`"
    right = f' -> "{r["after"]}"' if r.get("after") else ""
    why = f". {r['rationale']}" if r.get("rationale") else ""
    tail = ""
    if r["status"] == "promoted":
        t = r.get("trial") or {}
        tail = f" (rule `{r['rule_id']}`, {r.get('severity', 'warning')}; {t.get('hits', 0)} corpus hit(s) in {t.get('files_hit', 0)} file(s) at trial)"
    elif r["status"] == "judgment-only":
        tail = " (judgment layer; no regex expresses it)"
    elif r["status"] == "preference":
        tail = " (a preference, not a ban)"
    elif r["kind"] == "factual":
        tail = " (a factual correction, not a style rule)"
    return f"- {left}{right}{why}{tail}"


BROAD_PER_1K = 1.0  # trialled hits per 1,000 words above which a rule is too broad to promote unasked


def _promote_checks(r: dict, args) -> None:
    """What a rule must show before it is written (I185, I036, I184)."""
    t = r.get("trial") or {}
    if t.get("matcher_sha") and t["matcher_sha"] != _matcher_sha(r):
        _fail(f"{r['id']}: the matcher changed after its trial; trial it again")
    if not (r.get("rationale") or "").strip():
        _fail(f"{r['id']} has no rationale; a rule carries the author's reason (add it to the record, or retire it)")
    rate = float(t.get("per_1k_words") or 0)
    if rate > BROAD_PER_1K and not getattr(args, "broad", False):
        _fail(f"{r['id']} fired {rate} times per 1,000 words in its trial, over {BROAD_PER_1K}; "
              "read the contexts, and pass --broad only if a rule that wide is meant")
    if r["matcher"].startswith("re:") and _slow_regex(r["matcher"][3:]):
        _fail(f"{r['id']}: the matcher takes over a second on a 2,000-character line; it would stall the hook")
    if r["kind"] == "literal" and len(re.findall(r"\w+", r["matcher"])) == 1 and not getattr(args, "confirm", False):
        _fail(f"{r['id']} would ban the single word {r['matcher']!r} (the author wrote {r['before']!r} -> "
              f"{r['after']!r}); a one-word rule fires everywhere the word does. Pass --confirm if that is meant")


def _slow_regex(pattern: str) -> bool:
    """Whether the pattern takes over a second on hostile 2,000-character lines, timed
    in a child process so a catastrophic backtrack cannot hang this one."""
    code = ("import re,sys\np=re.compile(sys.argv[1],re.I)\n"
            "for s in ('a'*2000+'!', ' '*2000+'x', 'ab '*667, 'x'*2000):\n    p.search(s)\n")
    try:
        subprocess.run([sys.executable, "-c", code, pattern], timeout=1.0, capture_output=True)
    except subprocess.TimeoutExpired:
        return True
    return False


def cmd_promote(args) -> int:
    records = load_ledger(args.ledger)
    r = find(records, args.id)
    if r["status"] not in ("promoted", "retired", "rejected"):
        _set_kind(r, getattr(args, "kind", None))
    if r["status"] in ("promoted", "retired", "rejected"):
        _fail(f"{r['id']} is already {r['status']}")
    source = args.source or r.get("source") or ""
    if r["kind"] == "factual":
        r["status"] = "rejected"
        _note(r, "factual: no rule; prose only")
        if args.prose:
            _append_prose(args.prose, source, prose_line(r))
        save_ledger(args.ledger, records)
        print(f"{r['id']}: factual correction; no rule written" + (f"; prose line appended to {args.prose}" if args.prose else ""))
        return 0
    if r["kind"] not in RULE_KINDS:
        r["status"] = "preference" if r["kind"] == "preference" else "judgment-only"
        _note(r, f"{r['status']}: prose only")
        if args.prose:
            _append_prose(args.prose, source, prose_line(r))
        save_ledger(args.ledger, records)
        print(f"{r['id']}: {r['status']}; no rule written" + (f"; prose line appended to {args.prose}" if args.prose else ""))
        return 0
    if r["status"] not in ("trialled", "promoting"):
        _fail(f"{r['id']} has not been trialled; run corrections.py trial first (nothing becomes a rule uncounted)")
    if r.get("trial", {}).get("example_problems"):
        _fail(f"{r['id']} has example problems from its trial; fix the matcher or the examples, trial again")
    if not args.overlay:
        _fail("--overlay is required to promote a rule")
    _promote_checks(r, args)
    # Everything is checked and built in memory before the first write, then
    # the ledger records "promoting", then the overlay, the prose, and the
    # ledger's "promoted" are each swapped in atomically. An interruption
    # leaves every file whole, and a rerun finishes the promotion.
    try:
        ov = json.load(open(args.overlay, encoding="utf-8")) if os.path.exists(args.overlay) else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"cannot read the overlay {args.overlay}: {exc}")
    # Into an overlay the entry goes under add_<field>; into the shipped base
    # (the maintainer promoting his own correction) it joins the list itself.
    into_base = os.path.exists(args.overlay) and os.path.samefile(args.overlay, voicelint.DEFAULTS_PATH)
    key = r["field"] if into_base else "add_" + r["field"]
    entry = rule_entry(r)
    same = lambda e: not isinstance(e, str) and e.get("id") == entry["id"] and e.get("pattern") == entry["pattern"]
    clash = lambda e: ((e if isinstance(e, str) else e.get("id")) == entry["id"]
                       or (e if isinstance(e, str) else e.get("pattern")) == entry["pattern"])
    resuming = r["status"] == "promoting" and any(same(e) for e in ov.get(key, []))
    if not resuming:
        if any(clash(e) for e in ov.get(key, [])):
            _fail(f"{args.overlay} already carries {entry['id']} / {entry['pattern']!r}")
        ov.setdefault(key, []).append(entry)
    voicelint._validate(ov)
    # the effective config must load with the new entry in it before anything is written
    probe = os.path.join(os.path.dirname(os.path.abspath(args.overlay)), f".{os.path.basename(args.overlay)}.probe.json")
    statefile.write_json(probe, ov)
    try:
        cfg = voicelint.load_config(probe)
    finally:
        os.unlink(probe)
    prose_text = None
    done = dict(r, rule_id=entry["id"], status="promoted")
    if args.prose:
        prose_text = _prose_with(args.prose, source, prose_line(done))
    covered = covering_rules(cfg, r)
    if covered:
        print(f"  note: overlaps shipped rule(s) {', '.join(covered)}; on a shared span the collapse keeps one finding")
    r["status"] = "promoting"
    save_ledger(args.ledger, records)
    if not resuming:
        statefile.write_json(args.overlay, ov)
    if prose_text is not None:
        already = os.path.exists(args.prose) and prose_line(done) in open(args.prose, encoding="utf-8").read()
        if not already:  # a resumed promotion does not add the line twice
            statefile.write_text(args.prose, prose_text)
    r["rule_id"] = entry["id"]
    r["status"] = "promoted"
    r["promoted"] = {"date": _today(), "overlay": os.path.abspath(args.overlay)}
    _note(r, f"promoted to {args.overlay} as {entry['id']}")
    save_ledger(args.ledger, records)
    print(f"promoted {r['id']} -> {key} {entry['id']} in {args.overlay}")
    if into_base:
        print("  the shipped base changed: run pherkad.py manifest --write, count it with corpusscan diff, and record it in the CHANGELOG")
    print(f"  fixtures: {len(entry.get('fires', []))} fires, {len(entry.get('clean', []))} clean (run by pherkad.py check-overlay)")
    if args.prose:
        print(f"  prose: appended to {args.prose}")
    return 0


def cmd_list(args) -> int:
    records = load_ledger(args.ledger)
    rows = [r for r in records if not args.status or r["status"] == args.status]
    for r in rows:
        t = r.get("trial") or {}
        hits = f"{t['hits']}h/{t['files_hit']}f" if t else "-"
        print(f"{r['id']}  {r['status']:<13} {r['kind']:<10} {hits:<8} {r['before']!r} -> {r['after']!r}"
              + (f"  [{r['rule_id']}]" if r.get("rule_id") else ""))
    print(f"corrections: {len(rows)} record(s)" + (f" with status {args.status}" if args.status else ""))
    return 0


def cmd_show(args) -> int:
    r = find(load_ledger(args.ledger), args.id)
    print(json.dumps(r, indent=2, ensure_ascii=False))
    return 0


def cmd_retire(args) -> int:
    records = load_ledger(args.ledger)
    r = find(records, args.id)
    if not args.reason.strip():
        _fail("--reason is required")
    r["status"] = "retired"
    _note(r, f"retired: {args.reason}")
    save_ledger(args.ledger, records)
    print(f"retired {r['id']}: {args.reason}")
    if r.get("rule_id"):
        print(f"  the overlay still carries {r['rule_id']}; remove it there (remove_{r['field']}: [\"{r['rule_id']}\"]) if the rule should go too")
    return 0


# ---------------------------------------------------------------------------
# mine: the author's edits of a draft as ledger candidates (roadmap item 24)
# ---------------------------------------------------------------------------
# The draft is what a model wrote; the edited file is what the author sent.
# Sentences are aligned, and inside a changed sentence the changed run of
# words is the candidate: "X -> Y" with the draft sentence as context. A cut
# ("X -> ") is a candidate too. A sentence rewritten wholesale is a judgment
# record (no regex). Every candidate enters as pending; trial and promote
# still need the count and the author's say.
_SENT_END = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])")
_TOKEN = re.compile(r"\w[\w'’-]*|[^\w\s]")


def _sentences(text: str) -> list[str]:
    out = []
    for para in re.split(r"\n\s*\n", text):
        para = " ".join(para.split())
        if para:
            out.extend(p.strip() for p in _SENT_END.split(para) if p.strip())
    return out


def _phrase(tokens: list[str]) -> str:
    """Tokens back to text, closing up before punctuation."""
    out = ""
    for t in tokens:
        if out and not re.match(r"[^\w\s]", t):
            out += " "
        elif out and t in ("(", "[", "\"", "'"):
            out += " "
        out += t
    return out.strip()


def _overlap(x: str, y: str) -> float:
    a, b = set(re.findall(r"\w+", x.lower())), set(re.findall(r"\w+", y.lower()))
    return len(a & b) / max(1, len(a | b))


def _pair_by_overlap(xs: list[str], ys: list[str], floor: float = 0.3) -> list[tuple]:
    """Pairs (x, y) of sentences that share the most words, each used once, in the
    draft's order. An x left over that matches two consecutive ys well is a split,
    and a y left over that matches two xs is a merge; each gives a tuple side."""
    cand = sorted(((_overlap(x, y), i, j) for i, x in enumerate(xs) for j, y in enumerate(ys)), reverse=True)
    used_x, used_y, pairs = set(), set(), {}
    for score, i, j in cand:
        if score < floor or i in used_x or j in used_y:
            continue
        used_x.add(i)
        used_y.add(j)
        pairs[i] = ys[j]
    out = []
    for i, x in enumerate(xs):
        if i in pairs:
            out.append((x, pairs[i]))
            continue
        split = next(((x, (ys[j], ys[j + 1])) for j in range(len(ys) - 1)
                      if j not in used_y and j + 1 not in used_y and _overlap(x, ys[j] + " " + ys[j + 1]) >= 0.6), None)
        out.append(split or (x, None))
    merged = set()
    for j, y in enumerate(ys):
        if j in used_y:
            continue
        merge = next((((xs[i], xs[i + 1]), y) for i in range(len(xs) - 1)
                      if _overlap(xs[i] + " " + xs[i + 1], y) >= 0.6), None)
        if merge:
            out.append(merge)
            merged.add(j)
    # one sentence left on each side is a sentence rewritten whole: pair them. With
    # unequal leftovers, position means nothing and nothing is paired.
    left_x = [k for k, (x, y) in enumerate(out) if y is None]
    left_y = [j for j in range(len(ys)) if j not in used_y and j not in merged
              and not any(isinstance(y, tuple) and ys[j] in y for _, y in out)]
    if len(left_x) == 1 and len(left_y) == 1:
        out[left_x[0]] = (out[left_x[0]][0], ys[left_y[0]])
    return out


def mine_pairs(draft: str, edited: str, max_words: int = 8, whole: float = 0.6) -> list[dict]:
    """Candidates from the diff of two texts: {before, after, context, kind}."""
    import difflib
    a, b = _sentences(draft), _sentences(edited)
    out = []
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "replace":
            continue  # equal sentences carry nothing; a whole sentence added or deleted is not a phrase correction
        # pair the replaced sentences by shared words, not by position: an inserted
        # sentence used to shift every pair after it and invent corrections (I186)
        for da, db in _pair_by_overlap(a[i1:i2], b[j1:j2]):
            if db is None:
                continue
            if isinstance(da, tuple) or isinstance(db, tuple):  # one sentence split in two, or two merged
                out.append({"before": " ".join(da) if isinstance(da, tuple) else da,
                            "after": " ".join(db) if isinstance(db, tuple) else db,
                            "context": " ".join(da) if isinstance(da, tuple) else da, "kind": "structural"})
                continue
            spans_a = [m.span() for m in _TOKEN.finditer(da)]
            ta, tb = _TOKEN.findall(da), _TOKEN.findall(db)
            wm = difflib.SequenceMatcher(a=[t.lower() for t in ta], b=[t.lower() for t in tb], autojunk=False)
            changed = sum(i2_ - i1_ for tg, i1_, i2_, _, _ in wm.get_opcodes() if tg != "equal")
            words_a = [t for t in ta if re.match(r"\w", t)]
            if words_a and changed / max(1, len(ta)) >= whole:
                out.append({"before": da, "after": db, "context": da, "kind": "judgment"})
                continue
            for tg, x1, x2, y1, y2 in wm.get_opcodes():
                if tg == "equal" or tg == "insert":
                    continue
                before = da[spans_a[x1][0]:spans_a[x2 - 1][1]]  # the author's own characters, sliced
                after = _phrase(tb[y1:y2]) if tg == "replace" else ""
                bw = re.findall(r"\w+", before)
                if not bw or len(bw) > max_words:
                    continue
                if before.lower() == after.lower():
                    continue  # case or punctuation only
                if re.fullmatch(r"[\W\d]+", before):
                    continue  # punctuation or a number
                if before.lower() not in da.lower():
                    continue
                out.append({"before": before, "after": after, "context": da, "kind": ""})
    return out


def cmd_mine(args) -> int:
    if not args.dry_run:
        _ledger_exists_or_init(args)
    try:
        draft = open(args.draft, encoding="utf-8", errors="replace").read()
        edited = open(args.edited, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        _fail(str(exc))
    cands = mine_pairs(draft, edited, args.max_words)
    if not cands:
        print("mine: no phrase-level changes between the two texts")
        return 0
    records = load_ledger(args.ledger) if not args.dry_run else []
    source = args.source or f"diff of {os.path.basename(args.draft)} and {os.path.basename(args.edited)}"
    added = 0
    for c in cands:
        guess = c["kind"] or classify(c["before"], c["after"], c["context"])
        kind = c["kind"] if c["kind"] in ("judgment", "structural") else ""  # the author sets a phrase's kind (I036)
        dup = any(x["before"].lower() == c["before"].lower() and x["status"] not in ("retired", "rejected") for x in records)
        mark = "  (already in the ledger)" if dup else ""
        print(f"{(kind or guess + '?'):10} {c['before']!r} -> {c['after']!r}{mark}")
        if args.dry_run or dup:
            continue
        r = {"id": _new_id(records), "date": _today(), "before": c["before"], "after": c["after"],
             "context": c["context"], "source": source, "surface": args.surface or "", "kind": kind,
             "suggested_kind": guess, "rationale": "", "status": "pending", "rule_id": "", "supersedes": "",
             "history": []}
        if kind in RULE_KINDS:
            propose(r)
        _note(r, f"mined from the author's edit ({source})")
        records.append(r)
        added += 1
    if not args.dry_run:
        save_ledger(args.ledger, records)
    print(f"mine: {len(cands)} candidate(s), {added} added to {args.ledger}" if not args.dry_run
          else f"mine: {len(cands)} candidate(s); dry run, nothing written")
    if added:
        print("next: read each, add a rationale or retire it, then corrections.py trial on the corpus; a factual change never becomes a rule")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The correction ledger: from X -> Y to a tested, counted rule.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("add", help="record a correction")
    pa.add_argument("--ledger", required=True)
    pa.add_argument("--init", action="store_true", help="start a new ledger at --ledger when none exists there")
    pa.add_argument("--before", required=True, help="what was written")
    pa.add_argument("--after", default="", help="what the author put instead")
    pa.add_argument("--context", default="", help="the sentence it was in")
    pa.add_argument("--source", default="", help="where it came from (an email, a review, a date)")
    pa.add_argument("--surface", default="")
    pa.add_argument("--kind", choices=list(KINDS))
    pa.add_argument("--rationale", default="")
    pa.add_argument("--severity", choices=["warning", "error"])
    pa.add_argument("--field", choices=list(voicelint._LIST_FIELDS))
    pa.add_argument("--matcher", help="override the proposed pattern (a phrase, [word] slots, or re:)")
    pa.add_argument("--supersedes", default="", help="the id this replaces")
    pa.add_argument("--fires", action="append", default=[], help="a sentence the rule must fire on (repeatable)")
    pa.add_argument("--clean", action="append", default=[], help="a near-miss the rule must not fire on (repeatable)")
    pa.set_defaults(fn=cmd_add)

    pm = sub.add_parser("mine", help="the author's edits of a draft as ledger candidates")
    pm.add_argument("draft", help="what the model wrote")
    pm.add_argument("edited", help="what the author sent")
    pm.add_argument("--ledger", required=True)
    pm.add_argument("--source", default="", help="where the edit came from (default: the two file names)")
    pm.add_argument("--surface", default="")
    pm.add_argument("--max-words", type=int, default=8, help="longest changed run treated as a phrase; longer runs become judgment records only when the whole sentence changed")
    pm.add_argument("--dry-run", action="store_true")
    pm.add_argument("--init", action="store_true", help="start a new ledger at --ledger when none exists there")
    pm.set_defaults(fn=cmd_mine)

    pt = sub.add_parser("trial", help="count the candidate on a corpus and check its examples")
    pt.add_argument("id")
    pt.add_argument("paths", nargs="+")
    pt.add_argument("--ledger", required=True)
    pt.add_argument("--config")
    pt.add_argument("--exclude", action="append", default=[])
    pt.add_argument("--contexts", type=int, default=6)
    pt.add_argument("--kind", choices=list(KINDS), help="set the kind of a mined record, which has none until the author gives one")
    pt.set_defaults(fn=cmd_trial)

    pp = sub.add_parser("promote", help="write the overlay entry, the fixtures, and the prose line")
    pp.add_argument("id")
    pp.add_argument("--ledger", required=True)
    pp.add_argument("--overlay", help="the project overlay to write the rule into")
    pp.add_argument("--prose", help="the prose rules file to append the mined-correction line to")
    pp.add_argument("--source", help="override the record's source for the prose heading")
    pp.add_argument("--kind", choices=list(KINDS), help="set the kind of a mined record")
    pp.add_argument("--broad", action="store_true", help=f"promote a rule that fired over {BROAD_PER_1K} per 1,000 words in its trial")
    pp.add_argument("--confirm", action="store_true", help="promote a literal rule of one word")
    pp.set_defaults(fn=cmd_promote)

    pl = sub.add_parser("list")
    pl.add_argument("--ledger", required=True)
    pl.add_argument("--status", choices=list(STATUSES))
    pl.set_defaults(fn=cmd_list)

    ps = sub.add_parser("show")
    ps.add_argument("id")
    ps.add_argument("--ledger", required=True)
    ps.set_defaults(fn=cmd_show)

    pr = sub.add_parser("retire")
    pr.add_argument("id")
    pr.add_argument("--ledger", required=True)
    pr.add_argument("--reason", required=True)
    pr.set_defaults(fn=cmd_retire)

    args = ap.parse_args(argv)
    ledger = getattr(args, "ledger", None)
    if not ledger or getattr(args, "dry_run", False):
        return args.fn(args)
    with statefile.locked(ledger):  # one load-change-save at a time
        return args.fn(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        sys.stderr.write(f"corrections: unexpected error: {exc}\n")
        sys.exit(2)
