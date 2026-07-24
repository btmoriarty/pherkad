#!/usr/bin/env python3
"""Pherkad voice-authoring evaluation harness.

Turns "have Pherkad write with a profile, then validate the output" into a
blinded study that measures correct-profile lift: whether a draft written with
the writer's own profile reads more like the writer than drafts written with a
wrong profile or no profile. Without those controls and blinding, a single
labeled draft cannot tell voice capture from competent prose.

The judgment is human. This tool does the bookkeeping that keeps the judgment
honest: conditions, randomization, hidden keys, and the arithmetic.

Data (writers, briefs, runs) lives under eval/data/ and is gitignored. The code
and protocol are shareable; the writers' samples are not.

Pipeline:
  study.py add-writer <id>
  study.py add-brief  <id>
  study.py plan <run> --brief <b> --writers a,b,c [--conditions correct,wrong,none] [--anchor]
  study.py prompts <run>     # emits authoring prompts to run through Pherkad
  # ... run each prompt through Pherkad authoring; save output to the named draft file ...
  study.py sheet <run> [--format rating|forcedchoice]
  # ... fill in ratings.csv, blind ...
  study.py score <run>

Stdlib only.
"""
import argparse
import csv
import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
WRITERS = os.path.join(DATA, "writers")
BRIEFS = os.path.join(DATA, "briefs")
RUNS = os.path.join(DATA, "runs")


def _ensure(*paths):
    for p in paths:
        os.makedirs(p, exist_ok=True)


def _blind_id(*parts):
    h = hashlib.sha1("|".join(parts).encode()).hexdigest()[:8]
    return "item-" + h


# ---------------------------------------------------------------------------
def add_writer(args):
    d = os.path.join(WRITERS, args.id)
    _ensure(os.path.join(d, "samples"), os.path.join(d, "holdout"))
    prof = os.path.join(d, "profile.md")
    if not os.path.exists(prof):
        with open(prof, "w") as fh:
            fh.write(f"# Voice profile: {args.id}\n\n"
                     "Build this from the writer's samples with Pherkad's profile\n"
                     "builder (references/profile_builder.md), holding one sample back\n"
                     "into holdout/ before extraction. Paste the finished profile here.\n")
    print(f"writer '{args.id}' ready: add samples to {d}/samples, one held-out\n"
          f"piece to {d}/holdout, and the built profile to {prof}")


def add_brief(args):
    _ensure(BRIEFS)
    path = os.path.join(BRIEFS, args.id + ".md")
    if not os.path.exists(path):
        with open(path, "w") as fh:
            fh.write(f"# Brief: {args.id}\n\n"
                     "A factual brief or notes on a subject the target writers have NOT\n"
                     "written about, so authoring composes rather than paraphrases. State\n"
                     "the facts, the audience, and the format. No source prose to imitate.\n")
    print(f"brief '{args.id}' ready: {path}")


# ---------------------------------------------------------------------------
def plan(args):
    _ensure(RUNS)
    run_dir = os.path.join(RUNS, args.run)
    if os.path.exists(os.path.join(run_dir, "manifest.json")):
        sys.exit(f"run '{args.run}' already planned; delete {run_dir} to redo")
    _ensure(os.path.join(run_dir, "drafts"), os.path.join(run_dir, "prompts"))

    writers = [w.strip() for w in args.writers.split(",") if w.strip()]
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    for w in writers:
        if not os.path.isdir(os.path.join(WRITERS, w)):
            sys.exit(f"unknown writer '{w}' (run add-writer first)")
    if not os.path.exists(os.path.join(BRIEFS, args.brief + ".md")):
        sys.exit(f"unknown brief '{args.brief}'")

    rng = random.Random(args.seed)
    items = []
    for target in writers:
        for cond in conditions:
            if cond == "correct":
                profile = target
            elif cond == "wrong":
                others = [w for w in writers if w != target] or \
                         [w for w in _all_writers() if w != target]
                if not others:
                    continue
                profile = rng.choice(others)
            elif cond == "none":
                profile = None
            else:
                sys.exit(f"unknown condition '{cond}'")
            bid = _blind_id(args.run, target, args.brief, cond, str(profile))
            items.append({
                "blind_id": bid, "target": target, "brief": args.brief,
                "condition": cond, "profile": profile, "kind": "authored",
                "draft": f"drafts/{bid}.md",
            })
        if args.anchor:
            hp = _pick_holdout(target)
            bid = _blind_id(args.run, target, args.brief, "anchor", hp or "none")
            items.append({
                "blind_id": bid, "target": target, "brief": args.brief,
                "condition": "anchor", "profile": target, "kind": "anchor",
                "draft": f"drafts/{bid}.md", "source": hp,
            })
    manifest = {"run": args.run, "brief": args.brief, "writers": writers,
                "conditions": conditions, "anchor": args.anchor,
                "seed": args.seed, "items": items}
    with open(os.path.join(run_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    print(f"planned run '{args.run}': {len(items)} items "
          f"({len(writers)} writers x {conditions} + {'anchor' if args.anchor else 'no anchor'}).")
    print(f"next: study.py prompts {args.run}")


def _all_writers():
    return sorted(d for d in os.listdir(WRITERS)
                  if os.path.isdir(os.path.join(WRITERS, d))) if os.path.isdir(WRITERS) else []


def _pick_holdout(writer):
    hd = os.path.join(WRITERS, writer, "holdout")
    if not os.path.isdir(hd):
        return None
    files = sorted(f for f in os.listdir(hd) if not f.startswith("."))
    return os.path.join("writers", writer, "holdout", files[0]) if files else None


# ---------------------------------------------------------------------------
def prompts(args):
    run_dir = os.path.join(RUNS, args.run)
    manifest = _load_manifest(args.run)
    brief_txt = _read(os.path.join(BRIEFS, manifest["brief"] + ".md"))
    n = 0
    for it in manifest["items"]:
        draft_abs = os.path.join(run_dir, it["draft"])
        if it["kind"] == "anchor":
            src = it.get("source")
            if src and os.path.exists(os.path.join(DATA, src)):
                _write(draft_abs, _read(os.path.join(DATA, src)))
            else:
                _write(draft_abs, "(no holdout sample found for this writer)\n")
            continue
        if it["profile"] is None:
            profile_txt = "(NO PROFILE: write in a clean, competent default voice.)"
        else:
            profile_txt = _read(os.path.join(WRITERS, it["profile"], "profile.md"))
        prompt = (
            "Author a draft from the brief below in the target voice, using Pherkad's\n"
            "authoring mode (references/authoring.md): write from the profile's positive\n"
            "markers, avoid the product-marketing register, preserve hedging, anchor in\n"
            "concrete detail, keep every fact in the brief, and self-validate before\n"
            "returning. Compose from the brief; do not imitate any source prose.\n\n"
            "Return ONLY the finished draft, no commentary.\n\n"
            f"=== BRIEF ===\n{brief_txt}\n\n=== VOICE PROFILE ===\n{profile_txt}\n"
        )
        _write(os.path.join(run_dir, "prompts", it["blind_id"] + ".txt"), prompt)
        n += 1
    print(f"wrote {n} authoring prompts to {run_dir}/prompts/")
    print("run each through Pherkad authoring, save the output to the matching\n"
          f"{run_dir}/drafts/<blind_id>.md, then: study.py sheet {args.run}")


# ---------------------------------------------------------------------------
def sheet(args):
    run_dir = os.path.join(RUNS, args.run)
    manifest = _load_manifest(args.run)
    rng = random.Random(str(manifest["seed"]) + "-sheet")

    # group items by target writer; shuffle within each so condition order leaks nothing
    by_writer = {}
    for it in manifest["items"]:
        by_writer.setdefault(it["target"], []).append(it)
    for w in by_writer:
        rng.shuffle(by_writer[w])

    lines = [f"# Blind rating sheet: run {manifest['run']} (brief {manifest['brief']})", ""]
    if args.format == "rating":
        lines += ["Rate each candidate 1 to 5 for how much it sounds like the named writer,",
                  "then also flag fidelity. Do NOT open manifest.json until you have rated everything.",
                  "", "Scale: 5 unmistakably this writer, 3 could be anyone, 1 clearly not them.",
                  "Fidelity flag: F if it invents facts, over-claims certainty, or caricatures the",
                  "writer's tics; else leave blank.", ""]
    else:
        lines += ["For each writer, read the reference, then pick the ONE candidate that most",
                  "sounds like them. Record its letter in ratings.csv. Do NOT open manifest.json first.", ""]

    rows = []  # for the csv template
    for w in sorted(by_writer):
        lines.append(f"## Writer: {w}")
        ref = _reference_block(w)
        lines.append("")
        lines.append("Reference (real writing by this writer):")
        lines.append("")
        lines.append(ref)
        lines.append("")
        lines.append("Candidates:")
        lines.append("")
        for i, it in enumerate(by_writer[w]):
            letter = chr(ord("a") + i)
            draft = _read(os.path.join(run_dir, it["draft"])).strip() or "(draft not generated yet)"
            lines.append(f"### {w} / candidate {letter}  [{it['blind_id']}]")
            lines.append("")
            lines.append(draft)
            lines.append("")
            rows.append({"blind_id": it["blind_id"], "writer": w, "candidate": letter,
                         "rating": "", "fidelity_flag": "", "forced_choice_pick": ""})

    _write(os.path.join(run_dir, "rating-sheet.md"), "\n".join(lines))
    csv_path = os.path.join(run_dir, "ratings.csv")
    with open(csv_path, "w", newline="") as fh:
        wtr = csv.DictWriter(fh, fieldnames=["blind_id", "writer", "candidate",
                                             "rating", "fidelity_flag", "forced_choice_pick"])
        wtr.writeheader()
        for r in rows:
            wtr.writerow(r)
    print(f"wrote {run_dir}/rating-sheet.md and a blank {csv_path}")
    print("rate blind (rating: fill 'rating' 1-5 and 'fidelity_flag'; forcedchoice: put the\n"
          f"chosen letter in 'forced_choice_pick' on any one row per writer), then: study.py score {args.run}")


def _reference_block(writer):
    sd = os.path.join(WRITERS, writer, "samples")
    if os.path.isdir(sd):
        files = sorted(f for f in os.listdir(sd) if not f.startswith("."))
        if files:
            txt = _read(os.path.join(sd, files[0])).strip()
            return txt[:1200] + ("\n..." if len(txt) > 1200 else "")
    return "(no reference sample on file)"


# ---------------------------------------------------------------------------
def score(args):
    run_dir = os.path.join(RUNS, args.run)
    manifest = _load_manifest(args.run)
    key = {it["blind_id"]: it for it in manifest["items"]}
    csv_path = os.path.join(run_dir, "ratings.csv")
    if not os.path.exists(csv_path):
        sys.exit("no ratings.csv; run sheet and fill it in first")

    ratings, picks = {}, {}
    with open(csv_path, newline="") as fh:
        for row in csv.DictReader(fh):
            bid = row["blind_id"]
            if row.get("rating", "").strip():
                ratings[bid] = (float(row["rating"]), row.get("fidelity_flag", "").strip().upper())
            if row.get("forced_choice_pick", "").strip():
                picks.setdefault(row["writer"], []).append(bid)

    # rating mode: per-writer mean by condition, correct-profile lift
    per_writer = {}
    for bid, (val, flag) in ratings.items():
        it = key.get(bid)
        if not it:
            continue
        w = it["target"]
        per_writer.setdefault(w, {}).setdefault(it["condition"], []).append((val, flag))

    lines = [f"# Results: run {manifest['run']} (brief {manifest['brief']})", ""]
    lifts = []
    if per_writer:
        lines.append("## Rating: mean 'sounds like the writer' by condition, and lift")
        lines.append("")
        lines.append("Lift = correct minus the mean of the controls (wrong, none). Positive lift")
        lines.append("means the writer's own profile beat the controls; near zero means it did not.")
        lines.append("")
        for w in sorted(per_writer):
            conds = per_writer[w]
            means = {c: sum(v for v, _ in xs) / len(xs) for c, xs in conds.items()}
            controls = [means[c] for c in ("wrong", "none") if c in means]
            summary = ", ".join(f"{c}={means[c]:.2f}" for c in
                                ("correct", "wrong", "none", "anchor") if c in means)
            if "correct" in means and controls:
                lift = means["correct"] - sum(controls) / len(controls)
                lifts.append(lift)
                cap = f", anchor(real)={means['anchor']:.2f}" if "anchor" in means else ""
                lines.append(f"- **{w}**: {summary}{cap}  ->  lift = {lift:+.2f}")
            else:
                lines.append(f"- **{w}**: {summary}  (need correct + a control for lift)")
        flags = [1 for _, f in
                 [x for xs in per_writer.values() for c in xs.values() for x in c] if f == "F"]
        if lifts:
            lines.append("")
            lines.append(f"**Pooled correct-profile lift:** mean {sum(lifts)/len(lifts):+.2f} "
                         f"across {len(lifts)} writer(s), range {min(lifts):+.2f} to {max(lifts):+.2f}.")
        if flags:
            lines.append(f"**Fidelity flags:** {sum(flags)} candidate(s) flagged (invented fact, "
                         "over-certainty, or caricature). A high-rated but flagged draft does not count as success.")

    # forced-choice mode: accuracy = picked the correct-profile candidate
    if picks:
        lines.append("")
        lines.append("## Forced choice: did you pick the correct-profile draft?")
        lines.append("")
        hits = total = 0
        for w, chosen in picks.items():
            for bid in chosen:
                total += 1
                if key.get(bid, {}).get("condition") == "correct":
                    hits += 1
        lines.append(f"Picked the correct-profile draft on {hits}/{total} writer-briefs "
                     f"({(hits/total*100 if total else 0):.0f}%). Chance depends on the number of candidates.")

    if not per_writer and not picks:
        lines.append("No ratings found. Fill ratings.csv (rating 1-5, or forced_choice_pick).")

    lines += ["", "## Reading it",
              "- Lift near zero: the profile is not adding writer-specific value; the tool is",
              "  scoring general polish. Keep the claim advisory.",
              "- Real lift that holds across writers and registers, with fidelity intact: evidence",
              "  the authoring captures voice. One run on a few writers is a pilot, not the claim;",
              "  see docs/blind-eval.md for the confirmatory design (~20-30 writers, preregistered)."]
    _write(os.path.join(run_dir, "results.md"), "\n".join(lines))
    print("\n".join(lines))
    print(f"\nwrote {run_dir}/results.md")


# ---------------------------------------------------------------------------
def _load_manifest(run):
    p = os.path.join(RUNS, run, "manifest.json")
    if not os.path.exists(p):
        sys.exit(f"no run '{run}' (plan it first)")
    with open(p) as fh:
        return json.load(fh)


def _read(p):
    with open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _write(p, text):
    _ensure(os.path.dirname(p))
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)


def main(argv):
    ap = argparse.ArgumentParser(description="Pherkad voice-authoring evaluation harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add-writer"); s.add_argument("id"); s.set_defaults(fn=add_writer)
    s = sub.add_parser("add-brief"); s.add_argument("id"); s.set_defaults(fn=add_brief)
    s = sub.add_parser("plan")
    s.add_argument("run"); s.add_argument("--brief", required=True)
    s.add_argument("--writers", required=True)
    s.add_argument("--conditions", default="correct,wrong,none")
    s.add_argument("--anchor", action="store_true")
    s.add_argument("--seed", type=int, default=1); s.set_defaults(fn=plan)
    s = sub.add_parser("prompts"); s.add_argument("run"); s.set_defaults(fn=prompts)
    s = sub.add_parser("sheet"); s.add_argument("run")
    s.add_argument("--format", choices=["rating", "forcedchoice"], default="rating")
    s.set_defaults(fn=sheet)
    s = sub.add_parser("score"); s.add_argument("run"); s.set_defaults(fn=score)
    args = ap.parse_args(argv)
    _ensure(DATA, WRITERS, BRIEFS, RUNS)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
