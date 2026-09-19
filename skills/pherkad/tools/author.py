#!/usr/bin/env python3
"""author.py: authoring on demand from the measured profile (roadmap item 25).

Builds the packet a model writes from: the surface, the constraints the
fingerprint's numbers impose (written as instructions), the archetype from the
prose profile, the nearest exemplars from the author's own samples, and the
notes to write from. A runner writes; the draft is scored with the fingerprint
discriminant and the mechanical check; a bounded loop sends the findings and
the deviating features back for revision and keeps the best draft.

Nothing here rewrites the author's prose, and the packet is only worth its
cost if the authoring experiment shows it produces text measurably closer to
the author than a bare prompt does.

    pherkad.py author NOTES --surface S --fingerprint F [--reference R] [--samples DIR]
                     [--exemplars 3] [--runner CMD] [--rounds 2] [--out FILE] [--format prompt|json]

Stdlib only.
"""
from __future__ import annotations
import datetime
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fingerprint as fpm  # noqa: E402

STOP = set("the a an and or of to in on for with at by from as is are was were be been it this that these those i you he she we they "
           "my your our his her their its me him them us not no yes if so but than then there here what which who when where how "
           "will would can could should may might do does did have has had just also very more most".split())


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z][a-z'’-]{2,}", text.lower()) if w not in STOP]


def nearest_exemplars(notes: str, samples: list[dict], k: int = 3, lo: int = 80, hi: int = 450) -> list[dict]:
    """The k samples nearest the notes by content-word overlap (cosine on
    counts), among samples of a workable length; ties broken by length."""
    q = {}
    for w in _words(notes):
        q[w] = q.get(w, 0) + 1
    qn = math.sqrt(sum(v * v for v in q.values())) or 1.0
    scored = []
    for s in samples:
        n = s["words"]
        if not lo <= n <= hi:
            continue
        d = {}
        for w in _words(s["text"]):
            d[w] = d.get(w, 0) + 1
        dn = math.sqrt(sum(v * v for v in d.values())) or 1.0
        cos = sum(q[w] * d.get(w, 0) for w in q) / (qn * dn)
        scored.append((cos, -abs(n - 220), s))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [dict(s, similarity=round(c, 3)) for c, _, s in scored[:k]]


def constraints(prof: dict, reference: dict | None = None) -> list[str]:
    """The fingerprint's numbers as instructions a writer can follow."""
    f = prof["features"]
    m = lambda k: f[k]["mean"]  # noqa: E731
    sd = lambda k: f[k]["sd"]  # noqa: E731
    out = [f"Sentences average {m('sent_mean'):.0f} words (most between {max(3, m('sent_mean') - sd('sent_mean')):.0f} and "
           f"{m('sent_mean') + sd('sent_mean'):.0f}); the median is {m('sent_median'):.0f}. About {100 * m('sent_short_share'):.0f}% of "
           f"sentences are under eight words and {100 * m('sent_long_share'):.0f}% run past 35.",
           f"Paragraphs average {m('para_sents'):.1f} sentences; {100 * m('para_one_sentence_share'):.0f}% are a single sentence.",
           f"About {100 * m('open_first_person'):.0f}% of sentences open in the first person, {100 * m('open_subordinator'):.0f}% with if, when, or because, "
           f"{100 * m('open_conjunction'):.0f}% with and, but, or so."]
    firsts = [w for w, r in (prof.get("first_words") or [])[:6] if w and w not in ("hi", "brian")]
    if firsts:
        out.append("Common first words: " + ", ".join(firsts) + ".")
    punct = f"Per sentence: {m('punct_comma'):.1f} commas, {m('punct_colon'):.2f} colons, {m('punct_semicolon'):.2f} semicolons."
    if m("punct_dash") < 0.02:
        punct += " No dashes of any kind."
    if m("punct_semicolon") < 0.03:
        punct += " Semicolons are rare."
    out.append(punct)
    out.append(f"Contractions about {m('con_contraction'):.0f} per 1,000 words; questions about {m('question_rate'):.0f} per 1,000 words.")
    avoid = []
    for k, label in (("con_contrast_frame", "the contrast frame (not X but Y; X, not Y; rather than)"), ("con_candour", "announcements of candour (honestly, to be fair)"),
                     ("con_pointer", "pointers (that is the part that)"), ("con_intensifier", "intensifiers (very, really, extremely)"),
                     ("con_hedge", "hedges (perhaps, maybe, I think)")):
        if m(k) < 1.0:
            avoid.append(label)
    if avoid:
        out.append("Rare or absent, so do not reach for them: " + "; ".join(avoid) + ".")
    if reference and reference.get("features"):
        rows = []
        for k in f:
            if not k.startswith("fw_"):
                continue
            r = reference["features"].get(k, {"mean": 0.0, "sd": 0.0})
            ps = ((f[k]["sd"] ** 2 + r["sd"] ** 2) / 2) ** 0.5 or 1e-9
            rows.append(((f[k]["mean"] - r["mean"]) / ps, k[3:]))
        rows.sort()
        more = [w for d, w in rows[::-1] if d > 0.6][:8]
        less = [w for d, w in rows if d < -0.6][:8]
        if more:
            out.append("Words the author uses more than polished prose does: " + ", ".join(more) + ".")
        if less:
            out.append("Words the author uses less than polished prose does: " + ", ".join(less) + ".")
    return out


def build_packet(notes: str, surface: str, fp: dict, reference: dict | None, samples: list[dict], k: int,
                 archetype: str, surface_info: dict | None) -> dict:
    prof = fp["surfaces"].get(surface) or fp["pooled"]
    basis = surface if surface in fp["surfaces"] else "pooled"
    ex = nearest_exemplars(notes, [s for s in samples if s["surface"] == surface] or samples, k)
    return {"tool": "pherkad-author", "version": fpm._tool_version(), "generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "surface": surface, "basis": basis, "speaker": (surface_info or {}).get("speaker", "author"),
            "guidance": (surface_info or {}).get("guidance", ""),
            "fingerprint_samples": len(fp["samples"]), "constraints": constraints(prof, reference),
            "archetype": archetype.strip(), "exemplars": [{"id": e["id"], "words": e["words"], "similarity": e["similarity"], "text": e["text"].strip()} for e in ex],
            "notes": notes.strip()}


def render(packet: dict, feedback: str = "", previous: str = "") -> str:
    parts = [f"You are writing as the author, in the author's own voice, for the surface: {packet['surface']}.",
             "Write from the notes below and nothing else; do not add facts, and do not leave any fact out.",
             "Reply with the finished text only: no preamble, no title unless the surface needs one, no commentary."]
    if packet.get("guidance"):
        parts += ["", f"Surface guidance: {packet['guidance']}"]
    parts += ["", "=== HOW THE AUTHOR WRITES (measured on the author's own samples) ==="]
    parts += [f"- {c}" for c in packet["constraints"]]
    if packet.get("archetype"):
        parts += ["", "=== THE AUTHOR'S MOVES (from the prose profile) ===", packet["archetype"]]
    if packet["exemplars"]:
        parts += ["", "=== THE AUTHOR'S OWN WRITING, NEAREST IN SUBJECT (match the register, never the content) ==="]
        for e in packet["exemplars"]:
            parts += [f"--- {e['id']} ({e['words']} words) ---", e["text"], ""]
    parts += ["=== NOTES TO WRITE FROM ===", packet["notes"], ""]
    if previous:
        parts += ["=== YOUR PREVIOUS DRAFT ===", previous, "", "=== WHAT TO CHANGE ===", feedback,
                  "Revise the previous draft to address every point above; keep everything else as it was."]
    return "\n".join(parts).rstrip() + "\n"


def score(draft: str, fp: dict, surface: str, reference: dict | None, cfg: dict) -> dict:
    import pherkad
    findings, _ = pherkad.run_text(draft, cfg, structure=True, density=True)
    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]
    res = fpm.compare(draft, fp, surface, 2.0, reference)
    disc = (res.get("discriminant") or {}).get("score")
    return {"errors": errors, "warnings": warnings, "discriminant": disc, "shape_distance": res.get("shape_distance"),
            "flagged": res.get("flagged", []), "words": res.get("words", 0)}


def feedback_text(sc: dict) -> str:
    lines = []
    for f in sc["errors"] + sc["warnings"]:
        lines.append(f"- Remove or recast {f['match']!r}: {f['message']}")
    for d in sc["flagged"][:4]:
        more = "more" if d["z"] > 0 else "less"
        lines.append(f"- {d['feature']} is {more} than the author by {abs(d['z']):.1f} of the author's standard deviations "
                     f"(yours {d['value']}, the author's {d['author_mean']}); for example {d['quote']!r}")
    if sc.get("discriminant") is not None and sc["discriminant"] < 0:
        lines.append(f"- The draft reads nearer generic polished prose than the author (discriminant {sc['discriminant']:+.2f}); "
                     "shorten sentences toward the author's median, use the author's function words, drop what the author never uses.")
    return "\n".join(lines) if lines else "- Nothing mechanical to change; tighten toward the exemplars' register."


def _better(a: dict, b: dict) -> bool:
    """Is score a better than score b: no errors first, then the discriminant, then fewer warnings."""
    if b is None:
        return True
    if bool(a["errors"]) != bool(b["errors"]):
        return not a["errors"]
    da, db = a.get("discriminant") or 0.0, b.get("discriminant") or 0.0
    if abs(da - db) > 0.02:
        return da > db
    return len(a["warnings"]) < len(b["warnings"])


def _run_one(runner: str, prompt: str, timeout: int) -> tuple[str | None, str]:
    import shlex
    import subprocess
    try:
        proc = subprocess.run(shlex.split(runner), input=prompt, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f"runner timed out after {timeout}s"
    except OSError as exc:
        return None, f"runner could not start: {exc}"
    if proc.returncode != 0:
        return None, f"runner exit {proc.returncode}: {proc.stderr.strip()[:300]}"
    return proc.stdout.strip(), ""


def author_loop(packet: dict, runner: str, rounds: int, fp: dict, surface: str, reference: dict | None, cfg: dict, timeout: int = 600) -> dict:
    """Draft, score, revise up to `rounds` times; keep the best draft."""
    history = []
    best, best_sc = "", None
    prompt = render(packet)
    draft, err = _run_one(runner, prompt, timeout)
    if draft is None:
        return {"error": err, "history": history}
    for rnd in range(rounds + 1):
        sc = score(draft, fp, surface, reference, cfg)
        history.append({"round": rnd, "words": sc["words"], "errors": len(sc["errors"]), "warnings": len(sc["warnings"]),
                        "discriminant": sc["discriminant"], "shape_distance": sc["shape_distance"], "draft": draft})
        if _better(sc, best_sc):
            best, best_sc = draft, sc
        if rnd == rounds or (not sc["errors"] and not sc["warnings"] and not sc["flagged"] and (sc["discriminant"] is None or sc["discriminant"] > 0.15)):
            break
        prompt = render(packet, feedback_text(sc), draft)
        draft, err = _run_one(runner, prompt, timeout)
        if draft is None:
            history.append({"round": rnd + 1, "error": err})
            break
    return {"draft": best, "score": {k: (v if k not in ("errors", "warnings", "flagged") else len(v)) for k, v in best_sc.items()},
            "rounds": len(history) - 1, "history": history}
