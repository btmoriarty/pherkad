#!/usr/bin/env python3
"""deckcheck: the voice check for slide decks, run by each deck builder as its last step.

Decks are built by scripts that write .pptx or HTML, so no Write hook sees their
text. This reads the built deck (slide text and speaker notes, through decks.py),
runs pherkad on each slide and each slide's notes under the ``slides`` surface,
prints the findings by slide, and exits 1 on an error-level finding, so the build
fails. With a gate config it also writes a snapshot of every slide's text and notes
(the deck as sent, which the nightly capture diffs against a deck Brian edits or
comments on and hands back) and logs the check, so decks count on the daily page.

    deckcheck.py DECK [DECK ...]               # check; exit 1 on an error
    deckcheck.py --config gate.json DECK       # check, snapshot, log
    deckcheck.py --no-snapshot --json DECK     # findings as JSON

The config comes from --config or PHERKAD_GATE_CONFIG; without one the deck is
checked and nothing is written. A builder calls it like this:

    node:    execFileSync("python3", [DECKCHECK, out], {stdio: "inherit"})
    python:  subprocess.run(["python3", DECKCHECK, out], check=True)

Stdlib only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import decks  # noqa: E402


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_dir(cfg: dict, deck: str) -> str:
    key = hashlib.sha1(os.path.abspath(deck).encode()).hexdigest()[:16]
    return os.path.join(cfg["log_dir"], "snapshots", key)


def write_snapshot(cfg: dict, deck: str, doc: dict, when: float | None = None) -> str:
    when = when or time.time()
    d = snapshot_dir(cfg, deck)
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, time.strftime("%Y%m%dT%H%M%S", time.localtime(when)) + ".json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"path": os.path.abspath(deck), "sha256": sha256(deck), "t": when,
                   "format": doc["format"], "revision": doc["revision"],
                   "slides": [{"n": s["n"], "text": s["text"], "notes": s["notes"]} for s in doc["slides"]]},
                  fh, ensure_ascii=False)
    return out


def snapshots(cfg: dict, deck: str) -> list[dict]:
    """Every snapshot of this deck path, oldest first."""
    d = snapshot_dir(cfg, deck)
    if not os.path.isdir(d):
        return []
    out = []
    for n in sorted(os.listdir(d)):
        if n.endswith(".json"):
            with open(os.path.join(d, n), encoding="utf-8") as fh:
                out.append(json.load(fh))
    return out


def all_snapshots(cfg: dict) -> list[dict]:
    root = os.path.join(cfg["log_dir"], "snapshots")
    out = []
    if os.path.isdir(root):
        for k in sorted(os.listdir(root)):
            d = os.path.join(root, k)
            for n in sorted(os.listdir(d)) if os.path.isdir(d) else []:
                if n.endswith(".json"):
                    with open(os.path.join(d, n), encoding="utf-8") as fh:
                        out.append(json.load(fh))
    return out


def check(deck: str, surface: str = "slides") -> tuple[dict, list[dict]]:
    import pherkad
    doc = decks.read(deck)
    cfg, _ = pherkad.load_layers(surface, None, cwd=False)
    findings = []
    for s in doc["slides"]:
        for part in ("text", "notes"):
            if not s[part].strip():
                continue
            fs, _ = pherkad.run_text(s[part], cfg, structure=False)
            for f in fs:
                if f.get("engine") == "voice":
                    findings.append({"slide": s["n"], "part": part, "rule_id": f.get("rule_id"),
                                     "severity": f.get("severity"), "match": f.get("match"),
                                     "message": f.get("message")})
    return doc, findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="voice check for slide decks")
    ap.add_argument("decks", nargs="+")
    ap.add_argument("--config")
    ap.add_argument("--surface", default="slides")
    ap.add_argument("--no-snapshot", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    gcfg = None
    cfg_path = args.config or os.environ.get("PHERKAD_GATE_CONFIG")
    if cfg_path:
        import gate
        try:
            gcfg = gate.load_config(cfg_path)
        except (OSError, ValueError, RuntimeError) as exc:
            sys.stderr.write(f"deckcheck: config not read ({exc}); checking without a snapshot\n")
    worst = 0
    report = []
    for deck in args.decks:
        try:
            doc, findings = check(deck, args.surface)
        except (OSError, ValueError, KeyError) as exc:
            sys.stderr.write(f"deckcheck: cannot read {deck}: {exc}\n")
            worst = max(worst, 2)
            continue
        errors = [f for f in findings if f["severity"] == "error"]
        if gcfg and not args.no_snapshot:
            try:
                import gate
                write_snapshot(gcfg, deck, doc)
                gate.append_log(gcfg, {"type": "deck", "t": time.time(), "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                       "tool": "deckcheck", "kind": "deck", "surface": args.surface,
                                       "target": os.path.abspath(deck), "slides": len(doc["slides"]),
                                       "verdict": "block" if errors else "pass", "findings": findings,
                                       "session": os.environ.get("CLAUDE_CODE_SESSION_ID")})
            except OSError as exc:
                sys.stderr.write(f"deckcheck: snapshot not written ({exc})\n")
        report.append({"deck": deck, "slides": len(doc["slides"]), "findings": findings})
        if not args.json:
            for f in findings:
                where = f"slide {f['slide']}" + (" notes" if f["part"] == "notes" else "")
                print(f"{deck}: {where} [{f['severity']}] {f['rule_id']}: {f['match']!r}")
            print(f"deckcheck: {len(errors)} error(s), {len(findings) - len(errors)} warning(s) "
                  f"across {len(doc['slides'])} slides of {os.path.basename(deck)}")
        if errors:
            worst = max(worst, 1)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return worst


if __name__ == "__main__":
    sys.exit(main())
