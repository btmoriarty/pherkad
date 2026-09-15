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

    results, io_failed = [], False
    errors = warnings = advis = suppressed = 0
    for path in files:
        try:
            text = read_source(path)
        except OSError as exc:
            sys.stderr.write(f"pherkad: {exc}\n")
            io_failed = True
            continue
        findings, dropped = run_text(text, cfg, structure=not args.no_structure)
        results.append((path, findings))
        suppressed += dropped
        for f in findings:
            lvl = _level(f, advisory)
            if lvl == "error":
                errors += 1
            elif lvl == "warning":
                warnings += 1
            else:
                advis += 1

    if args.format == "json":
        print(json.dumps({"tool": "pherkad", "version": _version(), "surface": args.surface or "",
                          "overlay": overlay or "", "config_sha256": config_sha256(cfg),
                          "advisory_prefixes": advisory, "suppressed": suppressed,
                          "files": {p: fs for p, fs in results}}, indent=2, ensure_ascii=False))
    elif args.format == "sarif":
        print(json.dumps(to_sarif(results, cfg, advisory), indent=2, ensure_ascii=False))
    else:
        if not args.quiet:
            for path, findings in results:
                for f in findings:
                    where = f"{path}:{f['line']}:{f['col']}" if f["line"] else path
                    print(f"{where} [{_level(f, advisory)}] {f['rule']} ({f['rule_id']}): "
                          f"{f['message']}  ->  {f['match']!r}")
        tail = []
        if advis:
            tail.append(f"{advis} advisory")
        if suppressed:
            tail.append(f"{suppressed} suppressed")
        tail_s = (", " + ", ".join(tail)) if tail else ""
        print(f"pherkad: {errors} error(s), {warnings} warning(s){tail_s} across {len(results)} file(s).")

    if io_failed:
        return 2
    return 1 if errors or (args.strict and warnings) else 0


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
    pc.set_defaults(fn=cmd_check)
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
