#!/usr/bin/env python3
"""fingerprint.py: the measured voice profile.

Numbers first. The fingerprint is computed from the author's own samples
(samples.py, provenance `hand` and, at lower weight, `captured`), per surface
and pooled, and every feature keeps quoted evidence with the sample id it came
from. A text is then compared to the fingerprint feature by feature, each
deviation measured in the author's own units (standard deviations across
200-word chunks of his samples), so the check reports what is unlike him and
quotes it, and the harness can score whether that separates his prose from
flattened prose and from other writers.

Features (per chunk, then mean and sd across chunks):
  sentences      mean, sd, quartiles, share under 8 words, share over 35, short-after-long rate
  paragraphs     sentences per paragraph, one-sentence share, short-closer share
  openers        first-word classes (first person, conjunction, article, subordinator, number)
  punctuation    commas, colons, semicolons, parentheses, quotes, dashes per sentence;
                 contractions and questions per 1,000 words
  constructions  contrast frames, candour announcements, pointers, hedges, intensifiers,
                 initial And/But/So, passive-shaped phrases, per 1,000 words
  function words rates per 1,000 words for the 150 commonest English function words
                 (Burrows's Delta over these is the classic authorship distance)
  vocabulary     mean word length, type-token ratio on the chunk, top first words

Usage:
  fingerprint.py build --samples DIR --out fingerprint.json [--provenance hand,captured] [--surface S]
  fingerprint.py build-reference DIR_OR_FILES --out reference.json [--name flattened]
  fingerprint.py compare FILE --fingerprint F [--reference R] [--surface S] [--format text|json] [--threshold 2.0]
  fingerprint.py show fingerprint.json
  fingerprint.py prose fingerprint.json [--surface email] [--reference R] [--out Voice_Profile.measured.md]

Stdlib only.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mdmask  # noqa: E402

VERSION_PATH = os.path.join(HERE, "..", "VERSION")
CHUNK_WORDS = 200
MIN_CHUNKS = 3

SENT_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])")
WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")

FUNCTION_WORDS = (
    "the of and a to in is you that it he was for on are as with his they i at be this have from or one had by "
    "word but not what all were we when your can said there use an each which she do how their if will up other "
    "about out many then them these so some her would make like him into time has look two more write go see "
    "number no way could people my than first been who oil its now find long down day did get come made may part "
    "over new sound take only little work know place year live me back give most very after thing our just name "
    "good sentence man think say great where help through much before line right too mean old any same tell boy "
    "follow came want show also around form three small set put end does another well large must big even such "
    "because turn here why ask went men read need land different home us move try kind hand picture again change "
    "off play spell air away animal house point page letter mother answer found study still learn should"
).split()
FUNCTION_WORDS = tuple(dict.fromkeys(FUNCTION_WORDS))[:150]

FIRST_PERSON = {"i", "i'm", "i've", "i'd", "i'll", "my", "we", "we're", "we've", "our", "me"}
CONJUNCTION = {"and", "but", "so", "or", "yet", "nor"}
ARTICLE = {"the", "a", "an"}
SUBORDINATOR = {"if", "when", "because", "although", "though", "while", "since", "after", "before", "unless", "until", "whether", "where", "as", "once"}

CONSTRUCTIONS = {
    "contrast_frame": re.compile(r"\bnot\s+(?:\w+\s+){0,6}\bbut\b|,\s*not\s+(?:a|an|the|only|merely|just|because|to)\b|\brather than\b", re.I),
    "candour": re.compile(r"\b(?:the\s+)?honest(?:ly)?\b|\bto be (?:clear|fair|frank|candid)\b|\bfrankly\b|\blet me be\b", re.I),
    "pointer": re.compile(r"\b(?:that|this|here) is (?:the|what) (?:part|thing|point|detail|bit)\b", re.I),
    "hedge": re.compile(r"\b(?:perhaps|maybe|somewhat|arguably|possibly|probably|i think|i suspect|it seems|sort of|kind of)\b", re.I),
    "intensifier": re.compile(r"\b(?:very|really|extremely|incredibly|truly|deeply|highly|absolutely)\b", re.I),
    "passive": re.compile(r"\b(?:is|are|was|were|been|being|be)\s+(?:\w+ly\s+)?\w+(?:ed|en)\b(?:\s+by\b)?", re.I),
    "initial_conjunction": re.compile(r"(?:^|(?<=[.!?]\s))(?:And|But|So)\b"),
    "contraction": re.compile(r"\b\w+(?:n't|'re|'ve|'ll|'d|'m)\b|\b(?:it's|that's|there's|what's|he's|she's|who's|let's)\b", re.I),
}
PUNCT = {
    "comma": ",", "colon": ":", "semicolon": ";", "paren": "(", "quote": "\"", "dash": "—",
}
DASHES = re.compile(r"—|–|(?<=\w) - (?=\w)|(?<=\w)--(?=\w)")


def _tool_version() -> str:
    try:
        with open(VERSION_PATH) as fh:
            return fh.read().strip()
    except OSError:
        return "unknown"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- text to units ------------------------------------------------------------
def prose_paragraphs(text: str) -> list[str]:
    """Prose paragraphs of a Markdown text: code, blockquotes, headings, and
    list markers removed; a list item counts as its own paragraph."""
    masked = mdmask.mask(text, kinds=("code", "blockquote"))
    paras, cur = [], []
    for line in masked.split("\n"):
        s = line.strip()
        if not s or mdmask.heading_text(line) is not None or set(s) <= {"-", "*", "_", "|", " "}:
            if cur:
                paras.append(" ".join(cur))
                cur = []
            continue
        if mdmask.is_list_item(line):
            if cur:
                paras.append(" ".join(cur))
                cur = []
            s = re.sub(r"^(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?", "", s)
        s = re.sub(r"\*\*|__|(?<!\w)[*_](?!\s)|(?<!\s)[*_](?!\w)", "", s)   # emphasis marks
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)                     # links
        s = " ".join(mdmask.strip_inline_code(s).split())
        cur.append(s)
    if cur:
        paras.append(" ".join(cur))
    return [p for p in paras if len(p.split()) >= 1]


def sentences(par: str) -> list[str]:
    return [p.strip() for p in SENT_SPLIT.split(par) if p.strip()]


def words(text: str) -> list[str]:
    return [w.lower() for w in WORD.findall(text)]


# --- features -----------------------------------------------------------------
def features(paras: list[str]) -> dict:
    """Scalar features of a run of paragraphs, and the evidence sentences behind them."""
    sents = [s for p in paras for s in sentences(p)]
    if not sents:
        return {}
    lens = [len(s.split()) for s in sents]
    n = len(sents)
    ws = [w for s in sents for w in words(s)]
    nw = max(1, len(ws))
    per_k = 1000.0 / nw
    f, ev = {}, {}

    # sentences
    f["sent_mean"] = statistics.fmean(lens)
    f["sent_sd"] = statistics.pstdev(lens) if n > 1 else 0.0
    q = statistics.quantiles(lens, n=4) if n >= 2 else [lens[0]] * 3
    f["sent_q1"], f["sent_median"], f["sent_q3"] = q[0], q[1], q[2]
    f["sent_short_share"] = sum(1 for x in lens if x < 8) / n
    f["sent_long_share"] = sum(1 for x in lens if x > 35) / n
    f["short_after_long"] = (sum(1 for a, b in zip(lens, lens[1:]) if a > 20 and b < 8) / max(1, n - 1))
    ev["sent_long_share"] = [max(sents, key=lambda s: len(s.split()))]
    real_short = [s for s in sents if 3 <= len(s.split()) < 8 and re.search(r"[A-Za-z]{2}", s)]
    ev["sent_short_share"] = [min(real_short, key=lambda s: len(s.split()))] if real_short else []

    # paragraphs
    counts = [len(sentences(p)) for p in paras]
    f["para_sents"] = statistics.fmean(counts)
    f["para_one_sentence_share"] = sum(1 for c in counts if c == 1) / len(counts)
    closers = []
    for p in paras:
        ss = sentences(p)
        if len(ss) >= 2:
            closers.append(len(ss[-1].split()) / max(1, statistics.fmean(len(x.split()) for x in ss[:-1])))
    f["para_short_closer_share"] = (sum(1 for c in closers if c < 0.5) / len(closers)) if closers else 0.0

    # openers
    firsts = [(words(s) or [""])[0] for s in sents]
    f["open_first_person"] = sum(1 for w in firsts if w in FIRST_PERSON) / n
    f["open_conjunction"] = sum(1 for w in firsts if w in CONJUNCTION) / n
    f["open_article"] = sum(1 for w in firsts if w in ARTICLE) / n
    f["open_subordinator"] = sum(1 for w in firsts if w in SUBORDINATOR) / n
    f["open_number"] = sum(1 for s in sents if re.match(r"^\W*\d", s)) / n
    top = {}
    for w in firsts:
        top[w] = top.get(w, 0) + 1
    f["_first_words"] = sorted(top.items(), key=lambda kv: -kv[1])[:20]

    # punctuation
    joined = " ".join(sents)
    for name, ch in PUNCT.items():
        if name == "dash":
            cnt = len(DASHES.findall(joined))
        else:
            cnt = joined.count(ch)
        f[f"punct_{name}"] = cnt / n
        if cnt:
            ev[f"punct_{name}"] = [s for s in sents if (DASHES.search(s) if name == "dash" else ch in s)][:3]
    f["question_rate"] = sum(1 for s in sents if s.endswith("?")) * per_k
    if f["question_rate"]:
        ev["question_rate"] = [s for s in sents if s.endswith("?")][:3]

    # constructions
    for name, rx in CONSTRUCTIONS.items():
        hits = [s for s in sents if rx.search(s)]
        f[f"con_{name}"] = sum(len(rx.findall(s)) for s in sents) * per_k
        if hits:
            ev[f"con_{name}"] = hits[:3]

    # function words
    counts_fw = {w: 0 for w in FUNCTION_WORDS}
    for w in ws:
        if w in counts_fw:
            counts_fw[w] += 1
    for w, c in counts_fw.items():
        f[f"fw_{w}"] = c * per_k

    # vocabulary
    f["word_len"] = statistics.fmean(len(w) for w in ws) if ws else 0.0
    f["type_token"] = len(set(ws)) / nw
    f["_words"] = nw
    f["_sentences"] = n
    return {"f": f, "ev": ev}


def chunks(paras: list[str], size: int = CHUNK_WORDS) -> list[list[str]]:
    """Runs of whole paragraphs of about `size` words; a paragraph is never split."""
    out, cur, cw = [], [], 0
    for p in paras:
        cur.append(p)
        cw += len(p.split())
        if cw >= size:
            out.append(cur)
            cur, cw = [], 0
    if cur and (cw >= size * 0.4 or not out):
        out.append(cur)
    elif cur:
        out[-1].extend(cur)
    return out


SCALAR_GROUPS = ("sent_", "short_after", "para_", "open_", "punct_", "question", "con_", "fw_", "word_len", "type_token")


def _scalar_keys(f: dict) -> list[str]:
    return [k for k in f if not k.startswith("_")]


# --- build --------------------------------------------------------------------
def load_samples(samples_dir: str, provenance: tuple[str, ...], surface: str | None, exclude: tuple[str, ...] = ()) -> list[dict]:
    import samples as smp
    m = smp.load(samples_dir)
    out = []
    for s in m["samples"]:
        if s["provenance"] not in provenance:
            continue
        if surface and s["surface"] != surface:
            continue
        if s["id"] in exclude:
            continue  # held out for a test; the fingerprint must not have seen it
        with open(os.path.join(samples_dir, s["file"]), encoding="utf-8") as fh:
            s = dict(s, text=fh.read())
        out.append(s)
    return out


def _profile_from(sample_list: list[dict]) -> dict | None:
    """Mean and sd of every scalar feature across chunks of these samples,
    with evidence tagged by sample id. Small samples are pooled into chunks
    in manifest order so short pieces still count."""
    paras_by_sample = [(s["id"], prose_paragraphs(s["text"])) for s in sample_list]
    tagged = [(sid, p) for sid, ps in paras_by_sample for p in ps]
    runs = chunks([p for _, p in tagged])
    if len(runs) < MIN_CHUNKS:
        return None
    # map chunks back to sample ids for evidence: a quoted sentence is credited
    # to the sample whose paragraph holds it
    idx = 0
    per_chunk = []
    for run in runs:
        owners = tagged[idx:idx + len(run)]
        idx += len(run)
        fe = features(run)
        if fe:
            per_chunk.append((owners, fe))
    keys = _scalar_keys(per_chunk[0][1]["f"])
    stats = {}
    for k in keys:
        vals = [fe["f"][k] for _, fe in per_chunk if k in fe["f"]]
        stats[k] = {"mean": statistics.fmean(vals), "sd": statistics.pstdev(vals) if len(vals) > 1 else 0.0}
    evidence = {}
    for owners, fe in per_chunk:
        for k, sents in fe["ev"].items():
            slot = evidence.setdefault(k, [])
            for s in sents:
                if len(slot) < 5 and s not in [x["quote"] for x in slot]:
                    sid = next((o for o, p in owners if s in p), owners[0][0])
                    slot.append({"quote": s[:240], "samples": [sid]})
    firsts = {}
    for _, fe in per_chunk:
        for w, c in fe["f"]["_first_words"]:
            firsts[w] = firsts.get(w, 0) + c
    nsent = sum(fe["f"]["_sentences"] for _, fe in per_chunk)
    return {"chunks": len(per_chunk), "words": sum(fe["f"]["_words"] for _, fe in per_chunk),
            "sentences": nsent, "features": stats, "evidence": evidence,
            "first_words": [[w, round(c / nsent, 4)] for w, c in sorted(firsts.items(), key=lambda kv: -kv[1])[:20]]}


def build(samples_dir: str, provenance=("hand", "captured"), surface=None, exclude=()) -> dict:
    sample_list = load_samples(samples_dir, tuple(provenance), surface, tuple(exclude))
    if not sample_list:
        sys.exit("fingerprint: no samples match (check --samples, --provenance, --surface)")
    fp = {"tool": "pherkad-fingerprint", "version": _tool_version(), "built": datetime.date.today().isoformat(),
          "chunk_words": CHUNK_WORDS, "provenance": list(provenance), "excluded": list(exclude),
          "samples": [{"id": s["id"], "sha256": s["sha256"], "provenance": s["provenance"], "surface": s["surface"], "words": s["words"]} for s in sample_list],
          "surfaces": {}, "pooled": None}
    by_surface = {}
    for s in sample_list:
        by_surface.setdefault(s["surface"], []).append(s)
    for surf, lst in sorted(by_surface.items()):
        prof = _profile_from(lst)
        if prof:
            fp["surfaces"][surf] = prof
    pooled = _profile_from(sample_list)
    if pooled is None:
        sys.exit(f"fingerprint: fewer than {MIN_CHUNKS} chunks of {CHUNK_WORDS} words; add samples")
    fp["pooled"] = pooled
    return fp


# --- reference and discriminant ----------------------------------------------
# A fingerprint alone says how far a text sits from the author's mean, and a
# generic text sits near everyone's mean, so distance cannot tell the author
# from a flattening (the first mail test: flattenings were closer on 15 of 16).
# Against a reference profile of what the author is NOT (flattenings, or other
# writers in the register) the question becomes which of the two a text is
# nearer to, feature by feature, on the features where the two differ. That is
# a linear discriminant with equal variance; on held-out mail it put the author
# above his flattening 16 of 16 times.
def build_reference(paths: list[str], name: str = "reference") -> dict:
    """A profile of a reference corpus from loose Markdown files (flattenings,
    impostors): chunked like the author's samples, same features."""
    paras = []
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as fh:
            paras.extend(prose_paragraphs(fh.read()))
    runs = chunks(paras)
    per = [features(r)["f"] for r in runs if features(r)]
    if len(per) < MIN_CHUNKS:
        sys.exit(f"fingerprint: the reference needs at least {MIN_CHUNKS} chunks of {CHUNK_WORDS} words")
    keys = _scalar_keys(per[0])
    stats = {k: {"mean": statistics.fmean(x[k] for x in per), "sd": statistics.pstdev([x[k] for x in per])} for k in keys}
    return {"tool": "pherkad-fingerprint-reference", "version": _tool_version(), "built": datetime.date.today().isoformat(),
            "name": name, "files": [os.path.basename(p) for p in paths], "chunks": len(per),
            "words": sum(x["_words"] for x in per), "features": stats}


def discriminant(f: dict, author: dict, reference: dict, min_effect: float = 0.5) -> dict:
    """Mean per-feature evidence that the text is the author's rather than the
    reference's, over the features whose means differ by at least `min_effect`
    pooled standard deviations. Positive means nearer the author."""
    total, used, top = 0.0, 0, []
    for k, a in author.items():
        r = reference.get(k)
        if r is None or k not in f:
            continue
        ps = ((a["sd"] ** 2 + r["sd"] ** 2) / 2) ** 0.5
        ps = max(ps, 0.1 * (abs(a["mean"]) + abs(r["mean"])) + 1e-6)
        if abs(a["mean"] - r["mean"]) / ps < min_effect:
            continue
        used += 1
        term = ((f[k] - r["mean"]) ** 2 - (f[k] - a["mean"]) ** 2) / (2 * ps * ps)
        total += term
        top.append((term, k))
    top.sort()
    return {"score": round(total / used, 3) if used else 0.0, "features_used": used,
            "for_author": [k for t, k in top[-5:][::-1] if t > 0],
            "for_reference": [k for t, k in top[:5] if t < 0]}


# --- compare ------------------------------------------------------------------
def compare(text: str, fp: dict, surface: str | None = None, threshold: float = 2.0, reference: dict | None = None) -> dict:
    """Deviation of a text from the fingerprint, feature by feature, in the
    author's own standard-deviation units; the overall distance is Burrows's
    Delta over the function words plus the mean absolute z of the shape
    features, reported separately."""
    prof = fp["surfaces"].get(surface) if surface else None
    basis = surface if prof else "pooled"
    prof = prof or fp["pooled"]
    paras = prose_paragraphs(text)
    fe = features(paras)
    if not fe:
        return {"basis": basis, "error": "no prose to measure"}
    f = fe["f"]
    devs = []
    for k, st in prof["features"].items():
        if k not in f:
            continue
        sd = st["sd"]
        if sd <= 1e-9:
            # a feature with no variance across the author's chunks: any nonzero difference is a deviation
            z = 0.0 if abs(f[k] - st["mean"]) < 1e-9 else (3.0 if f[k] > st["mean"] else -3.0)
        else:
            z = (f[k] - st["mean"]) / sd
        devs.append({"feature": k, "value": round(f[k], 4), "author_mean": round(st["mean"], 4),
                     "author_sd": round(sd, 4), "z": round(z, 2)})
    fw = [d for d in devs if d["feature"].startswith("fw_")]
    shape = [d for d in devs if not d["feature"].startswith("fw_")]
    delta = statistics.fmean(abs(d["z"]) for d in fw) if fw else 0.0
    shape_dist = statistics.fmean(abs(d["z"]) for d in shape) if shape else 0.0
    flagged = sorted((d for d in shape if abs(d["z"]) >= threshold), key=lambda d: -abs(d["z"]))
    for d in flagged:
        k = d["feature"]
        d["quote"] = (fe["ev"].get(k) or [""])[0][:240]
        d["author_quote"] = (prof["evidence"].get(k) or [{"quote": ""}])[0]["quote"]
    fw_flagged = sorted((d for d in fw if abs(d["z"]) >= threshold), key=lambda d: -abs(d["z"]))[:10]
    out = {"basis": basis, "words": f["_words"], "sentences": f["_sentences"],
           "delta": round(delta, 3), "shape_distance": round(shape_dist, 3), "threshold": threshold,
           "flagged": flagged, "function_words_flagged": fw_flagged, "n_features": len(devs)}
    if reference:
        out["discriminant"] = dict(discriminant(f, prof["features"], reference["features"]), reference=reference.get("name", "reference"))
    return out


def render(result: dict, path: str = "") -> str:
    if "error" in result:
        return f"fingerprint: {result['error']}"
    lines = [f"fingerprint: {path or 'text'}: {result['words']} words, {result['sentences']} sentences, "
             f"basis {result['basis']}; Delta {result['delta']} (function words), shape distance {result['shape_distance']} "
             f"(mean |z| over {result['n_features'] - len([1 for _ in ()])} features)"]
    if result.get("discriminant"):
        d = result["discriminant"]
        side = "nearer the author" if d["score"] > 0 else "nearer the reference"
        lines.append(f"  discriminant {d['score']:+.2f} against {d['reference']} over {d['features_used']} separating features: {side}"
                     + (f"; for the author: {', '.join(d['for_author'])}" if d["for_author"] else "")
                     + (f"; for the reference: {', '.join(d['for_reference'])}" if d["for_reference"] else ""))
    if not result["flagged"] and not result["function_words_flagged"]:
        lines.append(f"  nothing past {result['threshold']} of the author's standard deviations")
    for d in result["flagged"]:
        direction = "more" if d["z"] > 0 else "less"
        lines.append(f"  {d['feature']:28} z {d['z']:+5.1f}  {direction} than the author ({d['value']} against {d['author_mean']} ± {d['author_sd']})")
        if d["quote"]:
            lines.append(f"      text:   \"{d['quote'][:120]}\"")
        if d["author_quote"]:
            lines.append(f"      author: \"{d['author_quote'][:120]}\"")
    if result["function_words_flagged"]:
        lines.append("  function words: " + ", ".join(f"{d['feature'][3:]} {d['z']:+.1f}" for d in result["function_words_flagged"]))
    return "\n".join(lines)


# --- prose from numbers (roadmap item 23) -------------------------------------
# The prose profile is a view of the fingerprint. Every claim carries the
# number it rests on and, where the feature keeps evidence, one quoted
# sentence with its sample id. Nothing here is asserted that was not counted.
_FW_NAMES = {"i": "I"}


def _q(prof: dict, key: str) -> str:
    ev = (prof.get("evidence") or {}).get(key) or []
    if not ev:
        return ""
    e = ev[0]
    return f' For example, "{e["quote"].strip()}" ({e["samples"][0]}).'


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def _rate(prof: dict, key: str) -> tuple[float, float]:
    st = prof["features"].get(key) or {"mean": 0.0, "sd": 0.0}
    return st["mean"], st["sd"]


def prose_surface(name: str, prof: dict, reference: dict | None = None) -> str:
    f = prof["features"]
    m = lambda k: _rate(prof, k)[0]  # noqa: E731
    sd = lambda k: _rate(prof, k)[1]  # noqa: E731
    out = [f"## {name}", "",
           f"Measured on {prof['words']:,} words in {prof['chunks']} chunks of about {CHUNK_WORDS} words, "
           f"{prof['sentences']:,} sentences. Every figure below is a mean over those chunks, with the spread in the author's own units.", ""]
    # sentences
    out += ["### Sentences", "",
            f"- A sentence runs {m('sent_mean'):.1f} words on average (spread {sd('sent_mean'):.1f}); the median is {m('sent_median'):.1f} words, "
            f"the middle half sits between {m('sent_q1'):.0f} and {m('sent_q3'):.0f}.",
            f"- {_pct(m('sent_short_share'))} of sentences are under eight words.{_q(prof, 'sent_short_share')}",
            f"- {_pct(m('sent_long_share'))} run past 35 words.{_q(prof, 'sent_long_share')}",
            f"- A short sentence follows a long one {_pct(m('short_after_long'))} of the time.", ""]
    out += ["### Paragraphs", "",
            f"- {m('para_sents'):.1f} sentences per paragraph on average; {_pct(m('para_one_sentence_share'))} of paragraphs are one sentence.",
            f"- {_pct(m('para_short_closer_share'))} of multi-sentence paragraphs end on a sentence under half the length of the ones before it.", ""]
    fw = prof.get("first_words") or []
    fw_txt = ", ".join(f"{_FW_NAMES.get(w, w)} ({_pct(r)})" for w, r in fw[:8] if w)
    out += ["### Openers", "",
            f"- Sentences open in the first person {_pct(m('open_first_person'))} of the time, with an article {_pct(m('open_article'))}, "
            f"with a subordinator (if, when, because) {_pct(m('open_subordinator'))}, with a conjunction {_pct(m('open_conjunction'))}, "
            f"with a number {_pct(m('open_number'))}.",
            f"- Most frequent first words: {fw_txt}.", ""]
    out += ["### Punctuation", "",
            f"- Per sentence: {m('punct_comma'):.2f} commas, {m('punct_colon'):.2f} colons, {m('punct_semicolon'):.2f} semicolons, "
            f"{m('punct_paren'):.2f} parentheses, {m('punct_quote'):.2f} quotation marks, {m('punct_dash'):.3f} dashes."
            + _q(prof, 'punct_colon'),
            f"- Contractions: {m('con_contraction'):.1f} per 1,000 words.{_q(prof, 'con_contraction')}",
            f"- Questions: {m('question_rate'):.1f} per 1,000 words.{_q(prof, 'question_rate')}", ""]
    cons = [("con_contrast_frame", "contrast frames (not X but Y; X, not Y; rather than)"), ("con_hedge", "hedges (perhaps, maybe, I think)"),
            ("con_intensifier", "intensifiers (very, really, extremely)"), ("con_initial_conjunction", "sentences opening on And, But, or So"),
            ("con_passive", "passive-shaped verb phrases"), ("con_candour", "candour announcements (honestly, to be fair)"),
            ("con_pointer", "pointers (that is the part that)")]
    out += ["### Constructions, per 1,000 words", ""]
    absent = []
    for k, label in cons:
        if m(k) == 0 and sd(k) == 0:
            absent.append(label)
            continue
        out.append(f"- {label}: {m(k):.1f} (spread {sd(k):.1f}).{_q(prof, k)}")
    if absent:
        out.append(f"- Never in {prof['chunks']} chunks: {'; '.join(absent)}.")
    out.append("")
    # function words: the signature, against the reference if given
    fwk = [k for k in f if k.startswith("fw_")]
    if reference and reference.get("features"):
        rows = []
        for k in fwk:
            a = f[k]["mean"]
            r = reference["features"].get(k, {"mean": 0.0, "sd": 0.0})
            ps = ((f[k]["sd"] ** 2 + r["sd"] ** 2) / 2) ** 0.5 or 1e-9
            rows.append(((a - r["mean"]) / ps, k[3:], a, r["mean"]))
        rows.sort()
        more = [x for x in rows[::-1] if x[0] > 0.5][:8]
        less = [x for x in rows if x[0] < -0.5][:8]
        out += [f"### Function words, against {reference.get('name', 'the reference')}", ""]
        if more:
            out.append("- Used more than the reference: " + ", ".join(f"{w} ({a:.1f} against {r:.1f} per 1,000)" for _, w, a, r in more) + ".")
        if less:
            out.append("- Used less than the reference: " + ", ".join(f"{w} ({a:.1f} against {r:.1f} per 1,000)" for _, w, a, r in less) + ".")
        out.append("")
    else:
        top = sorted(fwk, key=lambda k: -f[k]["mean"])[:12]
        out += ["### Function words", "",
                "- Most frequent, per 1,000 words: " + ", ".join(f"{k[3:]} ({f[k]['mean']:.0f})" for k in top) + ".", ""]
    out += ["### Vocabulary", "",
            f"- Mean word length {m('word_len'):.2f} letters; type-token ratio {m('type_token'):.2f} on a {CHUNK_WORDS}-word chunk.", ""]
    return "\n".join(out)


def prose(fp: dict, surfaces: list[str] | None = None, reference: dict | None = None) -> str:
    names = surfaces or list(fp["surfaces"]) or ["pooled"]
    parts = ["# Measured voice profile", "",
             f"Rendered from `fingerprint.py` {fp['version']}, built {fp['built']} from {len(fp['samples'])} samples "
             f"({fp['pooled']['words']:,} words; provenance {', '.join(fp['provenance'])}). A view of the numbers: every claim "
             "below is a count over the author's own samples, and a quoted sentence is one the count was made on. "
             "Nothing here was written from an impression.", ""]
    for name in names:
        prof = fp["surfaces"].get(name) if name != "pooled" else fp["pooled"]
        if not prof:
            sys.exit(f"fingerprint: no surface '{name}' in the fingerprint (have {', '.join(fp['surfaces'])})")
        parts.append(prose_surface(name, prof, reference))
    return "\n".join(parts)


def cmd_prose(args) -> int:
    with open(args.fingerprint, encoding="utf-8") as fh:
        fp = json.load(fh)
    ref = None
    if args.reference:
        with open(args.reference, encoding="utf-8") as fh:
            ref = json.load(fh)
    text = prose(fp, [s.strip() for s in args.surface.split(",")] if args.surface else None, ref)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"fingerprint: prose profile written to {args.out}")
    else:
        print(text)
    return 0


# --- CLI ----------------------------------------------------------------------
def cmd_build(args) -> int:
    fp = build(args.samples, tuple(p.strip() for p in args.provenance.split(",") if p.strip()), args.surface,
               tuple(x.strip() for x in (args.exclude or "").split(",") if x.strip()))
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(fp, fh, indent=1, sort_keys=True)
        fh.write("\n")
    p = fp["pooled"]
    print(f"fingerprint: built from {len(fp['samples'])} sample(s), {p['words']} words in {p['chunks']} chunk(s) of "
          f"about {CHUNK_WORDS}; surfaces with their own profile: {', '.join(fp['surfaces']) or 'none'}; "
          f"{len(p['features'])} features -> {args.out}")
    return 0


def cmd_build_reference(args) -> int:
    paths = []
    for p in args.paths:
        if os.path.isdir(p):
            paths.extend(sorted(os.path.join(p, f) for f in os.listdir(p) if f.endswith(".md")))
        else:
            paths.append(p)
    ref = build_reference(paths, args.name)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(ref, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"fingerprint: reference '{args.name}' from {len(paths)} file(s), {ref['words']} words in {ref['chunks']} chunk(s) -> {args.out}")
    return 0


def cmd_compare(args) -> int:
    with open(args.fingerprint, encoding="utf-8") as fh:
        fp = json.load(fh)
    ref = None
    if args.reference:
        with open(args.reference, encoding="utf-8") as fh:
            ref = json.load(fh)
    text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8", errors="replace").read()
    res = compare(text, fp, args.surface, args.threshold, ref)
    if args.format == "json":
        print(json.dumps(res, indent=2))
    else:
        print(render(res, args.file))
    return 0


def cmd_show(args) -> int:
    with open(args.fingerprint, encoding="utf-8") as fh:
        fp = json.load(fh)
    p = fp["pooled"]
    print(f"fingerprint {fp['version']} built {fp['built']} from {len(fp['samples'])} sample(s), {p['words']} words, {p['chunks']} chunks")
    keyf = ("sent_mean", "sent_sd", "sent_median", "sent_short_share", "sent_long_share", "para_sents", "para_one_sentence_share",
            "open_first_person", "open_conjunction", "punct_comma", "punct_colon", "punct_semicolon", "punct_dash",
            "question_rate", "con_contraction", "con_contrast_frame", "con_hedge", "con_intensifier", "con_initial_conjunction",
            "word_len", "type_token")
    for k in keyf:
        st = p["features"].get(k)
        if st:
            print(f"  {k:26} {st['mean']:8.3f} ± {st['sd']:.3f}")
    print("  first words: " + ", ".join(f"{w} {r:.2f}" for w, r in p["first_words"][:12]))
    for k in ("con_contrast_frame", "con_hedge", "punct_dash", "sent_long_share"):
        for e in p["evidence"].get(k, [])[:1]:
            print(f"  {k}: \"{e['quote'][:110]}\"  [{', '.join(e['samples'])}]")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="the measured voice profile")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--samples", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--provenance", default="hand,captured")
    b.add_argument("--surface")
    b.add_argument("--exclude", help="comma-separated sample ids to hold out (a test set the profile never sees)")
    b.set_defaults(fn=cmd_build)
    r = sub.add_parser("build-reference", help="a profile of what the author is not: flattenings, or other writers")
    r.add_argument("paths", nargs="+", help="Markdown files or directories of them")
    r.add_argument("--out", required=True)
    r.add_argument("--name", default="reference")
    r.set_defaults(fn=cmd_build_reference)
    c = sub.add_parser("compare")
    c.add_argument("file")
    c.add_argument("--fingerprint", required=True)
    c.add_argument("--reference", help="a build-reference profile; adds the discriminant score")
    c.add_argument("--surface")
    c.add_argument("--format", choices=("text", "json"), default="text")
    c.add_argument("--threshold", type=float, default=2.0)
    c.set_defaults(fn=cmd_compare)
    s = sub.add_parser("show")
    s.add_argument("fingerprint")
    s.set_defaults(fn=cmd_show)
    pr = sub.add_parser("prose", help="render the prose profile from the numbers, every claim with its count and a quoted sample")
    pr.add_argument("fingerprint")
    pr.add_argument("--surface", help="comma-separated surfaces to render (default: all)")
    pr.add_argument("--reference", help="a build-reference profile; adds the function-word contrast")
    pr.add_argument("--out")
    pr.set_defaults(fn=cmd_prose)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
