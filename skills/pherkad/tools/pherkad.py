#!/usr/bin/env python3
"""pherkad: the combined mechanical check, both engines in one run.

Roadmap item 6. voicelint matches phrases and structlint matches shapes, and
until now a consumer ran both, read two formats, and got two densities. This
runs both over each file, folds the findings into one list in one schema,
removes the overlap between the engines, computes one density over the whole,
and prints one format.

    pherkad.py check FILE [FILE ...]                 # or - for stdin
    pherkad.py check --config OVERLAY FILE           # a project overlay
    pherkad.py check --surface assistant-chat FILE   # a shipped surface
    pherkad.py check --format json FILE              # voicelint's envelope, plus provenance
    pherkad.py check --format sarif FILE             # SARIF 2.1.0 for editors and CI
    pherkad.py check --advisory structure. FILE      # report, never count, rule ids under a prefix
    pherkad.py check --strict FILE                   # warnings fail too
    pherkad.py check --no-structure FILE             # voicelint only
    pherkad.py rules [--config OVERLAY] [--json]     # every rule both engines would run
    pherkad.py check --decisions FILE ...            # hide findings the author has decided on
    pherkad.py decide --decisions FILE --reason "..." path:line[:rule_id] ...
    pherkad.py decisions --decisions FILE [--prune] FILE...   # which decisions still match

Decisions (roadmap item 7). A warning the author has read and accepted should
stay quiet until something about it changes, and nothing else should. A
decision file is a project-owned JSON list of records:

    {"rule_id": "soft.is-the-whole", "path": "canon/x.md", "context_hash": "…",
     "rule_hash": "…", "count": 1, "disposition": "accepted", "reason": "…",
     "decided": "2026-09-15"}

The context is the whole line the finding sits on, whitespace collapsed; the
rule hash is the rule's pattern. A finding matches a decision when rule id,
path, context, and rule all match, up to ``count`` occurrences on that line;
a changed line, a changed rule, or an extra occurrence surfaces the finding
again as new. Decided findings are hidden from the list (``--show-decided``
prints them) and never counted toward the exit; the summary says how many.
Nothing here writes a decision except ``decide``, which requires a reason.
Dispositions: accepted (the author's usage), intentional (a deliberate
choice), deferred (known, fix later; still hidden, counted separately so the
debt stays visible). Paths are relative to ``--root`` (default: the decision
file's directory).

Finding schema (every engine, every format): line, col, severity, rule,
match, message, rule_id, engine. ``engine`` is voice, structure, or combined
(the density). Density: structlint's own per-document density is dropped and
one ``density`` finding is computed over both engines' findings, against the
``structure.density_per_100`` threshold, on documents of 100 words or more.
Overlap: a structlint ``header`` finding whose heading contains the text of a
voicelint finding on the same line is the same tell reported twice; the
voicelint one, which names the rule, is kept.

Exit status: 0 clean; 1 on an error-level finding, or a warning under
--strict, advisory findings never counted; 2 on a usage, IO, or config
problem. The same contract as voicelint, so it can replace it in a gate.

Stdlib only. Vendored beside voicelint.py, mdmask.py, structlint.py, and
voice_config.json wherever a downstream gate runs it.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import voicelint  # noqa: E402
import structlint  # noqa: E402

SURFACES = os.path.join(HERE, "surfaces")


def _version() -> str:
    try:
        with open(os.path.join(HERE, "..", "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return "unknown"


def resolve_config(surface: str | None, config: str | None) -> str | None:
    """The overlay path: a shipped surface by name, or a file. Both is an error."""
    if surface and config:
        sys.stderr.write("pherkad: give --surface or --config, not both\n")
        sys.exit(2)
    if surface:
        if os.path.sep in surface or surface.endswith(".json"):
            p = surface
        else:
            p = os.path.join(SURFACES, surface + ".json")
        if not os.path.exists(p):
            have = sorted(f[:-5] for f in os.listdir(SURFACES) if f.endswith(".json")) if os.path.isdir(SURFACES) else []
            sys.stderr.write(f"pherkad: unknown surface '{surface}'; have {', '.join(have) or 'none'}\n")
            sys.exit(2)
        return p
    return config


def config_sha256(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------
DISPOSITIONS = ("accepted", "intentional", "deferred")
_DECISION_KEYS = frozenset({"rule_id", "path", "context_hash", "rule_hash", "count",
                            "disposition", "reason", "decided", "line", "match", "note"})


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def context_hash(text: str, line: int) -> str:
    """The hash of the whole line a finding sits on, whitespace collapsed.
    A finding at line 0 (the density) has no context and cannot be decided."""
    lines = text.split("\n")
    if not 1 <= line <= len(lines):
        return ""
    return _hash(" ".join(lines[line - 1].split()))


def rule_hashes(cfg: dict) -> dict:
    return {r["id"]: _hash(r.get("pattern", "")) for r in all_rules(cfg)}


def load_decisions(path: str | None) -> list[dict]:
    if not path:
        return []
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"pherkad: cannot read decisions {path}: {exc}\n")
        sys.exit(2)
    if not isinstance(data, list):
        sys.stderr.write(f"pherkad: decisions file {path} must be a JSON list\n")
        sys.exit(2)
    for i, d in enumerate(data):
        if not isinstance(d, dict) or not {"rule_id", "path", "context_hash", "rule_hash", "disposition", "reason"} <= set(d):
            sys.stderr.write(f"pherkad: decision {i} in {path} is missing a required field\n")
            sys.exit(2)
        if set(d) - _DECISION_KEYS:
            sys.stderr.write(f"pherkad: decision {i} in {path} has unknown field(s) {sorted(set(d) - _DECISION_KEYS)}\n")
            sys.exit(2)
        if d["disposition"] not in DISPOSITIONS:
            sys.stderr.write(f"pherkad: decision {i} in {path}: disposition must be one of {', '.join(DISPOSITIONS)}\n")
            sys.exit(2)
        if not str(d["reason"]).strip():
            sys.stderr.write(f"pherkad: decision {i} in {path} has no reason; a decision without one is not a decision\n")
            sys.exit(2)
        d.setdefault("count", 1)
    return data


def save_decisions(path: str, decisions: list[dict]) -> None:
    decisions = sorted(decisions, key=lambda d: (d["path"], d["rule_id"], d["context_hash"]))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(decisions, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def rel_path(path: str, root: str) -> str:
    if path == "-":
        return "-"
    try:
        return os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    except ValueError:
        return os.path.abspath(path)


def apply_decisions(findings: list[dict], text: str, path_rel: str, decisions: list[dict],
                    hashes: dict) -> list[dict]:
    """Attach ``decision`` to each finding that a decision covers (None otherwise)
    and return the decisions that matched at least one finding. A decision
    covers up to ``count`` findings sharing its rule id and context on this
    path; a stale rule hash matches nothing."""
    budget = {}
    for d in decisions:
        if d["path"] != path_rel or d["rule_hash"] != hashes.get(d["rule_id"], ""):
            continue
        key = (d["rule_id"], d["context_hash"])
        budget[key] = [d, int(d.get("count", 1))]
    used = []
    for f in findings:
        f["decision"] = None
        if not f["line"]:
            continue
        key = (f["rule_id"], context_hash(text, f["line"]))
        slot = budget.get(key)
        if slot and slot[1] > 0:
            slot[1] -= 1
            f["decision"] = slot[0]
            if slot[0] not in used:
                used.append(slot[0])
    return used


def run_text(text: str, cfg: dict, structure: bool = True) -> tuple[list[dict], int]:
    """Both engines over ``text``: one list of finding dicts in the shared
    schema, sorted by position, plus the number of findings an inline
    directive suppressed. Structural findings carry ``engine`` structure; the
    per-document density is one ``combined`` finding."""
    voice, suppressed = voicelint.check_counting(text, cfg)
    out = [dict(vars(f), engine="voice") for f in voice]
    if structure:
        shape = structlint.check_text(text, cfg.get("structure"))
        by_line = {}
        for f in out:
            by_line.setdefault(f["line"], []).append(f)
        for f in shape:
            if f.rule == "density":
                continue  # recomputed over both engines below
            if f.rule == "header" and any(v["match"].lower() in f.match.lower() for v in by_line.get(f.line, [])):
                continue  # the same tell, already named by a voicelint rule
            out.append(dict(vars(f), engine="structure"))
    out.sort(key=lambda f: (f["line"], f["col"]))
    words = len(re.findall(r"\b\w+\b", voicelint.mask_code(text)))
    cap = float((cfg.get("structure") or {}).get("density_per_100", structlint.DEFAULT_THRESHOLDS["density_per_100"]))
    if words >= 100 and cap > 0:
        per100 = len(out) * 100.0 / words
        if per100 > cap:
            out.append({"line": 0, "col": 0, "severity": "warning", "rule": "density",
                        "match": f"{len(out)} findings / {words} words",
                        "message": f"{per100:.1f} flagged constructions per 100 words, over the {cap} cap",
                        "rule_id": "density", "engine": "combined"})
    return out, suppressed


def all_rules(cfg: dict) -> list[dict]:
    rows = voicelint.all_rules(cfg)
    for check, desc in (("two-beat", "clipped balanced parallel"), ("staccato", "run of short sentences"),
                        ("header", "heading that strikes a pose"), ("aphorism", "manufactured maxim"),
                        ("interrogative-headers", "rate of question-word headings")):
        rows.append({"id": "structure." + check, "family": check, "severity": "warning",
                     "pattern": desc, "rationale": ""})
    rows.append({"id": "density", "family": "density", "severity": "warning",
                 "pattern": "flagged constructions per 100 words, both engines", "rationale": ""})
    return rows


def read_source(path: str) -> str:
    return voicelint.read_source(path, False)


def _level(f: dict, advisory: list[str]) -> str:
    if any(f["rule_id"].startswith(p) for p in advisory):
        return "advisory"
    return f["severity"]


def to_sarif(results: list[tuple[str, list[dict]]], cfg: dict, advisory: list[str]) -> dict:
    rules = {r["id"]: r for r in all_rules(cfg)}
    seen = []
    sarif_results = []
    for path, findings in results:
        for f in findings:
            if f["rule_id"] not in seen:
                seen.append(f["rule_id"])
            level = {"error": "error", "warning": "warning", "advisory": "note"}[_level(f, advisory)]
            sarif_results.append({
                "ruleId": f["rule_id"], "level": level,
                "message": {"text": f["message"]},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": path},
                    "region": {"startLine": max(1, f["line"]), "startColumn": max(1, f["col"])}}}],
                "properties": {"engine": f["engine"], "family": f["rule"], "match": f["match"]},
            })
    driver_rules = []
    for rid in seen:
        r = rules.get(rid, {"pattern": "", "rationale": ""})
        driver_rules.append({"id": rid, "shortDescription": {"text": r.get("rationale") or r.get("pattern") or rid}})
    return {"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": "pherkad", "version": _version(), "rules": driver_rules}},
                      "results": sarif_results}]}


def cmd_check(args) -> int:
    overlay = resolve_config(args.surface, args.config)
    cfg = voicelint.load_config(overlay)
    advisory = args.advisory or []
    seen = set()
    files = [f for f in args.files if not (f in seen or seen.add(f))]
    decisions = load_decisions(args.decisions)
    root = args.root or (os.path.dirname(os.path.abspath(args.decisions)) if args.decisions else os.getcwd())
    hashes = rule_hashes(cfg) if decisions else {}

    results, io_failed = [], False
    errors = warnings = advis = suppressed = 0
    decided = {"accepted": 0, "intentional": 0, "deferred": 0}
    for path in files:
        try:
            text = read_source(path)
        except OSError as exc:
            sys.stderr.write(f"pherkad: {exc}\n")
            io_failed = True
            continue
        findings, dropped = run_text(text, cfg, structure=not args.no_structure)
        if decisions:
            apply_decisions(findings, text, rel_path(path, root), decisions, hashes)
        else:
            for f in findings:
                f["decision"] = None
        results.append((path, findings))
        suppressed += dropped
        for f in findings:
            if f["decision"]:
                decided[f["decision"]["disposition"]] += 1
                continue
            lvl = _level(f, advisory)
            if lvl == "error":
                errors += 1
            elif lvl == "warning":
                warnings += 1
            else:
                advis += 1
    n_decided = sum(decided.values())

    if args.format == "json":
        print(json.dumps({"tool": "pherkad", "version": _version(), "surface": args.surface or "",
                          "overlay": overlay or "", "config_sha256": config_sha256(cfg),
                          "advisory_prefixes": advisory, "suppressed": suppressed,
                          "decisions": args.decisions or "", "decided": decided,
                          "files": {p: fs for p, fs in results}}, indent=2, ensure_ascii=False))
    elif args.format == "sarif":
        undecided = [(p, [f for f in fs if not f["decision"]]) for p, fs in results]
        print(json.dumps(to_sarif(undecided, cfg, advisory), indent=2, ensure_ascii=False))
    else:
        if not args.quiet:
            for path, findings in results:
                for f in findings:
                    if f["decision"] and not args.show_decided:
                        continue
                    where = f"{path}:{f['line']}:{f['col']}" if f["line"] else path
                    lvl = f"decided:{f['decision']['disposition']}" if f["decision"] else _level(f, advisory)
                    print(f"{where} [{lvl}] {f['rule']} ({f['rule_id']}): "
                          f"{f['message']}  ->  {f['match']!r}")
        tail = []
        if advis:
            tail.append(f"{advis} advisory")
        if n_decided:
            parts = ", ".join(f"{v} {k}" for k, v in decided.items() if v)
            tail.append(f"{n_decided} decided ({parts})")
        if suppressed:
            tail.append(f"{suppressed} suppressed")
        tail_s = (", " + ", ".join(tail)) if tail else ""
        print(f"pherkad: {errors} error(s), {warnings} warning(s){tail_s} across {len(results)} file(s).")

    if io_failed:
        return 2
    return 1 if errors or (args.strict and warnings) else 0


def _parse_location(loc: str):
    """path:line or path:line:rule_id."""
    parts = loc.rsplit(":", 2)
    if len(parts) >= 2 and parts[1].isdigit():
        return parts[0], int(parts[1]), (parts[2] if len(parts) == 3 else None)
    if len(parts) == 3 and parts[-2].isdigit():
        return parts[0], int(parts[1]), parts[2]
    # path:line:rule where rsplit split at the wrong colon (a path with colons is rare)
    m = re.match(r"^(.*?):(\d+)(?::([\w.-]+))?$", loc)
    if not m:
        sys.stderr.write(f"pherkad: location must be path:line or path:line:rule_id, got {loc!r}\n")
        sys.exit(2)
    return m.group(1), int(m.group(2)), m.group(3)


def cmd_decide(args) -> int:
    """Record a decision for the finding(s) at a location. Requires a reason."""
    if not args.reason.strip():
        sys.stderr.write("pherkad: --reason is required; a decision without one is not a decision\n")
        return 2
    overlay = resolve_config(args.surface, args.config)
    cfg = voicelint.load_config(overlay)
    hashes = rule_hashes(cfg)
    decisions = load_decisions(args.decisions)
    root = args.root or os.path.dirname(os.path.abspath(args.decisions))
    import datetime
    today = datetime.date.today().isoformat()
    added = 0
    for loc in args.locations:
        path, line, rule_id = _parse_location(loc)
        try:
            text = read_source(path)
        except OSError as exc:
            sys.stderr.write(f"pherkad: {exc}\n")
            return 2
        findings, _ = run_text(text, cfg, structure=not args.no_structure)
        at = [f for f in findings if f["line"] == line and (rule_id is None or f["rule_id"] == rule_id)]
        if not at:
            sys.stderr.write(f"pherkad: no finding at {loc}; nothing to decide\n")
            return 2
        rel = rel_path(path, root)
        ctx = context_hash(text, line)
        by_rule = {}
        for f in at:
            by_rule.setdefault(f["rule_id"], []).append(f)
        for rid, fs in by_rule.items():
            existing = next((d for d in decisions if d["path"] == rel and d["rule_id"] == rid
                             and d["context_hash"] == ctx), None)
            if existing:
                existing.update(count=len(fs), rule_hash=hashes[rid], disposition=args.disposition,
                                reason=args.reason, decided=today, line=line, match=fs[0]["match"])
            else:
                decisions.append({"rule_id": rid, "path": rel, "context_hash": ctx, "rule_hash": hashes[rid],
                                  "count": len(fs), "disposition": args.disposition, "reason": args.reason,
                                  "decided": today, "line": line, "match": fs[0]["match"]})
            added += 1
            print(f"decided {args.disposition}: {rel}:{line} {rid} ({len(fs)} occurrence(s))  ->  {fs[0]['match']!r}")
    save_decisions(args.decisions, decisions)
    print(f"pherkad: {added} decision(s) written to {args.decisions}")
    return 0


def cmd_decisions(args) -> int:
    """Which decisions still match a finding, and which are stale (the line
    changed, the rule changed, the file is gone, or the finding no longer
    fires). --prune drops the stale ones; nothing is pruned otherwise."""
    overlay = resolve_config(args.surface, args.config)
    cfg = voicelint.load_config(overlay)
    hashes = rule_hashes(cfg)
    decisions = load_decisions(args.decisions)
    root = args.root or os.path.dirname(os.path.abspath(args.decisions))
    live = set()
    for path in args.files:
        try:
            text = read_source(path)
        except OSError as exc:
            sys.stderr.write(f"pherkad: {exc}\n")
            continue
        findings, _ = run_text(text, cfg, structure=not args.no_structure)
        for d in apply_decisions(findings, text, rel_path(path, root), decisions, hashes):
            live.add(id(d))
    checked = {rel_path(p, root) for p in args.files}
    stale, kept, unchecked = [], [], []
    for d in decisions:
        if id(d) in live:
            kept.append(d)
        elif d["path"] not in checked:
            unchecked.append(d)
        else:
            why = ("rule changed" if d["rule_hash"] != hashes.get(d["rule_id"], "")
                   else "rule gone" if d["rule_id"] not in hashes else "line changed or finding gone")
            stale.append((d, why))
    for d, why in stale:
        print(f"stale ({why}): {d['path']}:{d.get('line', '?')} {d['rule_id']}  ->  {d.get('match', '')!r}  [{d['disposition']}: {d['reason']}]")
    print(f"pherkad: {len(kept)} decision(s) live, {len(stale)} stale, {len(unchecked)} on files not checked, "
          f"of {len(decisions)} in {args.decisions}")
    if args.prune and stale:
        drop = {id(d) for d, _ in stale}
        save_decisions(args.decisions, [d for d in decisions if id(d) not in drop])
        print(f"pherkad: pruned {len(stale)} stale decision(s)")
    return 0


def cmd_rules(args) -> int:
    cfg = voicelint.load_config(resolve_config(args.surface, args.config))
    rows = all_rules(cfg)
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        for r in rows:
            tail = f"\t{r['rationale']}" if r["rationale"] else ""
            print(f"{r['id']}\t{r['family']}\t{r['severity']}\t{r['pattern']}{tail}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The combined mechanical voice check: voicelint and structlint in one run.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("check", help="check files with both engines")
    pc.add_argument("files", nargs="+", help="files to check, or - for stdin")
    pc.add_argument("--surface", help="a shipped surface under surfaces/ (or a path)")
    pc.add_argument("--config", help="an overlay config")
    pc.add_argument("--format", choices=["text", "json", "sarif"], default="text")
    pc.add_argument("--strict", action="store_true", help="warnings fail too")
    pc.add_argument("--advisory", action="append", metavar="PREFIX",
                    help="rule ids under this prefix are reported but never counted (repeatable), e.g. structure.")
    pc.add_argument("--no-structure", action="store_true", help="voicelint only")
    pc.add_argument("--quiet", action="store_true", help="only print the summary (text format)")
    pc.add_argument("--decisions", help="a project decision file; decided findings are hidden and not counted")
    pc.add_argument("--root", help="paths in the decision file are relative to this (default: its directory)")
    pc.add_argument("--show-decided", action="store_true", help="print decided findings too (text format)")
    pc.set_defaults(fn=cmd_check)
    pd = sub.add_parser("decide", help="record a decision for the finding(s) at path:line[:rule_id]")
    pd.add_argument("locations", nargs="+", metavar="path:line[:rule_id]")
    pd.add_argument("--decisions", required=True, help="the project decision file (created if missing)")
    pd.add_argument("--reason", required=True, help="why; required")
    pd.add_argument("--disposition", choices=list(DISPOSITIONS), default="accepted")
    pd.add_argument("--surface")
    pd.add_argument("--config")
    pd.add_argument("--root")
    pd.add_argument("--no-structure", action="store_true")
    pd.set_defaults(fn=cmd_decide)
    pdd = sub.add_parser("decisions", help="which decisions still match; --prune drops the stale ones")
    pdd.add_argument("files", nargs="+")
    pdd.add_argument("--decisions", required=True)
    pdd.add_argument("--prune", action="store_true")
    pdd.add_argument("--surface")
    pdd.add_argument("--config")
    pdd.add_argument("--root")
    pdd.add_argument("--no-structure", action="store_true")
    pdd.set_defaults(fn=cmd_decisions)
    pr = sub.add_parser("rules", help="list every rule both engines would run")
    pr.add_argument("--surface")
    pr.add_argument("--config")
    pr.add_argument("--json", action="store_true")
    pr.set_defaults(fn=cmd_rules)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:  # a crash must not look like findings
        sys.stderr.write(f"pherkad: unexpected error: {exc}\n")
        sys.exit(2)
