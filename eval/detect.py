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

CONDITIONS = ("correct", "wrong", "shuffled", "none", "linter")
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
    return "# (shuffled profile: the writer's own lines in scrambled order; a control)\n\n" + "\n".join(lines) + "\n"


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
                                    "none": None, "linter": None}[cond],
                        "verdict": f"verdicts/{bid}.json", "surface": args.surface,
                        "tool_version": study._tool_version(), "config_sha256": study._config_sha(args.surface),
                        "profile_sha256": study._profile_sha(target), "model": "",
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


def prompts(args, run_dir, manifest):
    n = floor = 0
    for it in manifest["items"]:
        text = study._read(os.path.join(study.DATA, it["text"])).strip()
        if it["condition"] == "linter":
            study._write(os.path.join(run_dir, it["verdict"]), json.dumps(_linter_verdict(text, it["surface"]), indent=2))
            it["model"] = "none (linter floor)"
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
    print(f"wrote {n} judging prompts to {run_dir}/prompts/ and {floor} linter-floor verdicts to {run_dir}/verdicts/")
    print("run every prompt with the SAME judging model and settings named in prereg.md; save each\n"
          f"JSON reply to {run_dir}/verdicts/<blind_id>.json, then: study.py sheet {args.run}")


def sheet(args, run_dir, manifest):
    """The reader's two blind sheets: pairwise authentic-versus-flattened, and
    the mechanical findings on authentic text to label true or false."""
    rng = random.Random(str(manifest["seed"]) + "-pairs")
    by_writer = {}
    for it in manifest["items"]:
        if it["condition"] == "correct" and it["repeat"] == 1:
            by_writer.setdefault(it["target"], {}).setdefault(it["case_type"], []).append(it)
    lines = [f"# Pairwise reference sheet: run {manifest['run']}", "",
             "For each pair, read both and mark in pairs.csv which sounds more like the named writer",
             "(A or B), or 'same' if you cannot tell. Do NOT open manifest.json first. A pair marked",
             "'same' is excluded from the model's scoring: if a reader cannot tell them apart, the",
             "model is not scored for failing to.", ""]
    rows = []
    for w in sorted(by_writer):
        auth = {it["case"]: it for it in by_writer[w].get("authentic", []) + by_writer[w].get("atypical", [])}
        for fl in by_writer[w].get("flattened", []):
            src = auth.get(fl["source"])
            if not src:
                continue
            a_text = study._read(os.path.join(study.DATA, src["text"])).strip()
            b_text = study._read(os.path.join(study.DATA, fl["text"])).strip()
            flip = rng.random() < 0.5
            first, second = (b_text, a_text) if flip else (a_text, b_text)
            pid = study._blind_id(manifest["run"], w, src["case"], str(fl["k"]))
            lines += [f"## {w} / pair {pid}", "", "### A", "", first, "", "### B", "", second, ""]
            rows.append({"pair_id": pid, "writer": w, "pick": "", "_authentic_is": "B" if flip else "A"})
    study._write(os.path.join(run_dir, "pairs-sheet.md"), "\n".join(lines))
    with open(os.path.join(run_dir, "pairs.csv"), "w", newline="") as fh:
        wtr = csv.DictWriter(fh, fieldnames=["pair_id", "writer", "pick"])
        wtr.writeheader()
        for r in rows:
            wtr.writerow({k: r[k] for k in ("pair_id", "writer", "pick")})
    study._write(os.path.join(run_dir, "pairs-key.json"), json.dumps({r["pair_id"]: r["_authentic_is"] for r in rows}, indent=2))

    # mechanical findings on authentic text, for per-rule precision
    sys.path.insert(0, study.TOOLS)
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
    print(f"wrote {run_dir}/pairs-sheet.md ({len(rows)} pair(s)) and pairs.csv; mark A, B, or same.")
    print(f"wrote {run_dir}/findings-labels.csv ({len(frows)} mechanical finding(s) on {words:,} authentic words); "
          "mark each label TP (a real tell) or FP (the writer's own usage).")
    print(f"then: study.py score {manifest['run']}")


def _load_verdicts(run_dir, manifest):
    out = {}
    for it in manifest["items"]:
        p = os.path.join(run_dir, it["verdict"])
        if not os.path.exists(p):
            continue
        try:
            raw = study._read(p)
            m = re.search(r"\{.*\}", raw, re.S)
            v = json.loads(m.group(0) if m else raw)
        except (json.JSONDecodeError, AttributeError):
            print(f"unreadable verdict: {p}")
            continue
        if v.get("verdict") not in VERDICTS or not isinstance(v.get("rating"), (int, float)):
            print(f"verdict {p} is missing a valid rating or verdict; skipped")
            continue
        out[it["blind_id"]] = v
    return out


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _fmt(x, plus=False):
    if x is None:
        return "n/a"
    return f"{x:+.2f}" if plus else f"{x:.2f}"


def score(run_dir, manifest):
    key = {it["blind_id"]: it for it in manifest["items"]}
    verdicts = _load_verdicts(run_dir, manifest)
    lines = [f"# Results: run {manifest['run']} (detection task)", ""]
    prereg = os.path.join(run_dir, "prereg.md")
    if os.path.exists(prereg) and "TODO" in study._read(prereg):
        lines.append("**prereg.md still has TODO fields. These numbers are exploratory until it is complete.**")
        lines.append("")
    if not verdicts:
        lines.append("No verdicts found under verdicts/. Run the prompts first.")
        study._write(os.path.join(run_dir, "results.md"), "\n".join(lines))
        print("\n".join(lines))
        return

    # reader reference: which pairs are usable
    excluded_pairs, reader_hits, reader_total = set(), 0, 0
    pairs_csv, pairs_key = os.path.join(run_dir, "pairs.csv"), os.path.join(run_dir, "pairs-key.json")
    if os.path.exists(pairs_csv) and os.path.exists(pairs_key):
        keyd = json.loads(study._read(pairs_key))
        for row in csv.DictReader(open(pairs_csv, newline="")):
            pick = (row.get("pick") or "").strip().upper()
            if not pick:
                continue
            reader_total += 1
            if pick == "SAME":
                excluded_pairs.add(row["pair_id"])
            elif pick == keyd.get(row["pair_id"]):
                reader_hits += 1

    # index: writer -> condition -> case_type -> case -> [(rating, verdict, pr, markers, repeat)]
    idx = {}
    for bid, v in verdicts.items():
        it = key[bid]
        idx.setdefault(it["target"], {}).setdefault(it["condition"], {}).setdefault(it["case_type"], {}) \
           .setdefault(it["case"], []).append((float(v["rating"]), v["verdict"], v.get("positive_register"),
                                               set(v.get("markers") or []), it["repeat"], it.get("source", ""), it.get("k", 0)))

    controls = [c for c in ("wrong", "shuffled", "none") if c in manifest["conditions"]]
    lifts_fl, lifts_imp = [], []
    for w in sorted(idx):
        lines += [f"## {w}", ""]
        conds = idx[w]
        # paired margins per condition
        lines.append("| condition | authentic minus flattened | authentic minus impostor | authentic accepted | flattened rejected | impostor rejected | override not failed |")
        lines.append("|---|---|---|---|---|---|---|")
        margins = {}
        for cond in manifest["conditions"]:
            c = conds.get(cond, {})
            auth = {**c.get("authentic", {}), **c.get("atypical", {})}
            auth_mean = {case: _mean([r for r, *_ in xs]) for case, xs in auth.items()}
            fl_margins = []
            for case, xs in c.get("flattened", {}).items():
                src = xs[0][5]
                pid = study._blind_id(manifest["run"], w, src, str(xs[0][6]))
                if pid in excluded_pairs or src not in auth_mean:
                    continue
                fl_margins.append(auth_mean[src] - _mean([r for r, *_ in xs]))
            imp_margins = []
            all_auth = _mean(list(auth_mean.values()))
            for case, xs in c.get("impostor", {}).items():
                if all_auth is not None:
                    imp_margins.append(all_auth - _mean([r for r, *_ in xs]))
            margins[cond] = (_mean(fl_margins), _mean(imp_margins))
            def rate(ctype, ok):
                xs = [x for case in c.get(ctype, {}).values() for x in case]
                return f"{sum(1 for x in xs if ok(x))}/{len(xs)}" if xs else "-"
            acc = rate("authentic", lambda x: x[1] in ("PASS", "light REVISE") and x[2] is not False)
            rej = rate("flattened", lambda x: x[1] in ("REVISE", "REWRITE"))
            imp = rate("impostor", lambda x: x[1] != "PASS")
            ovr = rate("override", lambda x: x[1] in ("PASS", "light REVISE"))
            lines.append(f"| {cond} | {_fmt(margins[cond][0], True)} | {_fmt(margins[cond][1], True)} | {acc} | {rej} | {imp} | {ovr} |")
        # lift
        if "correct" in margins:
            cf, ci = margins["correct"]
            ctrl_f = [margins[c][0] for c in controls if c in margins and margins[c][0] is not None]
            ctrl_i = [margins[c][1] for c in controls if c in margins and margins[c][1] is not None]
            lf = cf - _mean(ctrl_f) if cf is not None and ctrl_f else None
            li = ci - _mean(ctrl_i) if ci is not None and ctrl_i else None
            floor = margins.get("linter", (None, None))
            lines.append("")
            lines.append(f"**Correct-profile lift** (correct margin minus the mean of {', '.join(controls) or 'no controls'}): "
                         f"flattened {_fmt(lf, True)}, impostor {_fmt(li, True)}"
                         + (f"; linter-only floor margins {_fmt(floor[0], True)} / {_fmt(floor[1], True)}" if "linter" in margins else ""))
            if lf is not None:
                lifts_fl.append(lf)
            if li is not None:
                lifts_imp.append(li)
        # stability across repeats, correct condition
        c = conds.get("correct", {})
        exact = adjacent = severe = pairs = 0
        jaccards = []
        for ctype, cases in c.items():
            for case, xs in cases.items():
                if len(xs) < 2:
                    continue
                for i in range(len(xs)):
                    for j in range(i + 1, len(xs)):
                        pairs += 1
                        a, b = VERDICT_SCORE[xs[i][1]], VERDICT_SCORE[xs[j][1]]
                        if a == b:
                            exact += 1
                        elif abs(a - b) == 1:
                            adjacent += 1
                        else:
                            severe += 1
                        ma, mb = xs[i][3], xs[j][3]
                        if ma or mb:
                            jaccards.append(len(ma & mb) / len(ma | mb))
        if pairs:
            lines.append("")
            lines.append(f"**Stability across repeats (correct profile):** exact {exact}/{pairs}, adjacent {adjacent}/{pairs}, "
                         f"severe {severe}/{pairs}; explanation overlap (Jaccard of markers cited) "
                         f"{_fmt(_mean(jaccards))}")
        lines.append("")

    if lifts_fl or lifts_imp:
        lines += ["## Pooled correct-profile lift across writers", ""]
        if lifts_fl:
            lines.append(f"- authentic versus flattened: mean {_mean(lifts_fl):+.2f} over {len(lifts_fl)} writer(s), "
                         f"range {min(lifts_fl):+.2f} to {max(lifts_fl):+.2f}")
        if lifts_imp:
            lines.append(f"- authentic versus impostor: mean {_mean(lifts_imp):+.2f} over {len(lifts_imp)} writer(s), "
                         f"range {min(lifts_imp):+.2f} to {max(lifts_imp):+.2f}")
        lines.append("")
    if reader_total:
        lines += ["## Reader reference", "",
                  f"The reader told authentic from flattened on {reader_hits}/{reader_total - len(excluded_pairs)} "
                  f"decided pair(s); {len(excluded_pairs)} pair(s) marked same and excluded from the model's scoring.", ""]

    # per-rule linter precision on authentic text
    fl = os.path.join(run_dir, "findings-labels.csv")
    if os.path.exists(fl):
        per = {}
        labelled = 0
        for row in csv.DictReader(open(fl, newline="")):
            lab = (row.get("label") or "").strip().upper()
            if lab not in ("TP", "FP"):
                continue
            labelled += 1
            d = per.setdefault(row["rule_id"], [0, 0])
            d[0 if lab == "TP" else 1] += 1
        if labelled:
            words = int(study._read(os.path.join(run_dir, "authentic-words.txt")) or "0") if os.path.exists(os.path.join(run_dir, "authentic-words.txt")) else 0
            lines += ["## Linter precision on authentic text", "",
                      f"{labelled} finding(s) labelled over {words:,} authentic words.", "",
                      "| rule | TP | FP | precision | false flags per 1,000 words |", "|---|---|---|---|---|"]
            for rid, (tp, fp) in sorted(per.items(), key=lambda kv: -(kv[1][1])):
                prec = tp / (tp + fp)
                ff = fp * 1000 / words if words else 0
                lines.append(f"| {rid} | {tp} | {fp} | {prec:.2f} | {ff:.2f} |")
            tot_fp = sum(v[1] for v in per.values())
            lines.append("")
            lines.append(f"All rules: {tot_fp} false flag(s), {tot_fp * 1000 / words if words else 0:.2f} per 1,000 authentic words.")
            lines.append("")

    lines += ["## Reading it",
              "- Lift near zero: the judgment is reacting to polish or register, not to the writer.",
              "- Lift under the correct profile that the linter-only floor does not reach is the claim.",
              "- Severe movement between repeats is instability; report it, do not average it away.",
              "- One reader and a few writers is a pilot; the writer is the unit. See docs/blind-eval.md."]
    study._write(os.path.join(run_dir, "results.md"), "\n".join(lines))
    print("\n".join(lines))
    print(f"\nwrote {run_dir}/results.md")
