#!/usr/bin/env python3
"""corrections: from "X -> Y" to a tested, counted rule, with one approval.

Roadmap item 10. The author's corrections arrive as terse edits and were
transcribed by hand into the mined-corrections sections of voice-rules.md;
some of them later became config rules, most did not, and none carried a
count. This is the ledger and the pipeline.

    corrections.py add     --ledger F --before "X" --after "Y" [--context "..."] [--source "..."]
                           [--surface S] [--kind K] [--rationale "..."] [--severity warning|error]
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
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import voicelint  # noqa: E402
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
    return out


def save_ledger(path: str, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def find(records: list[dict], rid: str) -> dict:
    for r in records:
        if r["id"] == rid:
            return r
    _fail(f"no record {rid!r} in the ledger")


def _new_id(before: str) -> str:
    h = hashlib.sha1((before + _today()).encode("utf-8")).hexdigest()[:4]
    return f"c-{_today().replace('-', '')}-{h}"


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
    if len(b_words) <= 6:
        return "literal"
    return "judgment"


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
                r["fires"] = [ctx] if ctx and r["before"].lower() in ctx.lower() else [r["before"]]
        if not r.get("clean"):
            if ctx and r["before"].lower() in ctx.lower() and r.get("after"):
                r["clean"] = [re.sub(re.escape(r["before"]), r["after"], ctx, count=1, flags=re.I)]
            elif r.get("after"):
                r["clean"] = [r["after"]]
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
def cmd_add(args) -> int:
    records = load_ledger(args.ledger)
    before = args.before.strip()
    if not before:
        _fail("--before is required and must not be empty")
    kind = args.kind or classify(before, args.after or "", args.context or "")
    r = {"id": _new_id(before), "date": _today(), "before": before, "after": (args.after or "").strip(),
         "context": (args.context or "").strip(), "source": (args.source or "").strip(),
         "surface": args.surface or "", "kind": kind, "rationale": (args.rationale or "").strip(),
         "status": "pending", "rule_id": "", "supersedes": args.supersedes or "", "history": []}
    if kind in RULE_KINDS:
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


def cmd_trial(args) -> int:
    records = load_ledger(args.ledger)
    r = find(records, args.id)
    if r["kind"] not in RULE_KINDS:
        _fail(f"{r['id']} is {r['kind']}; only literal and templated corrections are trialled as rules")
    if r["status"] in ("promoted", "retired", "rejected"):
        _fail(f"{r['id']} is {r['status']}; nothing to trial")
    propose(r)
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
                  "covered_by": covered}
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
    heading = f"## Mined corrections ({_today()}, {source})" if source else f"## Mined corrections ({_today()})"
    text = open(prose_path, encoding="utf-8").read() if os.path.exists(prose_path) else ""
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
    with open(prose_path, "w", encoding="utf-8") as fh:
        fh.write(text)


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


def cmd_promote(args) -> int:
    records = load_ledger(args.ledger)
    r = find(records, args.id)
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
    if r["status"] != "trialled":
        _fail(f"{r['id']} has not been trialled; run corrections.py trial first (nothing becomes a rule uncounted)")
    if r.get("trial", {}).get("example_problems"):
        _fail(f"{r['id']} has example problems from its trial; fix the matcher or the examples, trial again")
    if not args.overlay:
        _fail("--overlay is required to promote a rule")
    # write the overlay entry
    ov = json.load(open(args.overlay, encoding="utf-8")) if os.path.exists(args.overlay) else {}
    # Into an overlay the entry goes under add_<field>; into the shipped base
    # (the maintainer promoting his own correction) it joins the list itself.
    into_base = os.path.exists(args.overlay) and os.path.samefile(args.overlay, voicelint.DEFAULTS_PATH)
    key = r["field"] if into_base else "add_" + r["field"]
    entry = rule_entry(r)
    existing = [e for e in ov.get(key, []) if (e if isinstance(e, str) else e.get("id")) == entry["id"]
                or (e if isinstance(e, str) else e.get("pattern")) == entry["pattern"]]
    if existing:
        _fail(f"{args.overlay} already carries {entry['id']} / {entry['pattern']!r}")
    ov.setdefault(key, []).append(entry)
    voicelint._validate(ov)
    with open(args.overlay, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    # confirm the effective config still loads and the examples hold under it
    cfg = voicelint.load_config(args.overlay)  # must load and validate with the new entry in it
    covered = covering_rules(cfg, r)
    if covered:
        print(f"  note: overlaps shipped rule(s) {', '.join(covered)}; on a shared span the collapse keeps one finding")
    r["rule_id"] = entry["id"]
    r["status"] = "promoted"
    r["promoted"] = {"date": _today(), "overlay": os.path.abspath(args.overlay)}
    _note(r, f"promoted to {args.overlay} as {entry['id']}")
    if args.prose:
        _append_prose(args.prose, source, prose_line(r))
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The correction ledger: from X -> Y to a tested, counted rule.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("add", help="record a correction")
    pa.add_argument("--ledger", required=True)
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
    pa.set_defaults(fn=cmd_add)

    pt = sub.add_parser("trial", help="count the candidate on a corpus and check its examples")
    pt.add_argument("id")
    pt.add_argument("paths", nargs="+")
    pt.add_argument("--ledger", required=True)
    pt.add_argument("--config")
    pt.add_argument("--exclude", action="append", default=[])
    pt.add_argument("--contexts", type=int, default=6)
    pt.set_defaults(fn=cmd_trial)

    pp = sub.add_parser("promote", help="write the overlay entry, the fixtures, and the prose line")
    pp.add_argument("id")
    pp.add_argument("--ledger", required=True)
    pp.add_argument("--overlay", help="the project overlay to write the rule into")
    pp.add_argument("--prose", help="the prose rules file to append the mined-correction line to")
    pp.add_argument("--source", help="override the record's source for the prose heading")
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
    return args.fn(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        sys.stderr.write(f"corrections: unexpected error: {exc}\n")
        sys.exit(2)
