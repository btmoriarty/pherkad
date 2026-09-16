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

Pipeline (authoring task, the default):
  study.py add-writer <id>
  study.py add-brief  <id>
  study.py plan <run> --brief <b> --writers a,b,c [--conditions correct,wrong,none] [--anchor]
  study.py prompts <run> [--model M]   # emits authoring prompts; records the model
  # ... run each prompt through Pherkad authoring; save output to the named draft file ...
  study.py sheet <run> [--format rating|forcedchoice]
  # ... fill in ratings.csv, blind ...
  study.py score <run>

Detection task (roadmap item 13; eval/detect.py):
  study.py plan <run> --task detect --writers a,b [--conditions correct,wrong,shuffled,none,linter] [--repeats 3]
  # ... cases live under writers/<w>/holdout, flattened, impostors, override; fill prereg.md ...
  study.py prompts <run> --model <judge>   # judging prompts; the linter floor's verdicts are written directly
  # ... save each judge reply as verdicts/<blind_id>.json ...
  study.py sheet <run>                     # pairwise reader sheet + mechanical findings to label
  study.py score <run>                     # paired margins, correct-profile lift, rates, stability, precision

Revision task (roadmap item 12): does feedback from the tools improve a draft
more than another editing pass would?
  study.py plan <run> --task revise --brief <b> --writers a,b [--arms ...] [--repeats N] [--surface post]
  # ... put each writer's starting draft in sources/<writer>.md ...
  study.py prompts <run> [--model M]   # one revision prompt per item, per arm
  # ... run each prompt with the SAME editing model and budget; save to the named draft ...
  study.py sheet <run>
  study.py score <run>
Arms: untouched (the source as is), generic (a self-review with no Pherkad
input, the control), mechanical (pherkad.py check findings only), judgment
(the skill's quick-mode judgment rules, mechanical calls disabled), both.
The primary outcome is each arm's rating minus the generic arm's, per writer,
with factual preservation required; a flagged draft counts against its arm
whatever its rating. Useful edits, unnecessary edits, and minutes are recorded
per draft. --repeats runs the same source through each arm N times so verdict
stability is measured, not assumed.

Provenance: every item in the manifest carries the tool version, the sha256 of
the effective rule set, the profile's sha256, and (after prompts --model) the
model that produced it, so a result can be traced to what made it.

Stdlib only; imports the tools beside skills/pherkad/tools for the mechanical arm.
"""
import argparse
import csv
import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "skills", "pherkad", "tools")
DATA = os.path.join(HERE, "data")
ARMS = ("untouched", "generic", "mechanical", "judgment", "both")
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
    if args.conditions is None:
        args.conditions = "correct,wrong,shuffled,none,linter" if args.task == "detect" else "correct,wrong,none"
    if args.task != "detect" and not args.brief:
        sys.exit("--brief is required for the author and revise tasks")
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    for w in writers:
        if not os.path.isdir(os.path.join(WRITERS, w)):
            sys.exit(f"unknown writer '{w}' (run add-writer first)")
    if args.task != "detect" and not os.path.exists(os.path.join(BRIEFS, args.brief + ".md")):
        sys.exit(f"unknown brief '{args.brief}'")

    rng = random.Random(args.seed)
    if args.task == "revise":
        return plan_revise(args, run_dir, writers, rng)
    if args.task == "detect":
        import detect
        return detect.plan(args, run_dir, writers, rng)
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
                "blind_id": bid, "target": target, "brief": args.brief, "task": "author",
                "condition": cond, "profile": profile, "kind": "authored",
                "draft": f"drafts/{bid}.md", "tool_version": _tool_version(),
                "profile_sha256": _profile_sha(profile) if profile else "", "model": "",
            })
        if args.anchor:
            hp = _pick_holdout(target)
            bid = _blind_id(args.run, target, args.brief, "anchor", hp or "none")
            items.append({
                "blind_id": bid, "target": target, "brief": args.brief,
                "condition": "anchor", "profile": target, "kind": "anchor",
                "draft": f"drafts/{bid}.md", "source": hp,
            })
    manifest = {"run": args.run, "task": "author", "brief": args.brief, "writers": writers,
                "conditions": conditions, "anchor": args.anchor,
                "seed": args.seed, "items": items}
    with open(os.path.join(run_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    print(f"planned run '{args.run}': {len(items)} items "
          f"({len(writers)} writers x {conditions} + {'anchor' if args.anchor else 'no anchor'}).")
    print(f"next: study.py prompts {args.run}")


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _tool_version():
    try:
        return _read(os.path.join(TOOLS, "..", "VERSION")).strip()
    except OSError:
        return "unknown"


def _config_sha(surface):
    """The sha of the effective rule set for a surface, via the tools beside this harness."""
    try:
        sys.path.insert(0, TOOLS)
        import pherkad  # noqa: WPS433
        cfg, _ = pherkad.load_layers(surface, None)
        return pherkad.config_sha256(cfg)[:16]
    except Exception:  # the tools are optional to the authoring task
        return ""


def _profile_sha(writer):
    p = os.path.join(WRITERS, writer, "profile.md")
    return _sha(_read(p)) if os.path.exists(p) else ""


def plan_revise(args, run_dir, writers, rng):
    """The revision experiment: one source draft per writer, every arm, N repeats."""
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    for a in arms:
        if a not in ARMS:
            sys.exit(f"unknown arm '{a}'; arms are {', '.join(ARMS)}")
    if "generic" not in arms:
        sys.exit("the revision task needs the 'generic' arm: it is the control every other arm is scored against")
    _ensure(os.path.join(run_dir, "sources"))
    items = []
    for target in writers:
        src = os.path.join(run_dir, "sources", target + ".md")
        if not os.path.exists(src):
            _write(src, "")
        for arm in arms:
            for rep in range(1, args.repeats + 1):
                bid = _blind_id(args.run, target, args.brief, "revise", arm, str(rep))
                items.append({
                    "blind_id": bid, "target": target, "brief": args.brief, "task": "revise",
                    "condition": arm, "arm": arm, "repeat": rep, "profile": target,
                    "kind": "revised", "source": f"sources/{target}.md", "draft": f"drafts/{bid}.md",
                    "surface": args.surface, "tool_version": _tool_version(),
                    "config_sha256": _config_sha(args.surface), "profile_sha256": _profile_sha(target),
                    "model": "",
                })
    manifest = {"run": args.run, "task": "revise", "brief": args.brief, "writers": writers,
                "arms": arms, "repeats": args.repeats, "surface": args.surface,
                "seed": args.seed, "items": items}
    with open(os.path.join(run_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    print(f"planned revision run '{args.run}': {len(items)} items "
          f"({len(writers)} writer(s) x {arms} x {args.repeats} repeat(s)).")
    print(f"next: put each writer's starting draft in {run_dir}/sources/<writer>.md, then study.py prompts {args.run}")


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
GENERIC_REVIEW = (
    "Revise the draft below once. Read it as a careful editor would, improve what "
    "you judge weak, keep every fact, name, number, date, and source exactly as it "
    "is, and keep the author's emphasis. Change only what you can justify; leave the "
    "rest as written. Return ONLY the revised draft, no commentary.")

JUDGMENT_REVIEW = (
    "Revise the draft below once, using Pherkad's quick-mode judgment rules ONLY: "
    "read it against the writer's voice profile for the judgment-only tells "
    "(antithesis and triplet families, counter-X and authenticity constructions, "
    "structural artifacts, and whatever the profile bans that no regex expresses), "
    "and for the positive register where the surface expects it. Do NOT run any "
    "linter or mechanical check; this arm is the model's reading alone. Decide each "
    "finding (fix, intentional, literal, not applicable, quoted) and edit only the "
    "fix rows. Keep every fact, name, number, date, and source exactly as it is, and "
    "keep the author's emphasis. Return ONLY the revised draft, no commentary.")

MECHANICAL_REVIEW = (
    "Revise the draft below once, acting ONLY on the mechanical findings listed "
    "(from pherkad.py check, both engines). Each finding names a rule, a line, and "
    "the matched text; fix what the finding supports and nothing else. Do not apply "
    "any judgment beyond the listed findings. Keep every fact, name, number, date, "
    "and source exactly as it is, and keep the author's emphasis. Return ONLY the "
    "revised draft, no commentary.")

BOTH_REVIEW = (
    "Revise the draft below once, using BOTH the mechanical findings listed (from "
    "pherkad.py check) and Pherkad's quick-mode judgment rules against the writer's "
    "voice profile. Decide each finding (fix, intentional, literal, not applicable, "
    "quoted) and edit only the fix rows. Keep every fact, name, number, date, and "
    "source exactly as it is, and keep the author's emphasis. Return ONLY the revised "
    "draft, no commentary.")


def _mechanical_findings(text, surface):
    """pherkad.py check over the source, rendered as the feedback block for a prompt."""
    sys.path.insert(0, TOOLS)
    import pherkad  # noqa: WPS433
    cfg, _ = pherkad.load_layers(surface, None)
    findings, _ = pherkad.run_text(text, cfg)
    if not findings:
        return "(no mechanical findings)"
    return "\n".join(f"line {f['line']}: [{f['severity']}] {f['rule_id']}: {f['message']}  ->  {f['match']!r}"
                      for f in findings)


def prompts_revise(args, run_dir, manifest):
    n = 0
    missing = set()
    for it in manifest["items"]:
        src_abs = os.path.join(run_dir, it["source"])
        source = _read(src_abs).strip() if os.path.exists(src_abs) else ""
        if not source:
            missing.add(it["target"])
            continue
        draft_abs = os.path.join(run_dir, it["draft"])
        if it["arm"] == "untouched":
            _write(draft_abs, source + "\n")
            it["model"] = "none (untouched)"
            continue
        profile_txt = _read(os.path.join(WRITERS, it["profile"], "profile.md"))
        head = {"generic": GENERIC_REVIEW, "judgment": JUDGMENT_REVIEW,
                "mechanical": MECHANICAL_REVIEW, "both": BOTH_REVIEW}[it["arm"]]
        parts = [head, "", f"Surface: {it['surface']}", ""]
        if it["arm"] in ("mechanical", "both"):
            parts += ["=== MECHANICAL FINDINGS ===", _mechanical_findings(source, it["surface"]), ""]
        if it["arm"] in ("judgment", "both"):
            parts += ["=== VOICE PROFILE ===", profile_txt, ""]
        parts += ["=== DRAFT ===", source, ""]
        prompt = "\n".join(parts)
        _write(os.path.join(run_dir, "prompts", it["blind_id"] + ".txt"), prompt)
        it["prompt_sha256"] = _sha(prompt)
        if args.model:
            it["model"] = args.model
        n += 1
    with open(os.path.join(run_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    for w in sorted(missing):
        print(f"no source draft for {w}: put it in {run_dir}/sources/{w}.md")
    print(f"wrote {n} revision prompts to {run_dir}/prompts/ (untouched arms copied from the source)")
    print("run every prompt with the SAME editing model and the same one-pass budget, save each\n"
          f"output to {run_dir}/drafts/<blind_id>.md, then: study.py sheet {args.run}")
    if not args.model:
        print("record the model with: study.py prompts <run> --model <name> (re-running is safe)")


def prompts(args):
    run_dir = os.path.join(RUNS, args.run)
    manifest = _load_manifest(args.run)
    if manifest.get("task") == "revise":
        return prompts_revise(args, run_dir, manifest)
    if manifest.get("task") == "detect":
        import detect
        return detect.prompts(args, run_dir, manifest)
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
        it["prompt_sha256"] = _sha(prompt)
        if args.model:
            it["model"] = args.model
        n += 1
    with open(os.path.join(run_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    print(f"wrote {n} authoring prompts to {run_dir}/prompts/")
    print("run each through Pherkad authoring, save the output to the matching\n"
          f"{run_dir}/drafts/<blind_id>.md, then: study.py sheet {args.run}")


# ---------------------------------------------------------------------------
def sheet(args):
    run_dir = os.path.join(RUNS, args.run)
    manifest = _load_manifest(args.run)
    if manifest.get("task") == "detect":
        import detect
        return detect.sheet(args, run_dir, manifest)
    rng = random.Random(str(manifest["seed"]) + "-sheet")

    # group items by target writer; shuffle within each so condition order leaks nothing
    by_writer = {}
    for it in manifest["items"]:
        by_writer.setdefault(it["target"], []).append(it)
    for w in by_writer:
        rng.shuffle(by_writer[w])

    revise = manifest.get("task") == "revise"
    lines = [f"# Blind rating sheet: run {manifest['run']} (brief {manifest['brief']}"
             + (", revision task" if revise else "") + ")", ""]
    if revise:
        lines += ["Each candidate is a revision of the same starting draft (one of them is the draft",
                  "untouched). Rate each 1 to 5 for how much it sounds like the named writer. Then",
                  "flag fidelity (F if it invents facts, over-claims certainty, or caricatures the",
                  "writer), count the edits that helped (useful_edits) and the edits that were",
                  "unnecessary or harmful (unnecessary_edits), and note the minutes you spent.",
                  "Do NOT open manifest.json until you have rated everything.", ""]
    elif args.format == "rating":
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
            row = {"blind_id": it["blind_id"], "writer": w, "candidate": letter,
                   "rating": "", "fidelity_flag": "", "forced_choice_pick": ""}
            if revise:
                row.update({"useful_edits": "", "unnecessary_edits": "", "minutes": ""})
            rows.append(row)

    _write(os.path.join(run_dir, "rating-sheet.md"), "\n".join(lines))
    csv_path = os.path.join(run_dir, "ratings.csv")
    fields = ["blind_id", "writer", "candidate", "rating", "fidelity_flag", "forced_choice_pick"]
    if revise:
        fields += ["useful_edits", "unnecessary_edits", "minutes"]
    with open(csv_path, "w", newline="") as fh:
        wtr = csv.DictWriter(fh, fieldnames=fields)
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
def _read_ratings(rows):
    """Parse ratings.csv rows into ``(ratings, picks)``.

    ``ratings`` maps blind_id to ``(rating, fidelity_flag)``. ``picks`` maps
    writer to the list of blind_ids chosen in forced-choice mode. A pick is the
    candidate LETTER written in ``forced_choice_pick`` on any one of that
    writer's rows, and it resolves to the row whose ``candidate`` is that
    letter, not to the row it was typed on. (An earlier version scored the row
    the letter sat on, so entering ``b`` on row ``a`` counted as picking ``a``.)
    A letter that names no candidate, or two rows for one writer naming
    different letters, stops the run: a silent guess would look like a result.
    """
    ratings, picks = {}, {}
    by_writer = {}
    for row in rows:
        bid = row["blind_id"]
        writer = row["writer"]
        letter = (row.get("candidate") or "").strip().lower()
        by_writer.setdefault(writer, {})[letter] = bid
        val = (row.get("rating") or "").strip()
        if val:
            try:
                num = float(val)
            except ValueError:
                sys.exit(f"ratings.csv: rating {val!r} on {bid} is not a number")
            if not 1 <= num <= 5:
                sys.exit(f"ratings.csv: rating {val!r} on {bid} is outside 1 to 5")
            ratings[bid] = (num, (row.get("fidelity_flag") or "").strip().upper())
            extras = {}
            for k in ("useful_edits", "unnecessary_edits", "minutes"):
                v = (row.get(k) or "").strip()
                if v:
                    try:
                        extras[k] = float(v)
                    except ValueError:
                        sys.exit(f"ratings.csv: {k} {v!r} on {bid} is not a number")
            if extras:
                ratings[bid] = ratings[bid] + (extras,)
    chosen = {}
    for row in rows:
        pick = (row.get("forced_choice_pick") or "").strip().lower()
        if not pick:
            continue
        writer = row["writer"]
        if pick not in by_writer[writer]:
            sys.exit(f"ratings.csv: forced_choice_pick {pick!r} for {writer} names no candidate "
                     f"(have {', '.join(sorted(by_writer[writer]))})")
        if writer in chosen and chosen[writer] != pick:
            sys.exit(f"ratings.csv: {writer} has two different forced-choice picks "
                     f"({chosen[writer]!r} and {pick!r}); keep one")
        chosen[writer] = pick
    for writer, pick in chosen.items():
        picks.setdefault(writer, []).append(by_writer[writer][pick])
    return ratings, picks


def score(args):
    run_dir = os.path.join(RUNS, args.run)
    manifest = _load_manifest(args.run)
    key = {it["blind_id"]: it for it in manifest["items"]}
    if manifest.get("task") == "detect":
        import detect
        return detect.score(run_dir, manifest)
    csv_path = os.path.join(run_dir, "ratings.csv")
    if not os.path.exists(csv_path):
        sys.exit("no ratings.csv; run sheet and fill it in first")

    with open(csv_path, newline="") as fh:
        ratings, picks = _read_ratings(list(csv.DictReader(fh)))

    if manifest.get("task") == "revise":
        return score_revise(run_dir, manifest, key, ratings)

    # rating mode: per-writer mean by condition, correct-profile lift
    per_writer = {}
    for bid, rec in ratings.items():
        val, flag = rec[0], rec[1]
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


def score_revise(run_dir, manifest, key, ratings):
    """Per writer and arm: mean rating, fidelity failures, useful and unnecessary
    edits, minutes; the primary outcome is each arm's rating minus the generic
    arm's on the same writer, with a flagged draft counting as a failure of its
    arm whatever its rating. Repeats give a range, not a point."""
    per = {}  # writer -> arm -> list of (rating, flag, extras)
    for bid, rec in ratings.items():
        it = key.get(bid)
        if not it:
            continue
        val, flag = rec[0], rec[1]
        extras = rec[2] if len(rec) > 2 else {}
        per.setdefault(it["target"], {}).setdefault(it["arm"], []).append((val, flag, extras, it.get("repeat", 1)))
    lines = [f"# Results: run {manifest['run']} (brief {manifest['brief']}, revision task)", "",
             f"Arms: {', '.join(manifest['arms'])}. Repeats: {manifest['repeats']}. Surface: {manifest['surface']}.",
             "A flagged draft (F) is scored 1 whatever its rating, and the primary outcome, an arm's mean",
             "minus the generic arm's, is computed over every draft with that penalty in, so an arm that",
             "invents facts cannot look good on its clean runs. The unflagged mean is shown beside it.", ""]
    pooled = {}
    for w in sorted(per):
        arms = per[w]
        lines.append(f"## {w}")
        lines.append("")
        lines.append("| arm | n | rating (unflagged) | flagged | penalised mean | useful edits | unnecessary edits | minutes | vs generic |")
        lines.append("|---|---|---|---|---|---|---|---|---|")

        def penalised(xs):
            vals = [1.0 if f == "F" else v for v, f, _, _ in xs]
            return sum(vals) / len(vals) if vals else None

        gen_mean = penalised(arms.get("generic", []))
        for arm in manifest["arms"]:
            xs = arms.get(arm, [])
            if not xs:
                lines.append(f"| {arm} | 0 | | | | | | | not rated |")
                continue
            ok = [v for v, f, _, _ in xs if f != "F"]
            flagged = sum(1 for _, f, _, _ in xs if f == "F")
            mean = sum(ok) / len(ok) if ok else None
            pen = penalised(xs)
            def avg(k):
                vals = [e[k] for _, _, e, _ in xs if k in e]
                return f"{sum(vals)/len(vals):.1f}" if vals else ""
            rng_s = f" ({min(ok):.0f} to {max(ok):.0f})" if len(ok) > 1 else ""
            vs = ""
            if pen is not None and gen_mean is not None and arm != "generic":
                d = pen - gen_mean
                vs = f"{d:+.2f}"
                pooled.setdefault(arm, []).append(d)
            elif arm == "generic":
                vs = "control"
            lines.append(f"| {arm} | {len(xs)} | {'' if mean is None else f'{mean:.2f}'}{rng_s} | {flagged}/{len(xs)} | "
                         f"{'' if pen is None else f'{pen:.2f}'} | "
                         f"{avg('useful_edits')} | {avg('unnecessary_edits')} | {avg('minutes')} | {vs} |")
        lines.append("")
    if pooled:
        lines.append("## Pooled: each arm against the generic self-review, across writers")
        lines.append("")
        for arm, ds in pooled.items():
            lines.append(f"- **{arm}**: mean {sum(ds)/len(ds):+.2f} over {len(ds)} writer(s), "
                         f"range {min(ds):+.2f} to {max(ds):+.2f}")
        lines.append("")
    lines += ["## Reading it",
              "- An arm at or below generic has not earned its cost: another editing pass does as well.",
              "- A high unflagged mean beside a low penalised mean is an arm that writes well when it does not invent;",
              "  the penalised number is the one that counts.",
              "- An arm above generic with fidelity intact and few unnecessary edits is the claim, per writer.",
              "- A spread across repeats is instability; report it, do not average it away.",
              "- One rater on a few writers is a pilot. The writer is the unit; see docs/blind-eval.md."]
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
    s.add_argument("run"); s.add_argument("--brief", default="", help="required for author and revise")
    s.add_argument("--writers", required=True)
    s.add_argument("--task", choices=["author", "revise", "detect"], default="author")
    s.add_argument("--conditions", default=None,
                   help="author: correct,wrong,none (default); detect: correct,wrong,shuffled,none,linter (default)")
    s.add_argument("--anchor", action="store_true")
    s.add_argument("--arms", default=",".join(ARMS), help="revision task: the arms to run (generic is required)")
    s.add_argument("--repeats", type=int, default=1, help="revision task: runs per arm per writer")
    s.add_argument("--surface", default="post", help="revision task: the surface the mechanical arm checks under")
    s.add_argument("--seed", type=int, default=1); s.set_defaults(fn=plan)
    s = sub.add_parser("prompts"); s.add_argument("run")
    s.add_argument("--model", help="record the model that will run these prompts")
    s.set_defaults(fn=prompts)
    s = sub.add_parser("sheet"); s.add_argument("run")
    s.add_argument("--format", choices=["rating", "forcedchoice"], default="rating")
    s.set_defaults(fn=sheet)
    s = sub.add_parser("score"); s.add_argument("run"); s.set_defaults(fn=score)
    args = ap.parse_args(argv)
    _ensure(DATA, WRITERS, BRIEFS, RUNS)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
