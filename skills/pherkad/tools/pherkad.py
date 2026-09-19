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
    pherkad.py check --surface fiction --config OV   # a surface, then a project overlay on top
    pherkad.py surfaces [--surfaces MAP] [--json]    # every surface, with speaker and register
    pherkad.py review-pack --surface X FILE          # the quick-mode judgment packet: prompt, or --format json, or --out DIR
    pherkad.py review-import TABLE --file FILE --decisions D   # record a table's ruled rows; the next packet lists them
    pherkad.py check --format json FILE              # voicelint's envelope, plus provenance
    pherkad.py check --format sarif FILE             # SARIF 2.1.0 for editors and CI
    pherkad.py check --advisory structure. FILE      # report, never count, rule ids under a prefix
    pherkad.py check --fingerprint F FILE            # measured voice.* findings against the author's fingerprint (advisory)
    pherkad.py check --strict FILE                   # warnings fail too
    pherkad.py check --no-structure FILE             # voicelint only
    pherkad.py rules [--config OVERLAY] [--json]     # every rule both engines would run
    pherkad.py manifest [--write | --verify]         # the release manifest: version, file hashes, rule ids
    pherkad.py check-overlay OVERLAY                 # does a downstream overlay still fit this base?
    pherkad.py check --decisions FILE ...            # hide findings the author has decided on
    pherkad.py decide --decisions FILE --reason "..." path:line[:rule_id] ...
    pherkad.py decisions --decisions FILE [--prune] FILE...   # which decisions still match

Decisions (roadmap item 7). A warning the author has read and accepted should
stay quiet until something about it changes, and nothing else should. A
decision file is a project-owned JSON list of records:

    {"rule_id": "soft.is-the-whole", "path": "canon/x.md", "context_hash": "…",
     "rule_hash": "…", "count": 1, "disposition": "accepted", "reason": "…",
     "decided": "2026-09-15"}

The context is the line the finding sits on, whitespace collapsed, or for a
structural finding the whole paragraph, since structlint reports a paragraph
against its first line; the rule hash is the rule's pattern, plus the
thresholds for a structural rule. A finding matches a decision when rule id,
path, context, and rule all match, up to ``count`` occurrences on that line;
a changed line, a changed rule, or an extra occurrence surfaces the finding
again as new. Decided findings are hidden from the list (``--show-decided``
prints them) and never counted toward the exit; the summary says how many.
Nothing here writes a decision except ``decide``, which requires a reason.
Dispositions: accepted (the author's usage), intentional (a deliberate
choice), deferred (known, fix later; still hidden, counted separately so the
debt stays visible). Paths are relative to ``--root`` (default: the decision
file's directory).

Release manifest (roadmap item 8). ``bundle-manifest.json`` beside this
script records the version, a schema number, the sha256 of every vendored
file, and every rule id the shipped base runs. ``manifest --write`` is run at
release; ``manifest --verify`` (in CI here, and in a downstream sync check)
fails when a file beside the script no longer matches, which is how a vendored
copy proves it is what it says it is. ``check-overlay`` loads a downstream
overlay on this base and reports what would silently do nothing: a
``remove_<field>`` naming a rule that is not here, an ``add_<field>`` that
duplicates a shipped rule, a structure key the base does not know; and it
runs every ``fires``/``clean`` example the overlay's rule objects carry.

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
    """VERSION from the skill root when this runs in the repository; the
    manifest's version when this is a vendored copy, which carries no VERSION."""
    try:
        with open(os.path.join(HERE, "..", "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        pass
    try:
        with open(os.path.join(HERE, "bundle-manifest.json"), encoding="utf-8") as fh:
            return json.load(fh).get("version", "unknown")
    except (OSError, json.JSONDecodeError):
        return "unknown"


# ---------------------------------------------------------------------------
# Surfaces (roadmap item 11)
# ---------------------------------------------------------------------------
# A surface names what the text is: who is speaking (the assistant to the
# author, or the author as himself) and whether the positive register is
# expected. It resolves to an overlay, guidance, and optionally a few approved
# excerpts. Shipped surfaces live in surfaces/<name>.json with a "_surface"
# block; a user map (surfaces.json, --surfaces, or PHERKAD_SURFACES) is
# consulted first and may add surfaces or point a shipped name at its own
# overlay and excerpts. An unknown surface is an error, never a guess.
SPEAKERS = ("assistant", "author")
REGISTERS = ("no", "profile", "frame", "yes", "own-voice-document")


def _user_map_path(explicit: str | None) -> str | None:
    for cand in (explicit, os.environ.get("PHERKAD_SURFACES"), os.path.join(os.getcwd(), "surfaces.json")):
        if cand and os.path.exists(cand):
            return cand
    return None


def load_surface_map(explicit: str | None = None) -> tuple[dict, str | None]:
    """The user's surface map (name -> entry) and where it came from."""
    path = _user_map_path(explicit)
    if not path:
        return {}, None
    try:
        with open(path, encoding="utf-8") as fh:
            m = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"pherkad: cannot read surface map {path}: {exc}\n")
        sys.exit(2)
    if not isinstance(m, dict):
        sys.stderr.write(f"pherkad: surface map {path} must be a JSON object of name -> entry\n")
        sys.exit(2)
    return {k: v for k, v in m.items() if not k.startswith("_")}, path


def shipped_surfaces() -> list[str]:
    if not os.path.isdir(SURFACES):
        return []
    return sorted(f[:-5] for f in os.listdir(SURFACES) if f.endswith(".json"))


def resolve_surface(name: str, map_path: str | None = None) -> dict:
    """A surface's overlay path, speaker, register, guidance, and excerpts.
    A path (or something ending in .json) is taken as an overlay file with
    its own optional _surface block."""
    user_map, map_file = load_surface_map(map_path)
    base_dir = os.path.dirname(os.path.abspath(map_file)) if map_file else os.getcwd()
    entry = {}
    if os.path.sep in name or name.endswith(".json"):
        overlay = name
        if not os.path.exists(overlay):
            sys.stderr.write(f"pherkad: no surface file at {overlay}\n")
            sys.exit(2)
    elif name in user_map:
        entry = user_map[name] if isinstance(user_map[name], dict) else {}
        overlay = entry.get("overlay")
        overlay = os.path.join(base_dir, overlay) if overlay and not os.path.isabs(overlay) else overlay
        if not overlay:
            overlay = os.path.join(SURFACES, name + ".json") if name in shipped_surfaces() else None
        if overlay and not os.path.exists(overlay):
            sys.stderr.write(f"pherkad: surface '{name}' in {map_file} points at a missing overlay {overlay}\n")
            sys.exit(2)
    elif name in shipped_surfaces():
        overlay = os.path.join(SURFACES, name + ".json")
    else:
        have = sorted(set(shipped_surfaces()) | set(user_map))
        sys.stderr.write(f"pherkad: unknown surface '{name}'; have {', '.join(have) or 'none'}"
                         + (f" (map: {map_file})" if map_file else "") + "\n")
        sys.exit(2)
    meta = {}
    if overlay:
        try:
            with open(overlay, encoding="utf-8") as fh:
                meta = (json.load(fh).get("_surface") or {})
        except (OSError, json.JSONDecodeError) as exc:
            sys.stderr.write(f"pherkad: cannot read overlay {overlay}: {exc}\n")
            sys.exit(2)
    speaker = entry.get("speaker") or meta.get("speaker") or "author"
    register = entry.get("positive_register") or meta.get("positive_register") or "profile"
    if speaker not in SPEAKERS:
        sys.stderr.write(f"pherkad: surface '{name}': speaker must be one of {', '.join(SPEAKERS)}\n")
        sys.exit(2)
    if register not in REGISTERS:
        sys.stderr.write(f"pherkad: surface '{name}': positive_register must be one of {', '.join(REGISTERS)}\n")
        sys.exit(2)
    excerpts = []
    for e in entry.get("excerpts", []) or []:
        pth = e if os.path.isabs(e) else os.path.join(base_dir, e)
        excerpts.append({"path": pth, "exists": os.path.exists(pth)})
    guidance = " ".join(x for x in (meta.get("guidance", ""), entry.get("guidance", "")) if x).strip()
    return {"name": name, "overlay": overlay, "speaker": speaker, "positive_register": register,
            "guidance": guidance, "excerpts": excerpts, "from_map": bool(entry)}


def load_layers(surface: str | None, config: str | None, map_path: str | None = None) -> tuple[dict, dict | None]:
    """The effective config: shipped base, then the surface's overlay, then the
    project overlay, in that order. Returns (cfg, surface info or None)."""
    info = resolve_surface(surface, map_path) if surface else None
    cfg = voicelint.load_config(info["overlay"] if info and info["overlay"] else None)
    if config:
        if info and info["overlay"] and os.path.exists(config) and os.path.samefile(config, info["overlay"]):
            return cfg, info
        ov = voicelint._read_json(config, "config")
        cfg = voicelint._apply_list_ops(voicelint._deep_merge(cfg, ov))
    elif not info:
        cfg = voicelint.load_config(None)
    return cfg, info


def resolve_config(surface: str | None, config: str | None) -> str | None:
    """Kept for callers that want one overlay path: the surface's overlay when
    a surface is named alone, the config file otherwise."""
    if surface and config:
        return None
    if surface:
        return resolve_surface(surface)["overlay"]
    return config


def config_sha256(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------
DISPOSITIONS = ("accepted", "intentional", "deferred")
_DECISION_KEYS = frozenset({"rule_id", "path", "context_hash", "rule_hash", "count",
                            "disposition", "reason", "decided", "line", "match", "note", "scope", "quote"})
JUDGMENT_PREFIX = "judgment."
JUDGMENT_HASH = "judgment"  # a judgment record has no pattern to hash; the reference itself is the rule


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def context_hash(text: str, line: int, paragraph: bool = False) -> str:
    """The hash of what a finding sits on, whitespace collapsed: the line for a
    phrase finding; for a structural finding, the whole paragraph from that
    line to the next blank line, because structlint reports a paragraph
    against its first line and an edit further down would otherwise leave an
    old decision in force. A finding at line 0 (the density) has no context."""
    lines = text.split("\n")
    if not 1 <= line <= len(lines):
        return ""
    if not paragraph:
        return _hash(" ".join(lines[line - 1].split()))
    block = []
    for ln in lines[line - 1:]:
        if not ln.strip():
            break
        block.append(ln)
    return _hash(" ".join(" ".join(block).split()))


def _scope(f: dict) -> bool:
    return f.get("engine") == "structure"


DOCUMENT_RULES = ("frame", "interrogative-headers")


def _document_context(f: dict) -> str | None:
    """A document-level finding (the repeated frame, the heading rate) is keyed
    on the units it quotes, not on any one line: its match lists them all."""
    if f.get("rule") in DOCUMENT_RULES:
        return _hash(" ".join(f["match"].split()))
    return None


def rule_hashes(cfg: dict) -> dict:
    """Rule id -> hash of what would change the rule: the pattern, and for the
    structural rules and the density, the thresholds too, so a decision made
    under one threshold does not survive a change to it."""
    thresholds = json.dumps(cfg.get("structure") or {}, sort_keys=True)
    out = {}
    for r in all_rules(cfg):
        seed = r.get("pattern", "")
        if r["id"].startswith("structure.") or r["id"] == "density":
            family = r["id"].split(".")[1] if r["id"].startswith("structure.") else "density"
            seed += "|" + thresholds + "|rev" + str(structlint.STRUCT_REVISION.get(family, 0))
        out[r["id"]] = _hash(seed)
    return out


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
        key = (f["rule_id"], _document_context(f) or context_hash(text, f["line"], _scope(f)))
        slot = budget.get(key)
        if slot and slot[1] > 0:
            slot[1] -= 1
            f["decision"] = slot[0]
            if slot[0] not in used:
                used.append(slot[0])
    return used


def density_finding(findings: list[dict], text: str, cfg: dict) -> dict | None:
    """One ``combined`` density finding over ``findings``, or None. Callers
    pass the findings that COUNT: not advisory, not decided; a density built
    from findings the gate has set aside would block on what it agreed to
    ignore, which is the bug Codex reproduced on 2026-09-15."""
    words = len(re.findall(r"\b\w+\b", voicelint.mask_code(text)))
    cap = float((cfg.get("structure") or {}).get("density_per_100", structlint.DEFAULT_THRESHOLDS["density_per_100"]))
    if words < 100 or cap <= 0:
        return None
    per100 = len(findings) * 100.0 / words
    if per100 <= cap:
        return None
    return {"line": 0, "col": 0, "severity": "warning", "rule": "density",
            "match": f"{len(findings)} findings / {words} words",
            "message": f"{per100:.1f} flagged constructions per 100 words, over the {cap} cap",
            "rule_id": "density", "engine": "combined"}


def run_text(text: str, cfg: dict, structure: bool = True, density: bool = True) -> tuple[list[dict], int]:
    """Both engines over ``text``: one list of finding dicts in the shared
    schema, sorted by position, plus the number of findings an inline
    directive suppressed. Structural findings carry ``engine`` structure; the
    per-document density is one ``combined`` finding over every finding, unless
    ``density`` is False, in which case the caller computes it over the
    findings that count (see cmd_check)."""
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
    if density:
        d = density_finding(out, text, cfg)
        if d:
            out.append(d)
    return out, suppressed


def all_rules(cfg: dict) -> list[dict]:
    rows = voicelint.all_rules(cfg)
    for check, desc in (("two-beat", "clipped balanced parallel"), ("staccato", "run of short sentences"),
                        ("header", "heading that strikes a pose"), ("aphorism", "manufactured maxim"),
                        ("interrogative-headers", "rate of question-word headings")):
        rows.append({"id": "structure." + check, "family": check, "severity": "warning",
                     "pattern": desc, "rationale": ""})
    for name in structlint.FRAMES:
        for kind in ("heading", "sentence", "closer"):
            rows.append({"id": f"structure.frame.{name}.{kind}", "family": "frame", "severity": "warning",
                         "pattern": f"the '{name}' frame recurring across {kind}s", "rationale": ""})
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


def voice_findings(text: str, fp: dict, surface_name: str | None, threshold: float, ref: dict | None = None) -> list[dict]:
    """Advisory findings from the measured profile: one per feature that sits
    past `threshold` of the author's own standard deviations, quoting the
    text's sentence and the author's; with a reference profile, the
    discriminant (nearer the author or nearer the reference) as well.
    Never counted in density; never an error."""
    import fingerprint as fpm
    res = fpm.compare(text, fp, surface_name, threshold, ref)
    if "error" in res:
        return []
    lines = text.split("\n")
    out = []
    for d in res["flagged"]:
        quote = d.get("quote") or ""
        line = next((i for i, ln in enumerate(lines, 1) if quote[:40] and quote[:40] in " ".join(ln.split())), 0)
        more = "more" if d["z"] > 0 else "less"
        out.append({"line": line, "col": 1, "severity": "advisory", "rule": "voice",
                    "rule_id": "voice." + d["feature"],
                    "match": quote[:160] or d["feature"],
                    "message": f"{d['feature']} {more} than the author by {abs(d['z']):.1f} sd ({d['value']} against "
                               f"{d['author_mean']} ± {d['author_sd']}, basis {res['basis']})"
                               + (f"; the author: {d['author_quote'][:80]!r}" if d.get("author_quote") else ""),
                    "engine": "fingerprint"})
    out.append({"line": 0, "col": 0, "severity": "advisory", "rule": "voice", "rule_id": "voice.distance",
                "match": f"Delta {res['delta']}, shape {res['shape_distance']}",
                "message": f"distance from the author's fingerprint: Delta {res['delta']} over function words, "
                           f"shape {res['shape_distance']} (mean |z| over the shape features); basis {res['basis']}",
                "engine": "fingerprint"})
    if res.get("discriminant"):
        d = res["discriminant"]
        side = "nearer the author" if d["score"] > 0 else "nearer the reference"
        out.append({"line": 0, "col": 0, "severity": "advisory", "rule": "voice", "rule_id": "voice.discriminant",
                    "match": f"{d['score']:+.2f} against {d['reference']}",
                    "message": f"{side}: {d['score']:+.2f} over {d['features_used']} separating features"
                               + (f"; for the author: {', '.join(d['for_author'])}" if d["for_author"] else "")
                               + (f"; for the reference: {', '.join(d['for_reference'])}" if d["for_reference"] else ""),
                    "engine": "fingerprint"})
    return out


def cmd_check(args) -> int:
    cfg, surface = load_layers(args.surface, args.config, args.surfaces)
    fp = ref = None
    if getattr(args, "fingerprint", None):
        try:
            with open(args.fingerprint, encoding="utf-8") as fh:
                fp = json.load(fh)
            if getattr(args, "reference", None):
                with open(args.reference, encoding="utf-8") as fh:
                    ref = json.load(fh)
        except (OSError, ValueError) as exc:
            sys.stderr.write(f"pherkad: fingerprint: {exc}\n")
            return 2
    overlay = args.config or (surface["overlay"] if surface else None)
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
        findings, dropped = run_text(text, cfg, structure=not args.no_structure, density=False)
        if decisions:
            apply_decisions(findings, text, rel_path(path, root), decisions, hashes)
        else:
            for f in findings:
                f["decision"] = None
        # Density over what counts: advisory and decided findings are set aside
        # by this gate's own configuration and must not feed a warning that blocks.
        counted = [f for f in findings if not f["decision"] and _level(f, advisory) != "advisory"
                   and f["rule"] != "frame"]  # a document-level frame finding is not a per-100-words construction
        d = density_finding(counted, text, cfg)
        if d:
            d["decision"] = None
            findings.append(d)
        if fp:
            for v in voice_findings(text, fp, surface["name"] if surface else None, args.fingerprint_threshold, ref):
                v["decision"] = None
                findings.append(v)
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
                          "speaker": surface["speaker"] if surface else "", "positive_register": surface["positive_register"] if surface else "",
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
        where = f"; surface {surface['name']} ({surface['speaker']}, register {surface['positive_register']})" if surface else ""
        print(f"pherkad: {errors} error(s), {warnings} warning(s){tail_s} across {len(results)} file(s){where}.")

    if io_failed:
        return 2
    return 1 if errors or (args.strict and warnings) else 0


# ---------------------------------------------------------------------------
# Release manifest and overlay check
# ---------------------------------------------------------------------------
MANIFEST = os.path.join(HERE, "bundle-manifest.json")
MANIFEST_SCHEMA = 1
# The five a gate needs are required wherever the bundle is vendored; the rest
# are listed so their hashes travel, but a vendored copy may leave them out.
REQUIRED_FILES = ("pherkad.py", "voicelint.py", "structlint.py", "mdmask.py", "voice_config.json")
BUNDLE_FILES = REQUIRED_FILES + ("replycheck.py", "replycheck-hook.py", "corpusscan.py", "corrections.py", "samples.py", "fingerprint.py")


def _file_sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def build_manifest() -> dict:
    import datetime
    files = {}
    for name in BUNDLE_FILES:
        p = os.path.join(HERE, name)
        if os.path.exists(p):
            files[name] = _file_sha(p)
    if os.path.isdir(SURFACES):
        for f in sorted(os.listdir(SURFACES)):
            if f.endswith(".json"):
                files["surfaces/" + f] = _file_sha(os.path.join(SURFACES, f))
    cfg = voicelint.load_config(voicelint.DEFAULTS_PATH)
    return {"tool": "pherkad", "version": _version(), "schema": MANIFEST_SCHEMA,
            "generated": datetime.date.today().isoformat(), "required": list(REQUIRED_FILES),
            "files": files, "rule_ids": sorted(r["id"] for r in all_rules(cfg))}


def verify_manifest(manifest_path: str = MANIFEST) -> list[str]:
    """Problems between the manifest and the files beside it; empty when clean."""
    if not os.path.exists(manifest_path):
        return [f"no manifest at {manifest_path}"]
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            m = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read manifest: {exc}"]
    problems = []
    here = os.path.dirname(os.path.abspath(manifest_path))
    if m.get("schema") != MANIFEST_SCHEMA:
        problems.append(f"manifest schema {m.get('schema')} is not {MANIFEST_SCHEMA}")
    version_file = os.path.join(here, "..", "VERSION")
    in_repo = os.path.exists(version_file)
    if in_repo and m.get("version") != _version():
        problems.append(f"manifest version {m.get('version')} is not VERSION {_version()}")
    required = set(m.get("required") or REQUIRED_FILES)
    for name, sha in (m.get("files") or {}).items():
        p = os.path.join(here, name)
        if not os.path.exists(p):
            if name in required or in_repo:
                problems.append(f"missing: {name}")
        elif _file_sha(p) != sha:
            problems.append(f"changed: {name}")
    if in_repo:
        current = build_manifest()
        for name in current["files"]:
            if name not in (m.get("files") or {}):
                problems.append(f"not in manifest: {name}")
        if current["rule_ids"] != m.get("rule_ids"):
            problems.append("rule ids differ from the shipped config")
    else:
        cfg = voicelint.load_config(voicelint.DEFAULTS_PATH)
        if sorted(r["id"] for r in all_rules(cfg)) != m.get("rule_ids"):
            problems.append("rule ids differ from the vendored config")
    return problems


def cmd_manifest(args) -> int:
    if args.write:
        m = build_manifest()
        with open(MANIFEST, "w", encoding="utf-8") as fh:
            json.dump(m, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(f"pherkad: wrote {MANIFEST} ({len(m['files'])} file(s), {len(m['rule_ids'])} rule id(s), version {m['version']})")
        return 0
    if args.verify:
        problems = verify_manifest()
        for p in problems:
            print(f"manifest: {p}")
        print(f"pherkad: manifest {'verified' if not problems else 'does not match: ' + str(len(problems)) + ' problem(s)'}")
        return 1 if problems else 0
    print(json.dumps(build_manifest(), indent=2, ensure_ascii=False))
    return 0


def check_overlay(overlay_path: str) -> tuple[list[str], list[str]]:
    """(errors, warnings) for a downstream overlay against the shipped base."""
    errors, warnings = [], []
    try:
        with open(overlay_path, encoding="utf-8") as fh:
            ov = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read overlay: {exc}"], []
    voicelint._validate(ov)  # exits 2 on a structural problem, as the linter would
    base = voicelint.load_config(voicelint.DEFAULTS_PATH)
    for field in voicelint._LIST_FIELDS:
        shipped = voicelint.rule_entries(base, field)
        ids = {e["id"] for e in shipped}
        pats = {e["pattern"] for e in shipped}
        for r in ov.get("remove_" + field, []):
            rid = r if isinstance(r, str) else r.get("id")
            pat = r if isinstance(r, str) else r.get("pattern")
            if rid not in ids and pat not in pats:
                errors.append(f"remove_{field}: {rid or pat!r} names no shipped rule; the removal does nothing")
        for a in ov.get("add_" + field, []):
            e = voicelint._norm_entry(field, a)
            if e["id"] in ids:
                warnings.append(f"add_{field}: {e['id']} is already a shipped rule; the addition is skipped")
            elif e["pattern"] in pats:
                warnings.append(f"add_{field}: {e['pattern']!r} is already shipped (as a different id); the addition is skipped")
        if field in ov and shipped:
            warnings.append(f"{field}: the overlay replaces the whole shipped list ({len(shipped)} rules) with {len(ov[field])}; "
                            f"use add_/remove_ to inherit")
    for k in (ov.get("structure") or {}):
        if not k.startswith("_") and k not in voicelint._STRUCTURE_KEYS:
            errors.append(f"structure.{k}: not a threshold this base knows")
    # The overlay's own fixtures: every rule object with examples is a tested
    # rule, and a promoted correction's tests live here.
    cfg = voicelint.load_config(overlay_path)
    for field in voicelint._LIST_FIELDS:
        for item in ov.get("add_" + field, []) + ov.get(field, []):
            if not isinstance(item, dict):
                continue
            e = voicelint._norm_entry(field, item)
            # Each rule is tested alone: under the full set a shipped rule can win
            # the same span on a tie and hide a fixture that does fire.
            solo = json.loads(json.dumps(cfg))
            for f_ in voicelint._LIST_FIELDS:
                solo[f_] = [x for x in cfg.get(f_, []) if voicelint._norm_entry(f_, x)["id"] == e["id"]]
            for text in e.get("fires", []):
                if e["id"] not in {f.rule_id for f in voicelint.check(text, solo)}:
                    errors.append(f"{e['id']}: fires example does not fire: {text!r}")
                    continue
                # Under the effective stack another rule can win the same span on
                # a tie, and then this rule never surfaces: say so.
                full = voicelint.check(text, cfg)
                if e["id"] not in {f.rule_id for f in full}:
                    winners = sorted({f.rule_id for f in full}) or ["nothing"]
                    warnings.append(f"{e['id']}: fires alone but under the full stack the finding is "
                                    f"{', '.join(winners)}: {text!r}")
            for text in e.get("clean", []):
                if e["id"] in {f.rule_id for f in voicelint.check(text, solo)}:
                    errors.append(f"{e['id']}: clean example fires: {text!r}")
    return errors, warnings


def cmd_check_overlay(args) -> int:
    errors, warnings = check_overlay(args.overlay)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    cfg = voicelint.load_config(args.overlay)
    n = len(all_rules(cfg))
    print(f"pherkad: overlay {args.overlay} on base {_version()}: {len(errors)} error(s), {len(warnings)} warning(s); "
          f"{n} rule(s) effective")
    return 1 if errors else 0


# ---------------------------------------------------------------------------
# Judgment packet (roadmap item 15)
# ---------------------------------------------------------------------------
# One command assembles everything a quick-mode judgment run needs, so the
# context is the same every time and any model or tool can run it without
# reading the skill: the surface (speaker, register, guidance, approved
# excerpts), the profile files, the mechanical findings with decisions applied,
# the judgment-only rules that apply to this surface, the instructions, the
# output schema, and a hash of every input.
PROFILE_FILES = ("Voice_Profile.md", "voice-rules.md", "voice-authoring.md")
OPTIONAL_PROFILE_FILES = ("Voice_Profile.measured.md",)  # the numbers view, fingerprint.py prose; carried when present

JUDGMENT_RULES = {
    "always": [
        "5c: the antithesis family ('not X but Y', 'X, not Y', 'less about X than Y') where it recurs; the repeated-frame check reports the mechanical part, read for it only under its threshold",
        "5f: triplet noun piling where the three are decoration rather than an enumeration",
        "5g: counter-X constructions ('counter-intuitive', 'contrary to popular belief')",
        "5h: authenticity language ('to be honest', 'I want to be clear', announced candour or directness)",
        "5i: structural artifacts (a paragraph that announces its own structure, a closing sentence that gestures at a theme, a demonstrative pointer 'that is the part that')",
        "the profile's companion files: any ban stated there that no regex expresses",
    ],
    "assistant": [
        "the chat-only rules: a markdown link where a full path belongs, a tilde path, question praise, a presenter-style narration of what the assistant will do",
    ],
    "register": {
        "no": [],
        "profile": ["positive register: one of the profile's markers where the profile shows it in this register; a status message needs none"],
        "frame": ["positive register in the frame and transitions only: the opening, the close, the joins; the core is held to accuracy"],
        "yes": ["positive register throughout: a draft clean of every tell with none of the profile's markers has flattened; say where one marker would go"],
        "own-voice-document": ["the project's own voice document governs; do not apply the personal profile's markers"],
    },
}

OUTPUT_SCHEMA = {
    "header": "QUICK VOICE CHECK (surface: <name>, <speaker>, register <register>; profile <loaded|missing>; <n> words)",
    "row": {"rule_ref": "a mechanical rule_id, or 'judgment (5c)' etc., or 'positive-register'",
            "quote": "the passage, verbatim, in backticks",
            "decision": "fix | intentional | literal | not applicable | quoted",
            "rationale": "one clause",
            "proposed_edit": "only when decision is fix; changes no fact, name, number, date, source, or emphasis"},
    "verdict": "PASS when no row is fix; REVISE when any is; REWRITE only when the positive-register row is fix and three or more other rows are",
}

_QUICK_FALLBACK = """Quick mode. One table, one verdict line. Nothing is scored and nothing is rewritten that was not flagged.
1. The mechanical findings are listed below with any decisions already applied; do not re-run them.
2. Read the draft once for the judgment-only rules listed for this surface, not the whole catalog. Add a row per supported hit.
3. Decide each row: fix (the tell is real here; the row carries a proposed edit), intentional (the writer's own move), literal (the plain sense), not applicable (the rule does not apply to this surface), quoted (someone else's words).
4. Read the positive register only where the surface expects it (stated below); where it does and the draft shows none of the profile's markers, add one positive-register row with decision fix.
5. Verdict: PASS when no row is fix; REVISE when any is; REWRITE only when the positive-register row is fix and three or more other rows are."""


def _quick_instructions() -> str:
    """The Quick mode section of SKILL.md when it is beside the tools (the
    repository); an embedded condensed version in a vendored copy."""
    skill = os.path.join(HERE, "..", "SKILL.md")
    try:
        text = open(skill, encoding="utf-8").read()
        m = re.search(r"^## Quick mode\n(.*?)^## Full mode", text, re.S | re.M)
        if m:
            body = m.group(1).strip()
            # The packet has already run the mechanical layer; the skill's step 1 says to run it.
            body = re.sub(r"^1\. \*\*Run the mechanical layer once\*\*.*?(?=\n2\. )",
                          "1. **The mechanical findings are already below**, with the author's decisions applied; do not run any tool.",
                          body, count=1, flags=re.S | re.M)
            return body
    except OSError:
        pass
    return _QUICK_FALLBACK


def _profile_dir(explicit: str | None) -> str | None:
    """An explicit directory is used as given, profile or not, so a missing
    profile is reported rather than papered over by a fallback. Otherwise:
    PHERKAD_PROFILE, the repository root (where the maintainer's live), then
    the working directory."""
    if explicit:
        return explicit
    for cand in (os.environ.get("PHERKAD_PROFILE"),
                 os.path.abspath(os.path.join(HERE, "..", "..", "..")), os.getcwd()):
        if cand and os.path.exists(os.path.join(cand, "Voice_Profile.md")):
            return cand
    return None


def build_pack(path: str, surface: str, config: str | None, decisions_path: str | None,
               root: str | None, profile_dir: str | None, surfaces_map: str | None,
               inline_profile: bool = True, structure: bool = True, measured: str | None = None) -> dict:
    cfg, info = load_layers(surface, config, surfaces_map)
    text = read_source(path)
    findings, suppressed = run_text(text, cfg, structure=structure, density=False)
    decisions = load_decisions(decisions_path)
    droot = root or (os.path.dirname(os.path.abspath(decisions_path)) if decisions_path else os.getcwd())
    if decisions:
        apply_decisions(findings, text, rel_path(path, droot), decisions, rule_hashes(cfg))
    else:
        for f in findings:
            f["decision"] = None
    live = [f for f in findings if not f["decision"]]
    d = density_finding(live, text, cfg)
    if d:
        d["decision"] = None
        findings.append(d)
    pdir = _profile_dir(profile_dir)
    profile = {"dir": pdir or "", "files": {}}
    for name in PROFILE_FILES + OPTIONAL_PROFILE_FILES:
        p = os.path.join(pdir, name) if pdir else ""
        if name in OPTIONAL_PROFILE_FILES and measured:
            p = measured  # the numbers view can live elsewhere (a private folder) and be named explicitly
        entry = {"path": p, "present": bool(p and os.path.exists(p))}
        if name in OPTIONAL_PROFILE_FILES and not entry["present"]:
            continue
        if entry["present"]:
            body = open(p, encoding="utf-8", errors="replace").read()
            entry["sha256"] = _hash(body)
            entry["words"] = len(re.findall(r"\w+", body))
            if inline_profile:
                entry["text"] = body
        profile["files"][name] = entry
    excerpts = []
    for e in (info["excerpts"] if info else []):
        item = dict(e)
        if e["exists"]:
            item["text"] = open(e["path"], encoding="utf-8", errors="replace").read()
        excerpts.append(item)
    ruled, _stale = judgment_records_for(decisions, rel_path(path, droot), text) if decisions else ([], [])
    speaker = info["speaker"] if info else "author"
    register = info["positive_register"] if info else "profile"
    rules = list(JUDGMENT_RULES["always"])
    if speaker == "assistant":
        rules += JUDGMENT_RULES["assistant"]
    rules += JUDGMENT_RULES["register"].get(register, [])
    import datetime
    return {
        "tool": "pherkad", "version": _version(), "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "depth": "quick",
        "surface": {"name": info["name"] if info else "", "speaker": speaker, "positive_register": register,
                    "guidance": info["guidance"] if info else "", "overlay": info["overlay"] if info else "",
                    "excerpts": excerpts},
        "project_overlay": config or "", "config_sha256": config_sha256(cfg),
        "profile": profile,
        "source": {"path": path, "sha256": _hash(text), "words": len(re.findall(r"\w+", text)), "text": text},
        "mechanical": {"findings": findings, "suppressed": suppressed,
                       "decided": sum(1 for f in findings if f["decision"]),
                       "decisions": decisions_path or ""},
        "already_ruled": [{"rule_id": d["rule_id"], "quote": d.get("quote", d.get("match", "")),
                           "disposition": d["disposition"], "reason": d["reason"]} for d in ruled],
        "judgment_rules": rules,
        "instructions": _quick_instructions(),
        "output_schema": OUTPUT_SCHEMA,
    }


def render_prompt(pack: dict) -> str:
    s = pack["surface"]
    parts = ["You are running Pherkad's quick voice check. Everything you need is below; do not run any tool.", "",
             f"SURFACE: {s['name'] or '(none)'}; speaker {s['speaker']}; positive register {s['positive_register']}.",
             f"GUIDANCE: {s['guidance']}" if s["guidance"] else "", ""]
    parts += ["=== INSTRUCTIONS ===", pack["instructions"], ""]
    parts += ["=== JUDGMENT-ONLY RULES FOR THIS SURFACE ===", *[f"- {r}" for r in pack["judgment_rules"]], ""]
    parts += ["=== OUTPUT ===", json.dumps(pack["output_schema"], indent=2, ensure_ascii=False), ""]
    for name, e in pack["profile"]["files"].items():
        if e.get("present") and e.get("text"):
            parts += [f"=== PROFILE: {name} ===", e["text"].strip(), ""]
    if not any(e.get("present") for e in pack["profile"]["files"].values()):
        parts += ["=== PROFILE ===", "(no Voice_Profile.md found; this is a profile-less scan and the report must say so)", ""]
    for ex in s["excerpts"]:
        if ex.get("text"):
            parts += [f"=== APPROVED EXCERPT: {os.path.basename(ex['path'])} ===", ex["text"].strip(), ""]
    parts += ["=== MECHANICAL FINDINGS (decisions applied; do not re-run) ==="]
    m = pack["mechanical"]
    live = [f for f in m["findings"] if not f["decision"]]
    if live:
        for f in live:
            parts.append(f"line {f['line']}: [{f['severity']}] {f['rule_id']}: {f['message']}  ->  {f['match']!r}")
    else:
        parts.append("(none)")
    if m["decided"]:
        parts.append(f"({m['decided']} finding(s) already decided by the author and hidden)")
    if pack.get("already_ruled"):
        parts += ["", "=== ALREADY RULED BY THE AUTHOR (do not raise these again) ==="]
        for d in pack["already_ruled"]:
            parts.append(f"{d['rule_id']}: `{d['quote'][:100]}`  ->  {d['disposition']}: {d['reason']}")
    parts += ["", f"=== DRAFT ({pack['source']['words']} words) ===", pack["source"]["text"].rstrip(), ""]
    return "\n".join(p for p in parts if p is not None)


def cmd_review_pack(args) -> int:
    pack = build_pack(args.file, args.surface, args.config, args.decisions, args.root, args.profile_dir,
                      args.surfaces, inline_profile=not args.no_profile_text, structure=not args.no_structure,
                      measured=args.measured)
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "pack.json"), "w", encoding="utf-8") as fh:
            json.dump(pack, fh, indent=2, ensure_ascii=False)
        with open(os.path.join(args.out, "prompt.md"), "w", encoding="utf-8") as fh:
            fh.write(render_prompt(pack))
        missing = [n for n, e in pack["profile"]["files"].items() if not e.get("present")]
        print(f"pherkad: wrote {args.out}/pack.json and prompt.md; surface {pack['surface']['name']}, "
              f"{len([f for f in pack['mechanical']['findings'] if not f['decision']])} live finding(s), "
              f"{len(pack['judgment_rules'])} judgment rule(s)"
              + (f"; profile files missing: {', '.join(missing)}" if missing else ""))
        return 0
    if args.format == "json":
        print(json.dumps(pack, indent=2, ensure_ascii=False))
    else:
        print(render_prompt(pack))
    return 0


# ---------------------------------------------------------------------------
# Persisting judgment findings (roadmap item 18)
# ---------------------------------------------------------------------------
# A quick-mode row the author rules on (intentional, literal, not applicable,
# quoted) is recorded in the same decision store as a mechanical finding. A
# mechanical row resolves to its finding by the quote; a judgment row becomes a
# `judgment.<family>` record keyed on the quote and the line it sits on. The
# next packet for that file lists what has been ruled so the model does not
# raise it again; `decisions` reports a judgment record stale when its quote
# is gone from the file.
_ROW_DISPOSITION = {"intentional": "intentional", "literal": "accepted", "not applicable": "accepted", "quoted": "accepted"}


def parse_review_table(text: str) -> list[dict]:
    """Rows of a quick-mode table (Markdown), or a JSON list of row objects."""
    text = text.strip()
    if text.startswith("["):
        return json.loads(text)
    rows = []
    for line in text.split("\n"):
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0].lower() in ("rule_ref", "rule") or set(cells[0]) <= {"-", ":"}:
            continue
        rows.append({"rule_ref": cells[0].strip("`"), "quote": cells[1].strip().strip("`\"'"),
                     "decision": cells[2].lower(), "rationale": cells[3] if len(cells) > 3 else "",
                     "proposed_edit": cells[4] if len(cells) > 4 else ""})
    return rows


def _judgment_id(ref: str) -> str:
    inner = re.sub(r"^judgment\s*\(?|\)?$", "", ref.strip(), flags=re.I).strip() or "general"
    return JUDGMENT_PREFIX + re.sub(r"[^a-z0-9.]+", "-", inner.lower()).strip("-")


def judgment_records_for(decisions: list[dict], path_rel: str, text: str) -> tuple[list[dict], list[dict]]:
    """(live, stale) judgment records for a file: live while the quote is still in the text."""
    live, stale = [], []
    for d in decisions:
        if d["path"] != path_rel or not d["rule_id"].startswith(JUDGMENT_PREFIX):
            continue
        q = " ".join((d.get("quote") or "").split())
        if q and q in " ".join(text.split()):
            live.append(d)
        else:
            stale.append(d)
    return live, stale


def cmd_review_import(args) -> int:
    """Record the ruled rows of a quick-mode table against the file they were about."""
    try:
        table = read_source(args.table)
        text = read_source(args.file)
    except OSError as exc:
        sys.stderr.write(f"pherkad: {exc}\n")
        return 2
    rows = parse_review_table(table)
    if not rows:
        sys.stderr.write("pherkad: no rows found in the table\n")
        return 2
    decisions = load_decisions(args.decisions)
    root = args.root or os.path.dirname(os.path.abspath(args.decisions))
    rel = rel_path(args.file, root)
    cfg, _s = load_layers(args.surface, args.config, args.surfaces)
    hashes = rule_hashes(cfg)
    findings, _ = run_text(text, cfg, density=False)
    import datetime
    today = datetime.date.today().isoformat()
    flat = " ".join(text.split())
    lines = text.split("\n")
    recorded = skipped = 0
    for r in rows:
        dec = r.get("decision", "").strip().lower()
        if dec not in _ROW_DISPOSITION:
            skipped += 1  # fix rows and anything else are not decisions
            continue
        quote = " ".join((r.get("quote") or "").split())
        reason = (r.get("rationale") or "").strip()
        if not quote or not reason:
            print(f"skipped (needs a quote and a rationale): {r.get('rule_ref')} {quote[:40]!r}")
            skipped += 1
            continue
        if quote not in flat:
            print(f"skipped (quote not found in {rel}): {quote[:60]!r}")
            skipped += 1
            continue
        line_no = next((i for i, ln in enumerate(lines, 1) if quote[:40] in " ".join(ln.split())), 0)
        ref = r.get("rule_ref", "").strip()
        if ref in hashes and not ref.startswith(JUDGMENT_PREFIX):
            at = [f for f in findings if f["rule_id"] == ref and f["line"] == line_no]
            if not at:
                at = [f for f in findings if f["rule_id"] == ref and quote[:20] in " ".join(lines[f["line"] - 1].split())]
            if not at:
                print(f"skipped (no {ref} finding at the quote): {quote[:60]!r}")
                skipped += 1
                continue
            f = at[0]
            ctx = _document_context(f) or context_hash(text, f["line"], _scope(f))
            n = sum(1 for g in findings if g["rule_id"] == ref and g["line"]
                    and (_document_context(g) or context_hash(text, g["line"], _scope(g))) == ctx)
            rec = {"rule_id": ref, "path": rel, "context_hash": ctx, "rule_hash": hashes[ref], "count": n,
                   "disposition": _ROW_DISPOSITION[dec], "reason": reason, "decided": today,
                   "line": f["line"], "match": f["match"],
                   "scope": "document" if _document_context(f) else ("paragraph" if _scope(f) else "line")}
        else:
            rid = ref if ref.startswith(JUDGMENT_PREFIX) else _judgment_id(ref)
            rec = {"rule_id": rid, "path": rel, "context_hash": _hash(" ".join(lines[line_no - 1].split())) if line_no else _hash(quote),
                   "rule_hash": JUDGMENT_HASH, "count": 1, "disposition": _ROW_DISPOSITION[dec], "reason": reason,
                   "decided": today, "line": line_no, "match": quote[:120], "quote": quote, "scope": "quote"}
        existing = next((d for d in decisions if d["path"] == rel and d["rule_id"] == rec["rule_id"]
                         and d["context_hash"] == rec["context_hash"]), None)
        if existing:
            existing.update(rec)
        else:
            decisions.append(rec)
        recorded += 1
        print(f"recorded {rec['disposition']}: {rel}:{rec['line']} {rec['rule_id']}  ->  {rec['match'][:70]!r}")
    save_decisions(args.decisions, decisions)
    print(f"pherkad: {recorded} row(s) recorded, {skipped} skipped, in {args.decisions}")
    return 0


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
    cfg, _surface = load_layers(args.surface, args.config, getattr(args, "surfaces", None))
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
        by_rule = {}
        for f in at:
            by_rule.setdefault(f["rule_id"], []).append(f)
        for rid, fs in by_rule.items():
            para = _scope(fs[0])
            ctx = _document_context(fs[0]) or context_hash(text, line, para)
            # The record is keyed on the text (the line, or the paragraph for a
            # structural finding, or the quoted units for a document-level one),
            # so it covers every place in the file with that text.
            n = sum(1 for f in findings if f["rule_id"] == rid and f["line"]
                    and (_document_context(f) or context_hash(text, f["line"], _scope(f))) == ctx)
            existing = next((d for d in decisions if d["path"] == rel and d["rule_id"] == rid
                             and d["context_hash"] == ctx), None)
            if existing:
                existing.update(count=n, rule_hash=hashes[rid], disposition=args.disposition,
                                reason=args.reason, decided=today, line=line, match=fs[0]["match"])
            else:
                decisions.append({"rule_id": rid, "path": rel, "context_hash": ctx, "rule_hash": hashes[rid],
                                  "count": n, "disposition": args.disposition, "reason": args.reason,
                                  "decided": today, "line": line, "match": fs[0]["match"],
                                  "scope": "document" if _document_context(fs[0]) else ("paragraph" if para else "line")})
            added += 1
            print(f"decided {args.disposition}: {rel}:{line} {rid} ({n} occurrence(s) of this line's text)  ->  {fs[0]['match']!r}")
    save_decisions(args.decisions, decisions)
    print(f"pherkad: {added} decision(s) written to {args.decisions}")
    return 0


def cmd_decisions(args) -> int:
    """Which decisions still match a finding, and which are stale (the line
    changed, the rule changed, the file is gone, or the finding no longer
    fires). --prune drops the stale ones; nothing is pruned otherwise."""
    cfg, _surface = load_layers(args.surface, args.config, getattr(args, "surfaces", None))
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
    texts = {}
    for path in args.files:
        try:
            texts[rel_path(path, root)] = read_source(path)
        except OSError:
            pass
    stale, kept, unchecked = [], [], []
    for d in decisions:
        if id(d) in live:
            kept.append(d)
        elif d["path"] not in checked:
            unchecked.append(d)
        elif d["rule_id"].startswith(JUDGMENT_PREFIX):
            lv, _st = judgment_records_for([d], d["path"], texts.get(d["path"], ""))
            if lv:
                kept.append(d)
            else:
                stale.append((d, "quote gone"))
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


def cmd_surfaces(args) -> int:
    """Every surface a name could resolve to, with speaker, register, overlay, and excerpts."""
    user_map, map_file = load_surface_map(args.surfaces)
    names = sorted(set(shipped_surfaces()) | set(user_map))
    rows = [resolve_surface(n, args.surfaces) for n in names]
    if args.json:
        print(json.dumps({"map": map_file or "", "surfaces": rows}, indent=2, ensure_ascii=False))
        return 0
    w = max(len(r["name"]) for r in rows) if rows else 8
    print(f"{'surface':<{w}}  {'speaker':<9} {'register':<18} {'from':<8} excerpts  overlay")
    for r in rows:
        ex = f"{sum(e['exists'] for e in r['excerpts'])}/{len(r['excerpts'])}" if r["excerpts"] else "-"
        print(f"{r['name']:<{w}}  {r['speaker']:<9} {r['positive_register']:<18} {'map' if r['from_map'] else 'shipped':<8} {ex:<8}  {r['overlay'] or '-'}")
        if r["guidance"]:
            print(f"{'':<{w}}    {r['guidance']}")
        for e in r["excerpts"]:
            print(f"{'':<{w}}    excerpt: {e['path']}" + ("" if e["exists"] else "  (missing)"))
    if map_file:
        print(f"pherkad: {len(rows)} surface(s); user map {map_file}")
    else:
        print(f"pherkad: {len(rows)} surface(s); no user map (surfaces.json, --surfaces, or PHERKAD_SURFACES)")
    return 0


def cmd_rules(args) -> int:
    cfg, _surface = load_layers(args.surface, args.config, getattr(args, "surfaces", None))
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
    pc.add_argument("--surface", help="what the text is: a shipped surface, one from the user map, or a path")
    pc.add_argument("--surfaces", help="the user surface map (default: ./surfaces.json or PHERKAD_SURFACES)")
    pc.add_argument("--config", help="a project overlay, applied after the surface's")
    pc.add_argument("--format", choices=["text", "json", "sarif"], default="text")
    pc.add_argument("--strict", action="store_true", help="warnings fail too")
    pc.add_argument("--fingerprint", metavar="FILE", help="the measured profile (fingerprint.py build); adds advisory voice.* findings")
    pc.add_argument("--fingerprint-threshold", type=float, default=2.0, help="standard deviations before a feature is reported")
    pc.add_argument("--reference", metavar="FILE", help="a fingerprint.py build-reference profile; adds the voice.discriminant finding")
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
    pd.add_argument("--surfaces")
    pd.add_argument("--config")
    pd.add_argument("--root")
    pd.add_argument("--no-structure", action="store_true")
    pd.set_defaults(fn=cmd_decide)
    pdd = sub.add_parser("decisions", help="which decisions still match; --prune drops the stale ones")
    pdd.add_argument("files", nargs="+")
    pdd.add_argument("--decisions", required=True)
    pdd.add_argument("--prune", action="store_true")
    pdd.add_argument("--surface")
    pdd.add_argument("--surfaces")
    pdd.add_argument("--config")
    pdd.add_argument("--root")
    pdd.add_argument("--no-structure", action="store_true")
    pdd.set_defaults(fn=cmd_decisions)
    pm = sub.add_parser("manifest", help="the release manifest: print, --write at release, --verify in CI and downstream")
    pm.add_argument("--write", action="store_true")
    pm.add_argument("--verify", action="store_true")
    pm.set_defaults(fn=cmd_manifest)
    po = sub.add_parser("check-overlay", help="does a downstream overlay still fit this base?")
    po.add_argument("overlay")
    po.set_defaults(fn=cmd_check_overlay)
    prp = sub.add_parser("review-pack", help="assemble the quick-mode judgment packet for one draft")
    prp.add_argument("file", help="the draft, or - for stdin")
    prp.add_argument("--surface", required=True, help="what the draft is; required, never inferred")
    prp.add_argument("--surfaces")
    prp.add_argument("--config", help="a project overlay, applied after the surface's")
    prp.add_argument("--decisions")
    prp.add_argument("--root")
    prp.add_argument("--profile-dir", help="where Voice_Profile.md and its companions live (default: PHERKAD_PROFILE, the repo root, or the working directory)")
    prp.add_argument("--measured", metavar="FILE", help="the measured profile view (fingerprint.py prose --out), carried in the packet as Voice_Profile.measured.md")
    prp.add_argument("--no-profile-text", action="store_true", help="reference the profile files by path and hash only")
    prp.add_argument("--no-structure", action="store_true")
    prp.add_argument("--format", choices=["prompt", "json"], default="prompt")
    prp.add_argument("--out", help="write pack.json and prompt.md into this directory instead of printing")
    prp.set_defaults(fn=cmd_review_pack)
    pri = sub.add_parser("review-import", help="record the ruled rows of a quick-mode table as decisions")
    pri.add_argument("table", help="the table: a Markdown file with the quick-mode rows, or a JSON list, or - for stdin")
    pri.add_argument("--file", required=True, help="the draft the table was about")
    pri.add_argument("--decisions", required=True)
    pri.add_argument("--root")
    pri.add_argument("--surface")
    pri.add_argument("--surfaces")
    pri.add_argument("--config")
    pri.set_defaults(fn=cmd_review_import)
    psf = sub.add_parser("surfaces", help="every surface a name could resolve to")
    psf.add_argument("--surfaces")
    psf.add_argument("--json", action="store_true")
    psf.set_defaults(fn=cmd_surfaces)
    pr = sub.add_parser("rules", help="list every rule both engines would run")
    pr.add_argument("--surface")
    pr.add_argument("--surfaces")
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
