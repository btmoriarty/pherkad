#!/usr/bin/env python3
"""The detection experiment (roadmap item 13): does the judgment layer tell a
writer's prose from flattened prose and from an impostor's, and does it do so
because of the profile? Implements the protocol in docs/blind-eval.md as far
as one operator can run it; study.py dispatches here for --task detect.

Cases, per writer, read from the writer's data directory:
    holdout/*.md              authentic held-out pieces the profile never saw;
                              a file named atypical-*.md is the atypical case
    flattened/<holdout>.<k>.md  flattenings of a held-out piece, k = 1, 2, ...
                              (facts kept, framing and rhythm neutralised)
    impostors/*.md            other writers' pieces matched on register and topic
    override/*.md             authentic pieces that use an allowed habit

Conditions: correct (the writer's profile), wrong (another writer's), shuffled
(the writer's profile with its lines scrambled, written by plan), none (no
profile), linter (no judgment at all: the mechanical verdict the harness
computes itself, the floor). Every case runs under every condition, --repeats
times, each as its own blind item.

Verdicts: for every item except the linter floor, the judging model returns a
JSON block saved to verdicts/<blind_id>.json:
    {"rating": 1-5, "verdict": "PASS|light REVISE|REVISE|REWRITE",
     "positive_register": true|false, "markers": ["..."], "evidence": ["..."]}
The linter floor's verdict is written by prompts from pherkad.py check.

Reference: sheet writes a pairwise sheet (each held-out piece against each of
its flattenings, blind order); the reader marks which sounds more like the
writer in pairs.csv. A pair the reader cannot tell apart is excluded from the
model's scoring, per the protocol. sheet also writes findings-labels.csv,
every mechanical finding on authentic text for the reader to mark true or
false, which is what per-rule precision is computed from.

Score reports, per writer and pooled: the paired discrimination margin
(authentic minus flattened; authentic minus impostor) under each condition;
correct-profile lift (the correct margin minus the mean of wrong, shuffled,
and none, with linter-only as the floor); acceptance and rejection rates by
case type against the pass bar; verdict stability across repeats (exact,
adjacent, severe); explanation stability (Jaccard of markers cited); reader
accuracy on the pairs; and per-rule linter precision with false flags per
1,000 words of authentic text. It warns when prereg.md still has TODOs.

Stdlib only.
"""
from __future__ import annotations
import csv
import json
import os
import random
import re
import sys

import study

CONDITIONS = ("correct", "wrong", "shuffled", "none", "linter", "fingerprint")
CASE_DIRS = {"holdout": "authentic", "flattened": "flattened", "impostors": "impostor", "override": "override"}
VERDICTS = ("PASS", "light REVISE", "REVISE", "REWRITE")
VERDICT_SCORE = {"PASS": 4, "light REVISE": 3, "REVISE": 2, "REWRITE": 1}

PREREG = """# Preregistration: run {run}

Fill every TODO before a single verdict is collected. score warns while any remains.

- Estimand: the average correct-profile lift, the paired discrimination margin (authentic minus
  flattened, authentic minus impostor) under the correct profile minus the same margin under the
  pooled controls (wrong, shuffled, none), across writers.
- Analysis unit: the writer.
- Primary outcome: the paired rating margin. Verdict scores are secondary (PASS 4, light REVISE 3,
  REVISE 2, REWRITE 1).
- Judging model and settings: TODO (exact model, temperature, sampling), frozen for the run.
- Repeats per item: {repeats}.
- Light REVISE: a REVISE driven by minor surface hits, with the positive register present.
- Lift threshold that counts as success: TODO
- Flattened-pass rate above which the positive-register read is judged unreliable: TODO
- Verdict swing (severe movement rate) above which the judgment is judged unstable: TODO
- Smallest lift worth detecting, and the writer count that would power it: TODO
- Roles: profile builder TODO; flattening author TODO; judge TODO; operator TODO.
"""


def _cases(writer: str) -> list[dict]:
    """Every labelled case a writer's directory holds."""
    base = os.path.join(study.WRITERS, writer)
    cases = []
    for d, ctype in CASE_DIRS.items():
        p = os.path.join(base, d)
        if not os.path.isdir(p):
            continue
        for f in sorted(os.listdir(p)):
            if f.startswith(".") or not f.endswith(".md"):
                continue
            case = {"type": ctype, "file": os.path.join("writers", writer, d, f), "name": f[:-3]}
            if ctype == "authentic" and f.startswith("atypical-"):
                case["type"] = "atypical"
            if ctype == "flattened":
                m = re.match(r"^(.*)\.(\d+)\.md$", f)
                case["source"] = m.group(1) if m else f[:-3]
                case["k"] = int(m.group(2)) if m else 1
            cases.append(case)
    return cases


def _shuffled_profile(text: str, seed: int) -> str:
    lines = [ln for ln in text.split("\n") if ln.strip()]
    rng = random.Random(seed)
    rng.shuffle(lines)
    # the same heading as a real profile: a label naming it a control told the judge which arm it was in (I161)
    return "# Voice profile\n\n" + "\n".join(lines) + "\n"


def _used_profile_sha(cond, target, wrong, run_dir):
    """The hash of the profile the judge actually reads under this condition (I162):
    the target's, the other writer's, the shuffled file, or none."""
    if cond == "correct":
        return study._profile_sha(target)
    if cond == "wrong":
        return study._profile_sha(wrong) if wrong else ""
    if cond == "shuffled":
        p = os.path.join(run_dir, "profiles", f"{target}-shuffled.md")
        return study._sha(study._read(p)) if os.path.exists(p) else ""
    return ""


def plan(args, run_dir, writers, rng):
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    for c in conditions:
        if c not in CONDITIONS:
            sys.exit(f"unknown condition '{c}'; conditions are {', '.join(CONDITIONS)}")
    if "correct" not in conditions:
        sys.exit("the detection task needs the 'correct' condition; lift is measured from it")
    study._ensure(os.path.join(run_dir, "verdicts"), os.path.join(run_dir, "profiles"))
    items, missing = [], []
    for target in writers:
        base = os.path.join(study.WRITERS, target)
        for d in CASE_DIRS:
            study._ensure(os.path.join(base, d))
        cases = _cases(target)
        have = {c["type"] for c in cases}
        for need in ("authentic", "flattened", "impostor"):
            if need not in have:
                missing.append(f"{target}: no {need} case (add files under writers/{target}/"
                               f"{[k for k, v in CASE_DIRS.items() if v == need][0]}/)")
        prof = os.path.join(base, "profile.md")
        if "shuffled" in conditions and os.path.exists(prof):
            study._write(os.path.join(run_dir, "profiles", f"{target}-shuffled.md"),
                         _shuffled_profile(study._read(prof), args.seed))
        others = [w for w in writers if w != target] or [w for w in study._all_writers() if w != target]
        wrong = rng.choice(others) if others else None
        for case in cases:
            for cond in conditions:
                if cond == "wrong" and not wrong:
                    continue
                for rep in range(1, args.repeats + 1):
                    bid = study._blind_id(args.run, target, "detect", case["file"], cond, str(rep))
                    items.append({
                        "blind_id": bid, "target": target, "task": "detect", "condition": cond, "repeat": rep,
                        "case_type": case["type"], "case": case["name"], "text": case["file"],
                        "source": case.get("source", ""), "k": case.get("k", 0),
                        "profile": {"correct": target, "wrong": wrong, "shuffled": f"{target}-shuffled",
                                    "none": None, "linter": None, "fingerprint": None}[cond],
                        "verdict": f"verdicts/{bid}.json", "surface": args.surface,
                        "tool_version": study._tool_version(), "config_sha256": study._config_sha(args.surface),
                        "profile_sha256": _used_profile_sha(cond, target, wrong, run_dir), "model": "",
                    })
    manifest = {"run": args.run, "task": "detect", "writers": writers, "conditions": conditions,
                "repeats": args.repeats, "surface": args.surface, "seed": args.seed, "items": items}
    with open(os.path.join(run_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    study._write(os.path.join(run_dir, "prereg.md"), PREREG.format(run=args.run, repeats=args.repeats))
    for m in missing:
        print("missing: " + m)
    print(f"planned detection run '{args.run}': {len(items)} items ({len(writers)} writer(s), "
          f"{len(conditions)} condition(s), {args.repeats} repeat(s)).")
    print(f"fill {run_dir}/prereg.md before collecting a verdict; then study.py prompts {args.run} --model <judge>")


JUDGE_PROMPT = (
    "Validate the passage below against the voice profile: does it sound like this writer? "
    "Use Pherkad's full validation (references/ai_tells.md, the seven dimensions, the positive "
    "register), then return ONLY a JSON object with these fields:\n"
    '  {"rating": <1 to 5, 5 unmistakably this writer, 1 clearly not>,\n'
    '   "verdict": "PASS" | "light REVISE" | "REVISE" | "REWRITE",\n'
    '   "positive_register": true | false,\n'
    '   "markers": [<the profile markers you found, by name>],\n'
    '   "evidence": [<one quoted phrase per cited marker or tell>]}\n'
    "A light REVISE is a REVISE driven by minor surface hits with the positive register present. "
    "The rating and the verdict must agree: PASS means a rating of 3 or higher, REWRITE a rating of 2 or lower. "
    "Every verdict cites at least one quoted phrase in evidence; a PASS quotes what sounds like the writer, "
    "a failing verdict quotes what does not. "
    "Do not rewrite anything. Do not guess who wrote it.")


def _linter_verdict(text: str, surface: str) -> dict:
    """The floor: a verdict from the mechanical findings alone, no reading."""
    sys.path.insert(0, study.TOOLS)
    import pherkad  # noqa: WPS433
    cfg, _ = pherkad.load_layers(surface, None)
    findings, _ = pherkad.run_text(text, cfg)
    errors = sum(f["severity"] == "error" for f in findings)
    warnings = sum(f["severity"] == "warning" for f in findings)
    density = any(f["rule"] == "density" for f in findings)
    if errors or density:
        rating, verdict = 2, "REVISE"
    elif warnings >= 3:
        rating, verdict = 3, "light REVISE"
    else:
        rating, verdict = 4, "PASS"
    return {"rating": rating, "verdict": verdict, "positive_register": None,
            "markers": [], "evidence": [f["rule_id"] for f in findings], "linter_only": True,
            "errors": errors, "warnings": warnings}


def _fingerprint_verdict(text: str, surface: str, fp: dict, ref: dict) -> dict:
    """The measured floor: a verdict from the fingerprint discriminant alone, no
    model. The mapping is the pilot's, fixed before the run: a score above
    +0.15 is PASS (5 above +0.40), 0 to +0.15 light REVISE, -0.15 to 0 REVISE,
    below that REWRITE."""
    sys.path.insert(0, study.TOOLS)
    import fingerprint  # noqa: WPS433
    res = fingerprint.compare(text, fp, surface, 2.0, ref)
    d = res.get("discriminant") or {"score": 0.0, "features_used": 0, "for_author": [], "for_reference": []}
    sc = d["score"]
    if sc >= 0.40:
        rating, verdict = 5, "PASS"
    elif sc >= 0.15:
        rating, verdict = 4, "PASS"
    elif sc >= 0.0:
        rating, verdict = 3, "light REVISE"
    elif sc >= -0.15:
        rating, verdict = 2, "REVISE"
    else:
        rating, verdict = 1, "REWRITE"
    return {"rating": rating, "verdict": verdict, "positive_register": None, "markers": d["for_author"],
            "evidence": d["for_reference"], "fingerprint_only": True, "score": sc,
            "features_used": d["features_used"], "basis": res.get("basis", "")}


def prompts(args, run_dir, manifest):
    problem = prereg_problem(run_dir, manifest)
    if problem:
        sys.exit(f"prompts: {problem}. Nothing is written, floor verdicts included, before the plan is frozen (I163).")
    n = floor = 0
    fp = ref = None
    if any(it["condition"] == "fingerprint" for it in manifest["items"]):
        if not (getattr(args, "fingerprint", None) and getattr(args, "reference", None)):
            sys.exit("the fingerprint condition needs --fingerprint F and --reference R (fingerprint.py build / build-reference)")
        fp = json.load(open(args.fingerprint))
        ref = json.load(open(args.reference))
    for it in manifest["items"]:
        text = study._read(os.path.join(study.DATA, it["text"])).strip()
        if it["condition"] == "linter":
            study._write(os.path.join(run_dir, it["verdict"]), json.dumps(_linter_verdict(text, it["surface"]), indent=2))
            it["model"] = "none (linter floor)"
            floor += 1
            continue
        if it["condition"] == "fingerprint":
            study._write(os.path.join(run_dir, it["verdict"]), json.dumps(_fingerprint_verdict(text, it["surface"], fp, ref), indent=2))
            it["model"] = "none (fingerprint floor)"
            it["fingerprint_sha256"] = study._sha(study._read(args.fingerprint))  # the whole file, not one field (I162)
            it["reference_sha256"] = study._sha(study._read(args.reference))
            floor += 1
            continue
        if it["profile"] is None:
            profile_txt = "(NO PROFILE: judge whether this reads as a distinct, specific writer at all.)"
        elif it["condition"] == "shuffled":
            profile_txt = study._read(os.path.join(run_dir, "profiles", it["profile"] + ".md"))
        else:
            profile_txt = study._read(os.path.join(study.WRITERS, it["profile"], "profile.md"))
        prompt = (f"{JUDGE_PROMPT}\n\nSurface: {it['surface']} (judge the positive register as that surface expects it).\n\n"
                  f"=== VOICE PROFILE ===\n{profile_txt}\n\n=== PASSAGE ===\n{text}\n")
        study._write(os.path.join(run_dir, "prompts", it["blind_id"] + ".txt"), prompt)
        it["prompt_sha256"] = study._sha(prompt)
        if args.model:
            it["model"] = args.model
        n += 1
    with open(os.path.join(run_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    print(f"wrote {n} judging prompts to {run_dir}/prompts/ and {floor} floor verdicts (linter, fingerprint) to {run_dir}/verdicts/")
    print("run every prompt with the SAME judging model and settings named in prereg.md; save each\n"
          f"JSON reply to {run_dir}/verdicts/<blind_id>.json, then: study.py sheet {args.run}")


def _filled(path, col):
    """Rows of a reader's CSV that already carry an answer in `col`."""
    if not os.path.exists(path):
        return []
    return [r for r in csv.DictReader(open(path, newline="")) if (r.get(col) or "").strip()]


def _guard_filled(paths_cols, force):
    """Never blank a reader's answers by regenerating a sheet (I147)."""
    import datetime
    import shutil
    filled = [(p, len(_filled(p, c))) for p, c in paths_cols if _filled(p, c)]
    if filled and not force:
        sys.exit("sheet: " + "; ".join(f"{os.path.basename(p)} already holds {n} answer(s)" for p, n in filled)
                 + ". Regenerating would blank them. --force keeps a timestamped copy first.")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    for p, _n in filled:
        shutil.copy2(p, f"{p}.{stamp}.bak")


def sheet(args, run_dir, manifest):
    """The reader's blind sheets: pairwise authentic-versus-flattened, and the
    mechanical findings on authentic text to label true or false.

    One sheet per flattening round (pairs-sheet-1.md, -2.md, ...), each holding
    at most one pair per source: on a single sheet the authentic text repeated
    across its k pairs, so the passage that appeared twice was the writer's
    (I156). Pair order and A/B placement come from the system's random source,
    not the manifest seed, so the key cannot be rebuilt from the plan (I027)."""
    import secrets
    sysrng = secrets.SystemRandom()
    _guard_filled([(os.path.join(run_dir, "pairs.csv"), "pick"),
                   (os.path.join(run_dir, "findings-labels.csv"), "label")], getattr(args, "force", False))
    by_writer = {}
    for it in manifest["items"]:
        if it["condition"] == "correct" and it["repeat"] == 1:
            by_writer.setdefault(it["target"], {}).setdefault(it["case_type"], []).append(it)
    rounds = {}
    for w in sorted(by_writer):
        auth = {it["case"]: it for it in by_writer[w].get("authentic", []) + by_writer[w].get("atypical", [])}
        for fl in by_writer[w].get("flattened", []):
            src = auth.get(fl["source"])
            if src:
                rounds.setdefault(int(fl["k"]), []).append((w, src, fl))
    rows, keyd, names = [], {}, []
    for k in sorted(rounds):
        pairs = rounds[k]
        sysrng.shuffle(pairs)
        lines = [f"# Pairwise reference sheet {k} of {len(rounds)}: run {manifest['run']}", "",
                 "For each pair, read both and mark in pairs.csv which sounds more like the named writer",
                 "(A or B), or 'same' if you cannot tell. Do NOT open manifest.json or pairs-key.json first.",
                 "A pair marked 'same' is left out of the model's scoring, and so is a pair where you hear the",
                 "flattening as the writer. Read the sheets on different days if you can.", ""]
        for w, src, fl in pairs:
            a_text = study._read(os.path.join(study.DATA, src["text"])).strip()
            b_text = study._read(os.path.join(study.DATA, fl["text"])).strip()
            flip = sysrng.random() < 0.5
            first, second = (b_text, a_text) if flip else (a_text, b_text)
            pid = study._blind_id()
            lines += [f"## {w} / pair {pid}", "", "### A", "", first, "", "### B", "", second, ""]
            rows.append({"pair_id": pid, "sheet": k, "writer": w, "pick": ""})
            keyd[pid] = {"authentic_is": "B" if flip else "A", "writer": w, "source": src["case"], "k": k}
        name = f"pairs-sheet-{k}.md"
        study._write(os.path.join(run_dir, name), "\n".join(lines))
        names.append(name)
    stale = os.path.join(run_dir, "pairs-sheet.md")
    if os.path.exists(stale):
        os.remove(stale)  # the old single sheet repeated each authentic text
    study.statefile.write_text(os.path.join(run_dir, "pairs.csv"),
                               "pair_id,sheet,writer,pick\n" + "".join(f"{r['pair_id']},{r['sheet']},{r['writer']},\n" for r in rows))
    study.statefile.write_json(os.path.join(run_dir, "pairs-key.json"), keyd, sort_keys=True)

    # mechanical findings on authentic text, for per-rule precision
    import pherkad  # noqa: WPS433
    cfg, _ = pherkad.load_layers(manifest["surface"], None)
    frows = []
    words = 0
    for w in sorted(by_writer):
        for it in by_writer[w].get("authentic", []) + by_writer[w].get("atypical", []) + by_writer[w].get("override", []):
            text = study._read(os.path.join(study.DATA, it["text"]))
            words += len(re.findall(r"\w+", text))
            findings, _ = pherkad.run_text(text, cfg)
            for f in findings:
                if not f["line"]:
                    continue
                ctx = text.split("\n")[f["line"] - 1].strip()
                frows.append({"writer": w, "case": it["case"], "line": f["line"], "rule_id": f["rule_id"],
                              "match": f["match"], "context": ctx[:200], "label": ""})
    with open(os.path.join(run_dir, "findings-labels.csv"), "w", newline="") as fh:
        wtr = csv.DictWriter(fh, fieldnames=["writer", "case", "line", "rule_id", "match", "context", "label"])
        wtr.writeheader()
        wtr.writerows(frows)
    study._write(os.path.join(run_dir, "authentic-words.txt"), str(words))
    print(f"wrote {', '.join(names) or 'no pair sheet'} ({len(rows)} pair(s)) and pairs.csv; mark A, B, or same.")
    print(f"wrote {run_dir}/findings-labels.csv ({len(frows)} mechanical finding(s) on {words:,} authentic words); "
          "mark each label TP (a real tell) or FP (the writer's own usage).")
    print(f"then: study.py score {manifest['run']}")


def prereg_problem(run_dir, manifest):
    """Why this run may not collect or score verdicts yet, or '' (I163). A run
    with a prereg.md must have it complete and frozen, and unchanged since."""
    p = os.path.join(run_dir, "prereg.md")
    if not os.path.exists(p):
        return ""
    text = study._read(p)
    if "TODO" in text:
        return "prereg.md still has TODO fields"
    frozen = manifest.get("prereg_sha256")
    if not frozen:
        return f"prereg.md is not frozen; run: study.py freeze {manifest['run']}"
    if study._sha(text) != frozen:
        return "prereg.md changed after it was frozen; the analysis plan must not move once verdicts exist"
    return ""


def freeze(args, run_dir, manifest):
    """Record prereg.md's hash and the time in the manifest; nothing is collected before this."""
    import datetime
    p = os.path.join(run_dir, "prereg.md")
    if not os.path.exists(p):
        sys.exit(f"no prereg.md in {run_dir}; nothing to freeze")
    text = study._read(p)
    if "TODO" in text:
        sys.exit("prereg.md still has TODO fields; fill every one before freezing")
    if manifest.get("prereg_sha256") and manifest["prereg_sha256"] != study._sha(text) and not args.force:
        sys.exit("this run was frozen with a different prereg.md; an analysis plan does not change after the fact "
                 "(--force records the change, and results.md will say so)")
    if manifest.get("prereg_sha256") and manifest["prereg_sha256"] != study._sha(text):
        manifest.setdefault("prereg_history", []).append({"sha256": manifest["prereg_sha256"], "frozen": manifest.get("prereg_frozen", "")})
    manifest["prereg_sha256"] = study._sha(text)
    manifest["prereg_frozen"] = datetime.datetime.now().isoformat(timespec="seconds")
    study.statefile.write_json(os.path.join(run_dir, "manifest.json"), manifest, sort_keys=True)
    print(f"froze prereg.md for run '{manifest['run']}' ({manifest['prereg_sha256'][:12]})")


JUDGED = ("correct", "wrong", "shuffled", "none")


def _load_verdicts(run_dir, manifest):
    """Verdicts that pass the CURRENT validator (I022): a verdict collected
    under an older, looser check is dropped and counted, not scored."""
    out, dropped = {}, {}
    for it in manifest["items"]:
        p = os.path.join(run_dir, it["verdict"])
        if not os.path.exists(p):
            continue
        raw = study._read(p)
        if it["condition"] in JUDGED:
            ok, why = study._validate_reply("detect", raw)
            if not ok:
                dropped.setdefault(it["condition"], []).append(why)
                continue
        try:
            m = re.search(r"\{.*\}", raw, re.S)
            v = json.loads(m.group(0) if m else raw)
        except (json.JSONDecodeError, AttributeError):
            dropped.setdefault(it["condition"], []).append("unreadable")
            continue
        if v.get("verdict") not in VERDICTS or not isinstance(v.get("rating"), (int, float)):
            dropped.setdefault(it["condition"], []).append("missing a valid rating or verdict")
            continue
        out[it["blind_id"]] = v
    return out, dropped


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _fmt(x, plus=False):
    if x is None:
        return "n/a"
    return f"{x:+.2f}" if plus else f"{x:.2f}"


def _boot(diffs, seed, n=2000):
    """A 95 percent percentile interval for the mean of paired differences."""
    if len(diffs) < 2:
        return None
    rng = random.Random(seed)
    means = sorted(_mean([rng.choice(diffs) for _ in diffs]) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def _pairs_key(run_dir, manifest):
    """pair_id -> {authentic_is, writer, source, k}; an older key held only the letter."""
    p = os.path.join(run_dir, "pairs-key.json")
    if not os.path.exists(p):
        return {}
    raw = json.loads(study._read(p))
    out = {}
    for pid, v in raw.items():
        out[pid] = v if isinstance(v, dict) else {"authentic_is": v}
    return out


def score(run_dir, manifest, exploratory=False):
    key = {it["blind_id"]: it for it in manifest["items"]}
    problem = prereg_problem(run_dir, manifest)
    if problem and not exploratory:
        sys.exit(f"score: {problem}. Score it anyway with --exploratory; results.md will say the numbers are exploratory.")
    verdicts, dropped = _load_verdicts(run_dir, manifest)
    lines = [f"# Results: run {manifest['run']} (detection task)", ""]
    if problem:
        lines += [f"**EXPLORATORY: {problem}. These numbers are not confirmatory.**", ""]
    if manifest.get("prereg_history"):
        lines += [f"**prereg.md was changed after it was first frozen ({len(manifest['prereg_history'])} time(s)).**", ""]
    # provenance: what these numbers were computed from (I162)
    lines += ["Inputs: manifest " + study._sha(json.dumps(manifest, sort_keys=True))[:12]
              + ", prereg " + (manifest.get("prereg_sha256", "") or "none")[:12]
              + f", {len(verdicts)} scored verdict(s) of {len(manifest['items'])} planned item(s).", ""]
    if not verdicts:
        lines.append("No verdicts found under verdicts/. Run the prompts first.")
        study._write(os.path.join(run_dir, "results.md"), "\n".join(lines))
        print("\n".join(lines))
        return

    # planned versus scored, per condition and case type (I022)
    planned, scored = {}, {}
    for it in manifest["items"]:
        k = (it["condition"], it["case_type"])
        planned[k] = planned.get(k, 0) + 1
        if it["blind_id"] in verdicts:
            scored[k] = scored.get(k, 0) + 1
    ctypes = sorted({ct for _, ct in planned})
    lines += ["| condition | " + " | ".join(ctypes) + " | dropped by the validator |",
              "|---|" + "---|" * len(ctypes) + "---|"]
    for cond in manifest["conditions"]:
        cells = [f"{scored.get((cond, ct), 0)}/{planned.get((cond, ct), 0)}" for ct in ctypes]
        lines.append(f"| {cond} | " + " | ".join(cells) + f" | {len(dropped.get(cond, []))} |")
    lines.append("")

    # the reader's reference: a pair's direction comes from the reader's pick (I164)
    keyd = _pairs_key(run_dir, manifest)
    excluded, contrary, decided = set(), set(), {}
    pairs_csv = os.path.join(run_dir, "pairs.csv")
    if os.path.exists(pairs_csv) and keyd:
        for row in csv.DictReader(open(pairs_csv, newline="")):
            pick = (row.get("pick") or "").strip().upper()
            if not pick:
                continue
            if pick not in ("A", "B", "SAME"):
                sys.exit(f"score: pair {row.get('pair_id')} has pick {row.get('pick')!r}; only A, B, or same are read (I166)")
            pid = row["pair_id"].strip()
            if pick == "SAME":
                excluded.add(pid)
            elif pick != keyd.get(pid, {}).get("authentic_is"):
                contrary.add(pid)  # the reader heard the flattening as the writer: the model is not scored against it
            decided[pid] = pick

    def pid_for(w, src, k):
        for pid, v in keyd.items():
            if v.get("writer") == w and v.get("source") == src and int(v.get("k", 0)) == int(k):
                return pid
        return study._legacy_blind_id(manifest["run"], w, src, str(k))

    idx = {}
    for bid, v in verdicts.items():
        it = key[bid]
        idx.setdefault(it["target"], {}).setdefault(it["condition"], {}).setdefault(it["case_type"], {}) \
           .setdefault(it["case"], []).append((float(v["rating"]), v["verdict"], v.get("positive_register"),
                                               set(v.get("markers") or []), it["repeat"], it.get("source", ""), it.get("k", 0)))

    controls = [c for c in ("wrong", "shuffled", "none") if c in manifest["conditions"]]
    pooled = {"flattened": [], "impostor": []}
    for w in sorted(idx):
        lines += [f"## {w}", ""]
        conds = idx[w]
        lines.append("| condition | authentic minus flattened | authentic minus impostor | authentic accepted | "
                     "atypical accepted | flattened rejected | impostor rejected | override not failed |")
        lines.append("|---|---|---|---|---|---|---|---|")
        per_case, degenerate = {}, set()
        for cond in manifest["conditions"]:
            c = conds.get(cond, {})
            auth = {**c.get("authentic", {}), **c.get("atypical", {})}
            auth_mean = {case: _mean([r for r, *_ in xs]) for case, xs in auth.items()}
            fl, kept_fl_cases = {}, set()
            for case, xs in c.get("flattened", {}).items():
                src, k = xs[0][5], xs[0][6]
                pid = pid_for(w, src, k)
                if pid in excluded or pid in contrary or src not in auth_mean:
                    continue
                fl[case] = auth_mean[src] - _mean([r for r, *_ in xs])
                kept_fl_cases.add(case)
            all_auth = _mean(list(auth_mean.values()))
            imp = {case: all_auth - _mean([r for r, *_ in xs]) for case, xs in c.get("impostor", {}).items()
                   if all_auth is not None}
            per_case[cond] = {"flattened": fl, "impostor": imp}

            def rate(ctype, ok, only=None):
                xs = [x for case, rows in c.get(ctype, {}).items() if only is None or case in only for x in rows]
                pieces = len([1 for case in c.get(ctype, {}) if only is None or case in only])
                return (sum(1 for x in xs if ok(x)), len(xs), pieces)

            accept = lambda x: x[1] in ("PASS", "light REVISE") and x[2] is not False
            acc, atyp = rate("authentic", accept), rate("atypical", accept)
            rej = rate("flattened", lambda x: x[1] in ("REVISE", "REWRITE"), kept_fl_cases)
            impr = rate("impostor", lambda x: x[1] != "PASS")
            ovr = rate("override", lambda x: x[1] in ("PASS", "light REVISE"))
            # a control whose verdicts sit on one side of the pass bar for every
            # authentic and flattened case cannot discriminate at all; its margin
            # would make any lift look large (I165)
            on_pass = [accept(x) for ct in ("authentic", "atypical", "flattened") for rows in c.get(ct, {}).values() for x in rows]
            if cond in controls and on_pass and (all(on_pass) or not any(on_pass)):
                degenerate.add(cond)
            cell = lambda t: f"{t[0]}/{t[1]} ({t[2]} piece(s))" if t[1] else "-"
            lines.append(f"| {cond}{' (degenerate)' if cond in degenerate else ''} | {_fmt(_mean(list(fl.values())), True)} | "
                         f"{_fmt(_mean(list(imp.values())), True)} | {cell(acc)} | {cell(atyp)} | {cell(rej)} | {cell(impr)} | {cell(ovr)} |")

        # lift against each control, paired by case, with an interval (I165)
        if "correct" in per_case:
            lines += ["", "| correct minus control | flattened lift [95% interval] (cases) | impostor lift [95% interval] (cases) |",
                      "|---|---|---|"]
            use = [c for c in controls if c in per_case and c not in degenerate]
            for kind in ("flattened", "impostor"):
                pooled_diffs = []
                for case, m in per_case["correct"][kind].items():
                    cs = [per_case[c][kind][case] for c in use if case in per_case[c][kind]]
                    if cs:
                        pooled_diffs.append(m - _mean(cs))
                if pooled_diffs:
                    pooled[kind].append(_mean(pooled_diffs))
            for ctl in [c for c in controls if c in per_case]:
                cells = []
                for kind in ("flattened", "impostor"):
                    diffs = [m - per_case[ctl][kind][case] for case, m in per_case["correct"][kind].items()
                             if case in per_case[ctl][kind]]
                    ci = _boot(diffs, f"{manifest['seed']}-{w}-{ctl}-{kind}")
                    cells.append(f"{_fmt(_mean(diffs), True)} [{_fmt(ci[0], True)}, {_fmt(ci[1], True)}] ({len(diffs)})" if ci
                                 else f"{_fmt(_mean(diffs), True)} ({len(diffs)})")
                lines.append(f"| {ctl}{' (degenerate: not pooled)' if ctl in degenerate else ''} | {cells[0]} | {cells[1]} |")
            for extra in ("linter", "fingerprint"):
                if extra in per_case:
                    lines.append(f"| floor: {extra} margin | {_fmt(_mean(list(per_case[extra]['flattened'].values())), True)} | "
                                 f"{_fmt(_mean(list(per_case[extra]['impostor'].values())), True)} |")

        # stability across repeats, correct condition, over the pairs still scored (I166)
        c = conds.get("correct", {})
        exact = adjacent = severe = pairs = 0
        jaccards = []
        for ctype, cases in c.items():
            for case, xs in cases.items():
                if ctype == "flattened" and case not in per_case.get("correct", {}).get("flattened", {}):
                    continue
                for i in range(len(xs)):
                    for j in range(i + 1, len(xs)):
                        pairs += 1
                        a, b = VERDICT_SCORE[xs[i][1]], VERDICT_SCORE[xs[j][1]]
                        exact += a == b
                        adjacent += abs(a - b) == 1
                        severe += abs(a - b) > 1
                        ma, mb = xs[i][3], xs[j][3]
                        if ma or mb:
                            jaccards.append(len(ma & mb) / len(ma | mb))
        if pairs:
            lines += ["", f"**Stability across repeats (correct profile):** exact {exact}/{pairs}, adjacent {adjacent}/{pairs}, "
                          f"severe {severe}/{pairs}; explanation overlap (Jaccard of markers cited) {_fmt(_mean(jaccards))}"]
        lines.append("")

    if pooled["flattened"] or pooled["impostor"]:
        lines += ["## Pooled correct-profile lift across writers (non-degenerate controls only)", ""]
        for kind in ("flattened", "impostor"):
            xs = pooled[kind]
            if xs:
                lines.append(f"- authentic versus {kind}: mean {_mean(xs):+.2f} over {len(xs)} writer(s), "
                             f"range {min(xs):+.2f} to {max(xs):+.2f}")
        lines.append("")
    if decided or excluded:
        lines += ["## Reader reference", "",
                  f"{len(decided)} pair(s) read: {len(excluded)} marked same and {len(contrary)} where the reader heard the "
                  f"flattening as the writer; both kinds are left out of the model's flattened scores.", ""]
        # model-reader agreement per condition, over the pairs the reader decided A or B
        agree_rows = []
        for cond in manifest["conditions"]:
            hit = tot = 0
            for w in idx:
                c = idx[w].get(cond, {})
                auth = {**c.get("authentic", {}), **c.get("atypical", {})}
                for case, xs in c.get("flattened", {}).items():
                    src, k = xs[0][5], xs[0][6]
                    pid = pid_for(w, src, k)
                    if pid not in decided or decided[pid] == "SAME" or src not in auth:
                        continue
                    model_auth = _mean([r for r, *_ in auth[src]]) > _mean([r for r, *_ in xs])
                    reader_auth = decided[pid] == keyd.get(pid, {}).get("authentic_is")
                    tot += 1
                    hit += model_auth == reader_auth
            if tot:
                agree_rows.append(f"| {cond} | {hit}/{tot} |")
        if agree_rows:
            lines += ["| condition | model agrees with the reader |", "|---|---|"] + agree_rows + [""]

    # per-rule linter precision on authentic text
    flp = os.path.join(run_dir, "findings-labels.csv")
    if os.path.exists(flp):
        per, labelled = {}, 0
        for row in csv.DictReader(open(flp, newline="")):
            lab = (row.get("label") or "").strip().upper()
            if lab not in ("TP", "FP"):
                continue
            labelled += 1
            d = per.setdefault(row["rule_id"], [0, 0])
            d[0 if lab == "TP" else 1] += 1
        if labelled:
            wp = os.path.join(run_dir, "authentic-words.txt")
            words = int(study._read(wp) or "0") if os.path.exists(wp) else 0
            lines += ["## Linter precision on authentic text", "",
                      f"{labelled} finding(s) labelled over {words:,} authentic words.", "",
                      "| rule | TP | FP | precision | false flags per 1,000 words |", "|---|---|---|---|---|"]
            for rid, (tp, fp) in sorted(per.items(), key=lambda kv: -(kv[1][1])):
                lines.append(f"| {rid} | {tp} | {fp} | {tp / (tp + fp):.2f} | {fp * 1000 / words if words else 0:.2f} |")
            tot_fp = sum(v[1] for v in per.values())
            lines += ["", f"All rules: {tot_fp} false flag(s), {tot_fp * 1000 / words if words else 0:.2f} per 1,000 authentic words.", ""]

    lines += ["## Reading it",
              "- Lift near zero: the judgment is reacting to polish or register, not to the writer.",
              "- A control marked degenerate puts every case on one side of the pass bar; it is shown, never pooled.",
              "- Each lift is paired by case; an interval that spans zero is not a finding.",
              "- Severe movement between repeats is instability; report it, do not average it away.",
              "- One reader and a few writers is a pilot; the writer is the unit. See docs/blind-eval.md."]
    study._write(os.path.join(run_dir, "results.md"), "\n".join(lines))
    print("\n".join(lines))
    print(f"\nwrote {run_dir}/results.md")
