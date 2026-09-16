#!/usr/bin/env python3
"""corpusscan: count the rules against a corpus before believing them.

Roadmap item 3. Every rule change is supposed to be counted against a real
corpus before it ships; until now that count was done by hand and recorded as
a config comment. This makes it one command, and the same command previews a
candidate rule and diffs two releases of the rule set under one overlay.

    corpusscan.py scan DIR [DIR...] [--config OVERLAY] [--surface S]
        every rule, both engines: hits, files, hits per 1,000 words, sorted by hits
    corpusscan.py scan DIR --rule soft.is-the-point --contexts 8
        one rule (repeatable), with sampled contexts
    corpusscan.py scan DIR --candidate "soft_phrases:the one that" --contexts 8
        a rule that is not in the config yet, tried as an add_<field> entry;
        also a JSON object {"field": ..., "pattern": ..., "id": ...}
    corpusscan.py review DIR --surface S --out labels.jsonl [--per-rule 10] [--unflagged 20]
        a labelling sample: hits per rule and unflagged paragraphs, for TP/FP and missed-rule labels
    corpusscan.py score-review labels.jsonl [...]
        precision per rule per surface, misses named, false flags per 1,000 words
    corpusscan.py diff DIR --old OLD_BASE.json --new NEW_BASE.json [--config OVERLAY]
        what a release changes on this corpus: rules added and removed, per-rule
        deltas, findings that appear and disappear, with contexts for the new ones

Corpus files: *.md, *.txt, *.html under each DIR, recursively, or files given
directly; --ext (repeatable) replaces that set, --exclude GLOB (repeatable,
matched against the path relative to DIR) drops files. --json prints the same as a document
with the tool version, the sha256 of every config involved, and the corpus
size, which is what a dated snapshot should keep.

Every number here is a raw hit count. A hit means the configured pattern is
present; it is not a confirmed violation until someone has read the context.
The output says so, and nothing in it auto-promotes a rule.

Stdlib only.
"""
from __future__ import annotations
import argparse
import collections
import datetime
import fnmatch
import hashlib
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import voicelint  # noqa: E402
import pherkad  # noqa: E402

DEFAULT_EXTS = (".md", ".txt", ".html", ".htm")


def _version() -> str:
    try:
        with open(os.path.join(HERE, "..", "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return "unknown"


def _sha(path: str | None) -> str:
    if not path or not os.path.exists(path):
        return ""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def collect_files(paths: list[str], exts=DEFAULT_EXTS, exclude: list[str] | None = None) -> list[str]:
    """Corpus files, sorted: directories are walked; files are taken as given."""
    out = []
    for p in paths:
        if os.path.isfile(p):
            out.append(os.path.abspath(p))
            continue
        if not os.path.isdir(p):
            sys.stderr.write(f"corpusscan: no such file or directory: {p}\n")
            sys.exit(2)
        for root, _dirs, files in os.walk(p):
            for f in files:
                if not f.lower().endswith(tuple(exts)):
                    continue
                full = os.path.join(root, f)
                rel = os.path.relpath(full, p)
                if any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(f, g) for g in (exclude or [])):
                    continue
                out.append(os.path.abspath(full))
    return sorted(set(out))


def parse_candidate(spec: str) -> dict:
    """``field:pattern`` or a JSON object with at least field and pattern."""
    if spec.lstrip().startswith("{"):
        try:
            d = json.loads(spec)
        except json.JSONDecodeError as exc:
            sys.stderr.write(f"corpusscan: candidate is not valid JSON: {exc}\n")
            sys.exit(2)
        if not isinstance(d, dict) or "field" not in d or "pattern" not in d:
            sys.stderr.write("corpusscan: a JSON candidate needs 'field' and 'pattern'\n")
            sys.exit(2)
        return d
    if ":" not in spec:
        sys.stderr.write("corpusscan: candidate must be field:pattern or a JSON object\n")
        sys.exit(2)
    field, pattern = spec.split(":", 1)
    return {"field": field.strip(), "pattern": pattern}


def config_with_candidates(cfg: dict, candidates: list[dict]) -> tuple[dict, list[str]]:
    """The effective config plus the candidate rules, and the ids they got."""
    cfg = json.loads(json.dumps(cfg))
    ids = []
    for c in candidates:
        field = c["field"]
        if field not in voicelint._LIST_FIELDS:
            sys.stderr.write(f"corpusscan: candidate field must be one of {', '.join(voicelint._LIST_FIELDS)}\n")
            sys.exit(2)
        entry = {k: v for k, v in c.items() if k != "field"}
        entry = voicelint._norm_entry(field, entry)
        existing = {e["id"]: e for e in voicelint.rule_entries(cfg, field)}
        if entry["id"] in existing or any(e["pattern"] == entry["pattern"] for e in existing.values()):
            sys.stderr.write(f"corpusscan: candidate '{entry['pattern']}' is already the rule "
                             f"{entry['id']}; count it with --rule {entry['id']}\n")
            sys.exit(2)
        cfg.setdefault(field, []).append(entry)
        ids.append(entry["id"])
    voicelint._validate({k: v for k, v in cfg.items() if k in voicelint._KNOWN_KEYS})
    return cfg, ids


def run_corpus(files: list[str], cfg: dict, base: str | None = None, structure: bool = True) -> dict:
    """Both engines over every file (pherkad.run_text, no density); return
    per-file findings as dicts, words, and the effective rules. Structural
    rules count here too, so a surface's thresholds can be calibrated."""
    per_file = {}
    words = 0
    for path in files:
        try:
            text = voicelint.read_source(path, False)
        except OSError as exc:
            sys.stderr.write(f"corpusscan: {exc}\n")
            continue
        words += len(re.findall(r"\w+", text))
        findings, _ = pherkad.run_text(text, cfg, structure=structure, density=False)
        per_file[path] = (findings, text)
    return {"per_file": per_file, "words": words, "rules": {r["id"]: r for r in pherkad.all_rules(cfg)}}


def _context(text: str, line: int, col: int, match: str, width: int = 60) -> str:
    lines = text.split("\n")
    if not 1 <= line <= len(lines):
        return ""
    ln = lines[line - 1]
    c = max(0, col - 1)
    left = ln[max(0, c - width):c]
    right = ln[c + len(match):c + len(match) + width]
    return (("…" if c - width > 0 else "") + left + "[" + ln[c:c + len(match)] + "]" + right
            + ("…" if c + len(match) + width < len(ln) else "")).strip()


def summarize(result: dict, roots: list[str], only: set[str] | None = None,
              contexts: int = 0, seed: int = 1) -> dict:
    """Per-rule counts over the corpus, with sampled contexts when asked."""
    hits = collections.Counter()
    files_hit = collections.defaultdict(set)
    samples = collections.defaultdict(list)
    sev = collections.Counter()
    for path, (findings, text) in result["per_file"].items():
        for f in findings:
            if only and f["rule_id"] not in only:
                continue
            hits[f["rule_id"]] += 1
            files_hit[f["rule_id"]].add(path)
            sev[f["severity"]] += 1
            samples[f["rule_id"]].append((path, f["line"], _context(text, f["line"], f["col"], f["match"])))
    words = result["words"] or 1
    rng = random.Random(seed)
    rows = []
    for rid, n in hits.most_common():
        meta = result["rules"].get(rid, {"family": rid.split(".")[0], "severity": "?", "pattern": ""})
        row = {"rule_id": rid, "family": meta["family"], "severity": meta["severity"],
               "pattern": meta.get("pattern", ""), "hits": n, "files": len(files_hit[rid]),
               "per_1k_words": round(n * 1000 / words, 2)}
        if contexts:
            pick = samples[rid] if len(samples[rid]) <= contexts else rng.sample(samples[rid], contexts)
            row["contexts"] = [{"file": _rel(p, roots), "line": ln, "text": ctx} for p, ln, ctx in sorted(pick)]
        rows.append(row)
    if only:
        for rid in sorted(only - set(hits)):
            meta = result["rules"].get(rid)
            if meta:
                rows.append({"rule_id": rid, "family": meta["family"], "severity": meta["severity"],
                             "pattern": meta.get("pattern", ""), "hits": 0, "files": 0, "per_1k_words": 0.0,
                             **({"contexts": []} if contexts else {})})
    return {"files": len(result["per_file"]), "words": result["words"],
            "errors": sev["error"], "warnings": sev["warning"],
            "per_1k_words": round((sev["error"] + sev["warning"]) * 1000 / words, 2), "rules": rows}


def _rel(path: str, roots: list[str]) -> str:
    for r in roots:
        r = os.path.abspath(r)
        if os.path.isdir(r) and path.startswith(r + os.sep):
            return os.path.relpath(path, r)
    return path


def _keyset(result: dict, roots: list[str]) -> dict:
    return {(_rel(p, roots), f["line"], f["rule_id"], f["match"].lower()): (p, f, text)
            for p, (findings, text) in result["per_file"].items() for f in findings}


def _layered(surface: str | None, overlay: str | None, base: str | None = None) -> dict:
    """Base (shipped, or the one given), then the surface's overlay, then the project's."""
    info = pherkad.resolve_surface(surface) if surface else None
    cfg = voicelint.load_config(info["overlay"] if info and info["overlay"] else None, base=base)
    if overlay:
        ov = voicelint._read_json(overlay, "config")
        cfg = voicelint._apply_list_ops(voicelint._deep_merge(cfg, ov))
    return cfg


def diff_corpus(files: list[str], old_base: str, new_base: str, overlay: str | None,
                roots: list[str], contexts: int = 3, seed: int = 1, surface: str | None = None) -> dict:
    old_cfg = _layered(surface, overlay, old_base)
    new_cfg = _layered(surface, overlay, new_base)
    old = run_corpus(files, old_cfg)
    new = run_corpus(files, new_cfg)
    # A rule whose id changed but whose pattern did not (a string that became
    # an object with an explicit id) is the same rule; report it under the new
    # id rather than as one removal and one addition.
    new_by_pattern = {r["pattern"]: rid for rid, r in new["rules"].items() if r.get("pattern")}
    renamed = {rid: new_by_pattern[r["pattern"]] for rid, r in old["rules"].items()
               if r.get("pattern") in new_by_pattern and new_by_pattern[r["pattern"]] != rid}
    for rid, target in renamed.items():
        old["rules"][target] = old["rules"].pop(rid)
    for findings, _ in old["per_file"].values():
        for f in findings:
            if f["rule_id"] in renamed:
                f["rule_id"] = renamed[f["rule_id"]]
    ok, nk = _keyset(old, roots), _keyset(new, roots)
    appeared = [nk[k] for k in nk.keys() - ok.keys()]
    vanished = [ok[k] for k in ok.keys() - nk.keys()]
    old_rules, new_rules = set(old["rules"]), set(new["rules"])

    def per_rule(items):
        c = collections.Counter(f["rule_id"] for _, f, _ in items)
        return c

    app_c, van_c = per_rule(appeared), per_rule(vanished)
    old_counts = collections.Counter(f["rule_id"] for fs, _ in old["per_file"].values() for f in fs)
    new_counts = collections.Counter(f["rule_id"] for fs, _ in new["per_file"].values() for f in fs)
    rows = []
    for rid in sorted(set(old_counts) | set(new_counts) | app_c.keys() | van_c.keys(),
                      key=lambda r: -(app_c[r] + van_c[r])):
        if old_counts[rid] == new_counts[rid] and not app_c[rid] and not van_c[rid]:
            continue
        meta = new["rules"].get(rid) or old["rules"].get(rid) or {}
        rows.append({"rule_id": rid, "severity": meta.get("severity", "?"),
                     "old": old_counts[rid], "new": new_counts[rid],
                     "appeared": app_c[rid], "vanished": van_c[rid],
                     "status": ("added" if rid in new_rules - old_rules else
                                "removed" if rid in old_rules - new_rules else "changed")})
    rng = random.Random(seed)
    by_rule = collections.defaultdict(list)
    for p, f, text in appeared:
        by_rule[f["rule_id"]].append((_rel(p, roots), f["line"], _context(text, f["line"], f["col"], f["match"])))
    samples = {rid: sorted(v if len(v) <= contexts else rng.sample(v, contexts)) for rid, v in by_rule.items()}

    def sev_counts(res):
        c = collections.Counter(f["severity"] for fs, _ in res["per_file"].values() for f in fs)
        return {"errors": c["error"], "warnings": c["warning"]}

    return {"files": len(files), "words": new["words"],
            "old": sev_counts(old), "new": sev_counts(new),
            "rules_added": sorted(new_rules - old_rules), "rules_removed": sorted(old_rules - new_rules),
            "rules_renamed": dict(sorted(renamed.items())),
            "appeared": len(appeared), "vanished": len(vanished), "rules": rows,
            "contexts": {rid: [{"file": p, "line": ln, "text": t} for p, ln, t in v] for rid, v in samples.items()}}


# ---------------------------------------------------------------------------
# Labelled calibration (roadmap item 17)
# ---------------------------------------------------------------------------
# A count says how often a rule fires; it cannot say how often it is right.
# `review` exports a sample of hits per rule, and a sample of paragraphs on
# which nothing fired, as JSONL for a reader to label; `score-review` turns
# the labels into precision per rule per surface, misses the reader named on
# the unflagged units, and false flags per 1,000 words. The labels file is
# the reader's; the tool never writes a label.
def export_review(files: list[str], cfg: dict, roots: list[str], surface: str, per_rule: int,
                  unflagged: int, seed: int, only: set | None = None) -> list[dict]:
    result = run_corpus(files, cfg)
    rng = random.Random(seed)
    hits = collections.defaultdict(list)
    clean_paras = []
    for path, (findings, text) in result["per_file"].items():
        lines = text.split("\n")
        flagged_lines = {f["line"] for f in findings}
        for f in findings:
            if not f["line"] or (only and f["rule_id"] not in only):
                continue
            hits[f["rule_id"]].append({"type": "hit", "surface": surface, "rule_id": f["rule_id"],
                                       "path": _rel(path, roots), "line": f["line"],
                                       "source_hash": hashlib.sha256(" ".join(lines[f["line"] - 1].split()).encode()).hexdigest()[:16],
                                       "span": f["match"], "context": _context(text, f["line"], f["col"], f["match"]),
                                       "severity": f["severity"], "label": ""})
        # unflagged paragraphs: a run of prose lines with no finding on any of them
        start = None
        for i, ln in enumerate(lines + [""], 1):
            if ln.strip():
                if start is None:
                    start = i
            elif start is not None:
                block = range(start, i)
                if len(block) and not any(j in flagged_lines for j in block):
                    para = " ".join(lines[j - 1].strip() for j in block)
                    if 40 <= len(para.split()) <= 200:
                        clean_paras.append({"type": "unflagged", "surface": surface, "rule_id": "",
                                            "path": _rel(path, roots), "line": start,
                                            "source_hash": hashlib.sha256(" ".join(para.split()).encode()).hexdigest()[:16],
                                            "span": "", "context": para[:600], "severity": "", "label": ""})
                start = None
    out = [{"type": "meta", "surface": surface, "files": len(result["per_file"]), "words": result["words"],
            "base_sha256": _sha(voicelint.DEFAULTS_PATH), "date": datetime.date.today().isoformat(),
            "per_rule": per_rule, "unflagged": unflagged, "seed": seed,
            "labels": "hit: TP (a real tell) or FP (the writer's own usage); unflagged: clean, or the rule_id that should have fired"}]
    for rid in sorted(hits):
        rows = hits[rid]
        out.extend(sorted(rows if len(rows) <= per_rule else rng.sample(rows, per_rule), key=lambda r: (r["path"], r["line"])))
    if clean_paras:
        out.extend(sorted(clean_paras if len(clean_paras) <= unflagged else rng.sample(clean_paras, unflagged),
                          key=lambda r: (r["path"], r["line"])))
    return out


def score_review(paths: list[str]) -> dict:
    per = {}   # (surface, rule_id) -> [tp, fp]
    misses = collections.Counter()  # (surface, rule_id named on an unflagged unit)
    clean = collections.Counter()
    unlabelled = collections.Counter()
    words = collections.Counter()
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError as exc:
                    sys.stderr.write(f"corpusscan: {p}:{n} is not JSON: {exc}\n")
                    sys.exit(2)
                if r.get("type") == "meta":
                    words[r.get("surface", "")] += int(r.get("words", 0))
                    continue
                lab = (r.get("label") or "").strip()
                surf = r.get("surface", "")
                if r.get("type") == "hit":
                    if lab.upper() == "TP":
                        per.setdefault((surf, r["rule_id"]), [0, 0])[0] += 1
                    elif lab.upper() == "FP":
                        per.setdefault((surf, r["rule_id"]), [0, 0])[1] += 1
                    else:
                        unlabelled["hit"] += 1
                elif r.get("type") == "unflagged":
                    if lab.lower() == "clean":
                        clean[surf] += 1
                    elif lab:
                        misses[(surf, lab)] += 1
                    else:
                        unlabelled["unflagged"] += 1
    rows = []
    for (surf, rid), (tp, fp) in sorted(per.items(), key=lambda kv: (kv[0][0], -(kv[1][1]), kv[0][1])):
        rows.append({"surface": surf, "rule_id": rid, "tp": tp, "fp": fp,
                     "precision": round(tp / (tp + fp), 2) if tp + fp else None,
                     "false_flags_per_1k": round(fp * 1000 / words[surf], 2) if words.get(surf) else None})
    return {"rules": rows, "misses": [{"surface": s_, "rule_id": r_, "count": c} for (s_, r_), c in misses.most_common()],
            "clean_units": dict(clean), "unlabelled": dict(unlabelled), "words": dict(words)}


def render_review_score(sc: dict) -> str:
    out = ["# Labelled calibration", ""]
    if sc["unlabelled"]:
        out.append(f"Unlabelled: {sc['unlabelled']}. Precision counts labelled hits only.")
        out.append("")
    if sc["rules"]:
        w = max(len(r["rule_id"]) for r in sc["rules"])
        out.append(f"{'surface':<14} {'rule':<{w}}  {'TP':>4} {'FP':>4} {'prec':>5} {'FP/1k':>6}")
        for r in sc["rules"]:
            prec = "" if r["precision"] is None else f"{r['precision']:.2f}"
            ff = "" if r["false_flags_per_1k"] is None else str(r["false_flags_per_1k"])
            out.append(f"{r['surface']:<14} {r['rule_id']:<{w}}  {r['tp']:>4} {r['fp']:>4} {prec:>5} {ff:>6}")
    if sc["misses"]:
        out += ["", "Misses the reader named on unflagged units (a rule that should have fired):"]
        for m in sc["misses"]:
            out.append(f"  {m['surface']:<14} {m['rule_id']}  x{m['count']}")
    if sc["clean_units"]:
        out += ["", f"Unflagged units confirmed clean: {sc['clean_units']}"]
    return "\n".join(out)


# ---------------------------------------------------------------------------
def render_scan(s: dict, title: str) -> str:
    out = [f"# {title}", "",
           f"{s['files']} file(s), {s['words']:,} words: {s['errors']} error(s), {s['warnings']} warning(s), "
           f"{s['per_1k_words']} per 1,000 words. Raw hits, not confirmed violations.", ""]
    if s["rules"]:
        w = max(len(r["rule_id"]) for r in s["rules"])
        out.append(f"{'rule':<{w}}  {'sev':<7} {'hits':>5} {'files':>5} {'per 1k':>7}  pattern")
        for r in s["rules"]:
            out.append(f"{r['rule_id']:<{w}}  {r['severity']:<7} {r['hits']:>5} {r['files']:>5} "
                       f"{r['per_1k_words']:>7}  {r['pattern'][:60]}")
            for c in r.get("contexts", []):
                out.append(f"{'':<{w}}    {c['file']}:{c['line']}  {c['text']}")
    return "\n".join(out)


def render_diff(d: dict, old_label: str, new_label: str) -> str:
    out = [f"# Release diff on {d['files']} file(s), {d['words']:,} words", "",
           f"old ({old_label}): {d['old']['errors']} error(s), {d['old']['warnings']} warning(s)",
           f"new ({new_label}): {d['new']['errors']} error(s), {d['new']['warnings']} warning(s)",
           f"{d['appeared']} finding(s) appear, {d['vanished']} vanish. Raw hits, not confirmed violations.", ""]
    if d["rules_added"]:
        out.append("rules added:   " + ", ".join(d["rules_added"]))
    if d["rules_removed"]:
        out.append("rules removed: " + ", ".join(d["rules_removed"]))
    if d.get("rules_renamed"):
        out.append("rules renamed: " + ", ".join(f"{a} -> {b}" for a, b in d["rules_renamed"].items()))
    if d["rules"]:
        w = max(len(r["rule_id"]) for r in d["rules"])
        out += ["", f"{'rule':<{w}}  {'sev':<7} {'old':>5} {'new':>5} {'+':>5} {'-':>5}  status"]
        for r in d["rules"]:
            out.append(f"{r['rule_id']:<{w}}  {r['severity']:<7} {r['old']:>5} {r['new']:>5} "
                       f"{r['appeared']:>5} {r['vanished']:>5}  {r['status']}")
            for c in d["contexts"].get(r["rule_id"], []):
                out.append(f"{'':<{w}}    {c['file']}:{c['line']}  {c['text']}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Count the voice rules against a corpus.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("paths", nargs="+", help="corpus directories or files")
        p.add_argument("--config", help="overlay config (for example a downstream project's)")
        p.add_argument("--surface", help="a surface (its overlay and thresholds are applied before --config)")
        p.add_argument("--no-structure", action="store_true", help="voicelint rules only")
        p.add_argument("--ext", action="append", default=[], help="file extension to include (repeatable; replaces the default .md .txt .html)")
        p.add_argument("--exclude", action="append", default=[], help="glob to skip, against the path relative to its directory")
        p.add_argument("--contexts", type=int, default=None, help="sampled contexts per rule")
        p.add_argument("--seed", type=int, default=1, help="sampling seed")
        p.add_argument("--json", action="store_true", help="machine-readable output")

    ps = sub.add_parser("scan", help="count every rule, one rule, or a candidate rule")
    common(ps)
    ps.add_argument("--rule", action="append", default=[], help="restrict to this rule id (repeatable)")
    ps.add_argument("--candidate", action="append", default=[],
                    help="try a rule not in the config: field:pattern or a JSON object (repeatable)")
    pr = sub.add_parser("review", help="export a labelled-calibration sample: hits per rule plus unflagged units, as JSONL")
    common(pr)
    pr.add_argument("--rule", action="append", default=[], help="restrict to this rule id (repeatable)")
    pr.add_argument("--per-rule", type=int, default=10, help="hits sampled per rule")
    pr.add_argument("--unflagged", type=int, default=20, help="unflagged paragraphs sampled")
    pr.add_argument("--out", required=True, help="the JSONL file for the reader to label")
    psr = sub.add_parser("score-review", help="precision per rule per surface from labelled JSONL")
    psr.add_argument("labels", nargs="+")
    psr.add_argument("--json", action="store_true")
    pd = sub.add_parser("diff", help="what a new base rule set changes on the corpus under one overlay")
    common(pd)
    pd.add_argument("--old", required=True, help="the old base voice_config.json")
    pd.add_argument("--new", required=True, help="the new base voice_config.json")
    args = ap.parse_args(argv)

    if args.cmd == "score-review":
        sc = score_review(args.labels)
        print(json.dumps(sc, indent=2, ensure_ascii=False) if args.json else render_review_score(sc))
        return 0
    exts = tuple(e if e.startswith(".") else "." + e for e in args.ext) or DEFAULT_EXTS
    files = collect_files(args.paths, exts, args.exclude)
    if not files:
        sys.stderr.write("corpusscan: no corpus files found\n")
        return 2
    stamp = {"tool_version": _version(), "date": datetime.date.today().isoformat(),
             "overlay": args.config or "", "overlay_sha256": _sha(args.config),
             "files": len(files)}

    if args.cmd == "review":
        cfg = _layered(args.surface, args.config)
        rows = export_review(files, cfg, args.paths, args.surface or "", args.per_rule, args.unflagged,
                             args.seed, set(args.rule) or None)
        with open(args.out, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        n_hits = sum(1 for r in rows if r["type"] == "hit")
        n_un = sum(1 for r in rows if r["type"] == "unflagged")
        print(f"corpusscan: wrote {args.out}: {n_hits} hit(s) across {len({r['rule_id'] for r in rows if r['type'] == 'hit'})} rule(s) "
              f"and {n_un} unflagged unit(s) to label (TP/FP on hits; clean or a rule_id on unflagged units)")
        return 0
    if args.cmd == "scan":
        cfg = _layered(args.surface, args.config)
        only = set(args.rule)
        title = "Corpus scan"
        if args.candidate:
            cfg, ids = config_with_candidates(cfg, [parse_candidate(c) for c in args.candidate])
            only |= set(ids)
            title = "Candidate rule(s): " + ", ".join(ids)
        elif only:
            title = "Rule(s): " + ", ".join(sorted(only))
        contexts = args.contexts if args.contexts is not None else (5 if only else 0)
        result = run_corpus(files, cfg, structure=not args.no_structure)
        s = summarize(result, args.paths, only or None, contexts, args.seed)
        s.update(stamp, base_sha256=_sha(voicelint.DEFAULTS_PATH), candidates=args.candidate)
        print(json.dumps(s, indent=2, ensure_ascii=False) if args.json else render_scan(s, title))
        return 0

    contexts = args.contexts if args.contexts is not None else 3
    d = diff_corpus(files, args.old, args.new, args.config, args.paths, contexts, args.seed, args.surface)
    d.update(stamp, old_base=args.old, old_sha256=_sha(args.old), new_base=args.new, new_sha256=_sha(args.new))
    print(json.dumps(d, indent=2, ensure_ascii=False) if args.json else render_diff(d, args.old, args.new))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        sys.stderr.write(f"corpusscan: unexpected error: {exc}\n")
        sys.exit(2)
