#!/usr/bin/env python3
"""author_pilot.py: does the authoring packet beat a bare prompt?

For each held-out piece of the author's own writing: a runner extracts the
facts as terse notes (no phrasing carried over), then two drafts are written
from the same notes with the same runner, one from a bare prompt and one from
the pherkad author packet (fingerprint built without the held-out pieces,
exemplars drawn from the other samples). Each draft is scored with the
fingerprint discriminant against the reference, the mechanical check, and
its distance from the real piece; a blind pairs sheet is written for the
author to say which of the two reads as his. The score is the number the
packet has to earn: roadmap item 25 keeps the feature only if the packet's
draft sits measurably nearer the author than the bare prompt's.

    author_pilot.py RUN --holdout DIR --fingerprint F --reference R --samples DIR --surface email
                    --runner CMD [--profile-dir D] [--rounds 1] [--limit N]
    author_pilot.py RUN --score            # after pairs.csv is filled in

Writes eval/data/runs/RUN/{notes,bare,packet}/<id>.md, scores.json, pairs-sheet.md, pairs.csv, results.md.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "skills", "pherkad", "tools")
sys.path.insert(0, TOOLS)
import author as au  # noqa: E402
import fingerprint as fpm  # noqa: E402
import pherkad  # noqa: E402

RUNS = os.path.join(HERE, "data", "runs")

NOTES_PROMPT = """Read the message below and list the facts it conveys as terse bullet points: who it is to, what it asks or tells,
every concrete detail (names, dates, numbers, places), and the requested action if any. Use as few words as possible per
bullet and do not reuse the message's sentences or phrasing; nouns and numbers only where you can. Reply with the bullets only.

=== MESSAGE ===
{text}
"""
BARE_PROMPT = """Write a {surface} from these notes. Include every fact and add none. Reply with the finished text only.

=== NOTES ===
{notes}
"""


def _write(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text.rstrip() + "\n")


def generate(args) -> int:
    run_dir = os.path.join(RUNS, args.run)
    fp = json.load(open(args.fingerprint))
    ref = json.load(open(args.reference))
    cfg, info = pherkad.load_layers(args.surface, None, None)
    held = sorted(f for f in os.listdir(args.holdout) if f.endswith(".md"))
    if args.limit:
        held = held[:args.limit]
    held_ids = {f[:-3] for f in held}
    samples = [s for s in fpm.load_samples(args.samples, ("hand",), None) if s["id"] not in held_ids]
    archetype = ""
    if args.profile_dir and os.path.exists(os.path.join(args.profile_dir, "Voice_Profile.md")):
        archetype = open(os.path.join(args.profile_dir, "Voice_Profile.md"), encoding="utf-8").read()
    scores = json.load(open(os.path.join(run_dir, "scores.json"))) if os.path.exists(os.path.join(run_dir, "scores.json")) else {}
    for f in held:
        sid = f[:-3]
        real = open(os.path.join(args.holdout, f), encoding="utf-8").read()
        notes_p = os.path.join(run_dir, "notes", f)
        if not os.path.exists(notes_p):
            notes, err = au._run_one(args.runner, NOTES_PROMPT.format(text=real.strip()), args.timeout)
            if notes is None:
                print(f"{sid}: notes failed: {err}")
                continue
            _write(notes_p, notes)
        notes = open(notes_p, encoding="utf-8").read()
        bare_p = os.path.join(run_dir, "bare", f)
        if not os.path.exists(bare_p):
            bare, err = au._run_one(args.runner, BARE_PROMPT.format(surface=args.surface, notes=notes.strip()), args.timeout)
            if bare is None:
                print(f"{sid}: bare failed: {err}")
                continue
            _write(bare_p, bare)
        pack_p = os.path.join(run_dir, "packet", f)
        if not os.path.exists(pack_p):
            packet = au.build_packet(notes, args.surface, fp, ref, samples, args.exemplars, archetype,
                                     {"speaker": info["speaker"], "guidance": info["guidance"]} if info else None)
            res = au.author_loop(packet, args.runner, args.rounds, fp, args.surface, ref, cfg, args.timeout)
            if "error" in res:
                print(f"{sid}: packet failed: {res['error']}")
                continue
            _write(pack_p, res["draft"])
            _write(pack_p + ".author.json", json.dumps({"exemplars": [e["id"] for e in packet["exemplars"]],
                                                         "history": [{k: v for k, v in h.items() if k != "draft"} for h in res["history"]]}, indent=2))
        row = {}
        for arm, path in (("real", os.path.join(args.holdout, f)), ("bare", bare_p), ("packet", pack_p)):
            text = open(path, encoding="utf-8").read()
            sc = au.score(text, fp, args.surface, ref, cfg)
            row[arm] = {"words": sc["words"], "errors": len(sc["errors"]), "warnings": len(sc["warnings"]),
                        "discriminant": sc["discriminant"], "shape_distance": sc["shape_distance"]}
        scores[sid] = row
        print(f"{sid}: real {row['real']['discriminant']:+.2f}  bare {row['bare']['discriminant']:+.2f}  packet {row['packet']['discriminant']:+.2f}"
              f"  (errors bare {row['bare']['errors']}, packet {row['packet']['errors']})")
        _write(os.path.join(run_dir, "scores.json"), json.dumps(scores, indent=2))
    # blind pairs sheet
    rng = random.Random(args.seed)
    lines = [f"# Authoring pairs: run {args.run}", "",
             "Each pair is two drafts written from the same notes. Mark in pairs.csv which one reads as the author (A or B),",
             "or 'same'. Do not open scores.json or the arm folders until every pair is marked.", ""]
    rows = []
    for sid in sorted(scores):
        a, b = "bare", "packet"
        if rng.random() < 0.5:
            a, b = b, a
        ta = open(os.path.join(run_dir, a, sid + ".md"), encoding="utf-8").read().strip()
        tb = open(os.path.join(run_dir, b, sid + ".md"), encoding="utf-8").read().strip()
        lines += [f"## {sid}", "", "### A", "", ta, "", "### B", "", tb, ""]
        rows.append({"id": sid, "pick": "", "_a": a, "_b": b})
    _write(os.path.join(run_dir, "pairs-sheet.md"), "\n".join(lines))
    with open(os.path.join(run_dir, "pairs.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "pick"])
        w.writeheader()
        for r in rows:
            w.writerow({"id": r["id"], "pick": ""})
    _write(os.path.join(run_dir, "pairs-key.json"), json.dumps({r["id"]: {"A": r["_a"], "B": r["_b"]} for r in rows}, indent=2))
    print(f"wrote {run_dir}/pairs-sheet.md and pairs.csv ({len(rows)} pairs); the key is in pairs-key.json, do not open it before marking")
    return report(args.run, scores, None)


def report(run: str, scores: dict, picks: dict | None) -> int:
    run_dir = os.path.join(RUNS, run)
    ids = sorted(scores)
    d = {arm: [scores[i][arm]["discriminant"] for i in ids if scores[i][arm]["discriminant"] is not None] for arm in ("real", "bare", "packet")}
    wins = sum(1 for i in ids if (scores[i]["packet"]["discriminant"] or 0) > (scores[i]["bare"]["discriminant"] or 0))
    errs = {arm: sum(scores[i][arm]["errors"] for i in ids) for arm in ("real", "bare", "packet")}
    warns = {arm: sum(scores[i][arm]["warnings"] for i in ids) for arm in ("real", "bare", "packet")}
    lines = [f"# Results: authoring pilot {run}", "",
             f"{len(ids)} pieces. Discriminant against the reference (positive is nearer the author):", "",
             "| arm | mean discriminant | errors | warnings |", "|---|---|---|---|"]
    for arm in ("real", "bare", "packet"):
        lines.append(f"| {arm} | {statistics.fmean(d[arm]):+.2f} | {errs[arm]} | {warns[arm]} |")
    lines += ["", f"Packet above bare on {wins} of {len(ids)} pieces.", ""]
    if picks:
        key = json.load(open(os.path.join(run_dir, "pairs-key.json")))
        chose_packet = sum(1 for i, p in picks.items() if p in ("A", "B") and key[i][p] == "packet")
        decided = sum(1 for p in picks.values() if p in ("A", "B"))
        lines += [f"Author's blind reading: packet chosen on {chose_packet} of {decided} decided pairs "
                  f"({sum(1 for p in picks.values() if p == 'same')} marked same).", ""]
    lines += ["Reading: the packet earns its cost when its drafts sit nearer the author than the bare prompt's on the measured score",
              "and the author picks them blind; a measured win the author does not see is a win for the score, not for the voice."]
    _write(os.path.join(run_dir, "results.md"), "\n".join(lines))
    print("\n".join(lines))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="the authoring packet against a bare prompt")
    ap.add_argument("run")
    ap.add_argument("--holdout")
    ap.add_argument("--fingerprint")
    ap.add_argument("--reference")
    ap.add_argument("--samples")
    ap.add_argument("--surface", default="email")
    ap.add_argument("--runner")
    ap.add_argument("--profile-dir")
    ap.add_argument("--exemplars", type=int, default=3)
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--score", action="store_true", help="score the filled pairs.csv")
    args = ap.parse_args(argv)
    if args.score:
        run_dir = os.path.join(RUNS, args.run)
        scores = json.load(open(os.path.join(run_dir, "scores.json")))
        picks = {r["id"]: r["pick"].strip().upper() if r["pick"].strip().upper() in ("A", "B") else r["pick"].strip().lower()
                 for r in csv.DictReader(open(os.path.join(run_dir, "pairs.csv")))}
        return report(args.run, scores, picks)
    for need in ("holdout", "fingerprint", "reference", "samples", "runner"):
        if not getattr(args, need):
            sys.exit(f"--{need} is required to generate")
    return generate(args)


if __name__ == "__main__":
    sys.exit(main())
