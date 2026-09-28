#!/usr/bin/env python3
"""fingerprint.py: the measured voice profile.

Numbers first. The fingerprint is computed from the author's own samples
(samples.py, provenance `hand` and `captured`, weighted alike), per surface
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
  function words rates per 1,000 words for about 150 closed-class English words
  vocabulary     mean word length, moving-average type-token ratio over 50-word
                 windows (steady with length), top first words

A text is compared with the author's single-document pieces of the size
nearest its length. Each feature gives a prediction t; features fall into
families (sentence length, paragraphs, openers, punctuation, constructions,
vocabulary, function words), a family's statistic is its largest |t|, its
p-value is that statistic's rank among the author's own pieces (a conformal
test), and a family is flagged when it survives Benjamini-Hochberg at --fdr. With a reference,
a nearest-shrunken-centroid discriminant, chosen and calibrated by grouped
cross-validation, gives the log-odds that the text is the author's.

Usage:
  fingerprint.py build --samples DIR --out fingerprint.json [--provenance hand,captured] [--surface S]
  fingerprint.py build-reference DIR_OR_FILES --out reference.json [--name flattened]
  fingerprint.py compare FILE --fingerprint F [--reference R] [--surface S] [--format text|json] [--fdr 0.05]
  fingerprint.py show fingerprint.json
  fingerprint.py prose fingerprint.json [--surface email] [--reference R] [--out Voice_Profile.measured.md]

Stdlib only.
"""
from __future__ import annotations
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
import statefile  # noqa: E402

VERSION_PATH = os.path.join(HERE, "..", "VERSION")
CHUNK_WORDS = 200
MIN_CHUNKS = 5
# A feature's spread depends on how much text it is measured over, so the
# profile is kept at several chunk sizes and a text is compared at the size
# nearest its own length (I188). Under the smallest there is too little to measure.
SCALES = (100, 200, 400, 800)
MIN_COMPARE_WORDS = SCALES[0]
FDR = 0.05
MATTR_WINDOW = 50
MIN_REFERENCE_CHUNKS = 50

SENT_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])")
WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")

# Closed-class words only: determiners, pronouns, prepositions, conjunctions,
# auxiliaries and modals, and focusing particles. Content words and the
# intensifiers (counted by con_intensifier) stay out, so a rate here is how
# the author joins a sentence, not what the sentence is about (I191).
FUNCTION_WORDS = tuple(dict.fromkeys((
    "the a an this that these those my your his her its our their some any no every each either neither all both "
    "much many more most few less least several such what which whose another other "
    "i me we us you he him she it they them myself yourself himself herself itself ourselves themselves "
    "one who whom someone something anyone anything nothing everyone everything "
    "of in to for with on at by from about into over after before between through during without under around "
    "against among upon within along across behind beyond near off since until toward towards up down out "
    "and but or nor so yet if because although though while when where whether unless than as once whereas "
    "be is are was were been being am have has had having do does did "
    "will would shall should can could may might must "
    "not then there here how why also only just even still too again ever never"
).split()))

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
# Curly apostrophes and quotes count as their ASCII forms, or a mail client's
# "don’t" is no contraction and a “quote” no quote. The fold is one character
# for one, so the folded text splits at the same offsets as the original and
# the evidence still quotes the author's own characters.
FOLD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def fold(text: str) -> str:
    return text.translate(FOLD)


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


def _sentence_pairs(par: str) -> list[tuple[str, str]]:
    """Each sentence of a paragraph, folded and as written, split on the folded text."""
    folded, out, start = fold(par), [], 0
    for m in SENT_SPLIT.finditer(folded):
        out.append((folded[start:m.start()].strip(), par[start:m.start()].strip()))
        start = m.end()
    out.append((folded[start:].strip(), par[start:].strip()))
    return [(s, r) for s, r in out if s]


def words(text: str) -> list[str]:
    return [w.lower() for w in WORD.findall(text)]


def _mattr(ws: list[str], window: int = MATTR_WINDOW) -> float:
    """Moving-average type-token ratio: the mean share of distinct words in
    every window of `window` words. A plain ratio falls as a text grows."""
    if len(ws) <= window:
        return len(set(ws)) / max(1, len(ws))
    counts, total = {}, 0.0
    for w in ws[:window]:
        counts[w] = counts.get(w, 0) + 1
    total += len(counts)
    for i in range(window, len(ws)):
        old = ws[i - window]
        counts[old] -= 1
        if not counts[old]:
            del counts[old]
        counts[ws[i]] = counts.get(ws[i], 0) + 1
        total += len(counts)
    return total / ((len(ws) - window + 1) * window)


# --- features -----------------------------------------------------------------
def features(paras: list[str]) -> dict:
    """Scalar features of a run of paragraphs, and the evidence sentences behind them."""
    pairs = [sr for p in paras for sr in _sentence_pairs(p)]
    sents = [s for s, _ in pairs]
    as_written = dict(pairs)
    as_written.update((fold(p), p) for p in paras)
    paras = [fold(p) for p in paras]
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
    # a length statistic is quoted by the sentence whose length is nearest it, so
    # every flagged number carries a passage of the text it was measured on
    for k in ("sent_mean", "sent_q1", "sent_median", "sent_q3"):
        ev[k] = [min(sents, key=lambda s: abs(len(s.split()) - f[k]))]
    ev["sent_long_share"] = [max(sents, key=lambda s: len(s.split()))]
    real_short = [s for s in sents if 3 <= len(s.split()) < 8 and re.search(r"[A-Za-z]{2}", s)]
    ev["sent_short_share"] = [min(real_short, key=lambda s: len(s.split()))] if real_short else []
    ev["sent_sd"] = [max(sents, key=lambda s: len(s.split()))] + ([min(real_short, key=lambda s: len(s.split()))] if real_short else [])
    ev["short_after_long"] = [b for a, b in zip(sents, sents[1:]) if len(a.split()) > 20 and len(b.split()) < 8][:3]

    # paragraphs: quoted whole (a profile trims a quote to 240 characters)
    counts = [len(sentences(p)) for p in paras]
    f["para_sents"] = statistics.fmean(counts)
    f["para_one_sentence_share"] = sum(1 for c in counts if c == 1) / len(counts)
    ev["para_sents"] = [min(paras, key=lambda p: abs(len(sentences(p)) - f["para_sents"]))]
    ev["para_one_sentence_share"] = [p for p, c in zip(paras, counts) if c == 1][:3]
    closers, short_closers = [], []
    for p in paras:
        ss = sentences(p)
        if len(ss) >= 2:
            closers.append(len(ss[-1].split()) / max(1, statistics.fmean(len(x.split()) for x in ss[:-1])))
            if closers[-1] < 0.5:
                short_closers.append(ss[-1])
    f["para_short_closer_share"] = (sum(1 for c in closers if c < 0.5) / len(closers)) if closers else 0.0
    ev["para_short_closer_share"] = short_closers[:3]

    # openers
    firsts = [(words(s) or [""])[0] for s in sents]
    f["open_first_person"] = sum(1 for w in firsts if w in FIRST_PERSON) / n
    f["open_conjunction"] = sum(1 for w in firsts if w in CONJUNCTION) / n
    f["open_article"] = sum(1 for w in firsts if w in ARTICLE) / n
    f["open_subordinator"] = sum(1 for w in firsts if w in SUBORDINATOR) / n
    f["open_number"] = sum(1 for s in sents if re.match(r"^\W*\d", s)) / n
    for key, cls in (("open_first_person", FIRST_PERSON), ("open_conjunction", CONJUNCTION), ("open_article", ARTICLE),
                     ("open_subordinator", SUBORDINATOR)):
        ev[key] = [s for s, w in zip(sents, firsts) if w in cls][:3]
    ev["open_number"] = [s for s in sents if re.match(r"^\W*\d", s)][:3]
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
    sent_words = [set(words(s)) for s in sents]
    for w, c in counts_fw.items():
        f[f"fw_{w}"] = c * per_k
        if c:
            ev[f"fw_{w}"] = [s for s, sw in zip(sents, sent_words) if w in sw][:2]

    # vocabulary: quoted by the sentence whose own value is nearest the text's
    f["word_len"] = statistics.fmean(len(w) for w in ws) if ws else 0.0
    f["type_token"] = _mattr(ws)
    worded = [(s, words(s)) for s in sents if words(s)]
    if worded:
        ev["word_len"] = [min(worded, key=lambda sw: abs(statistics.fmean(len(w) for w in sw[1]) - f["word_len"]))[0]]
        ev["type_token"] = [min(worded, key=lambda sw: abs(_mattr(sw[1]) - f["type_token"]))[0]]
    ev = {k: v for k, v in ev.items() if v}
    f["_words"] = nw
    f["_sentences"] = n
    ev = {k: [as_written.get(s, s) for s in v] for k, v in ev.items()}
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
    stats = _stats([fe["f"] for _, fe in per_chunk])
    keys = sorted(stats)
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
            "first_words": [[w, round(c / nsent, 4)] for w, c in sorted(firsts.items(), key=lambda kv: -kv[1])[:20]],
            "scales": _scales(paras_by_sample), "vectors": _vectors(paras_by_sample, keys)}


def _vectors(by_doc: list[tuple[str, list[str]]], keys: list[str]) -> dict:
    """One feature vector per single-document piece of about CHUNK_WORDS words
    (any document of MIN_COMPARE_WORDS or more), grouped by document, for the
    discriminant's fit and its cross-validation."""
    groups, rows = [], []
    for doc, run in _doc_units(by_doc, CHUNK_WORDS, lo=MIN_COMPARE_WORDS):
        fe = features(run)
        if fe:
            groups.append(doc)
            rows.append([_sig4(fe["f"].get(k, 0.0)) for k in keys])
    return {"keys": keys, "groups": groups, "rows": rows}


def _sig4(x: float):
    """Four significant figures, stored as an int when whole: the per-chunk
    vectors are the bulk of a fingerprint file, and the fit needs no more."""
    v = float(f"{x:.4g}")
    return int(v) if v.is_integer() else v


def _stats(per: list[dict]) -> dict:
    """Mean and sample sd (n - 1) of every scalar feature over chunks."""
    out = {}
    for k in _scalar_keys(per[0]):
        vals = [f[k] for f in per if k in f]
        out[k] = {"mean": statistics.fmean(vals), "sd": statistics.stdev(vals) if len(vals) > 1 else 0.0}
    return out


def _doc_units(by_doc: list[tuple[str, list[str]]], size: int, lo: float | None = None) -> list[tuple[str, list[str]]]:
    """Pieces of about `size` words that never mix two documents: a document
    within a factor of 1.4 of the size is one piece, a longer one is cut into
    paragraph-whole runs of it, a shorter one (under `lo`) is left out. A
    compared text is one document, and chunks pooled across several short
    ones average away the variation between documents: on the author's own
    held-out mail, spreads from pooled chunks flagged a third of it (I188)."""
    lo = size / math.sqrt(2) if lo is None else lo
    hi = size * math.sqrt(2)
    out = []
    for doc, ps in by_doc:
        w = sum(len(p.split()) for p in ps)
        if not ps or w < lo:
            continue
        if w < hi:
            out.append((doc, ps))
        else:
            out.extend((doc, run) for run in chunks(ps, size))
    return out


def _scales(by_doc: list[tuple[str, list[str]]]) -> dict:
    """The profile at every size in SCALES that gives MIN_CHUNKS single-document
    pieces: the piece count, the mean words, sentences and paragraphs a piece
    holds (for the sd floors), each feature's mean and sd at that size, and
    the null: for each family, the sorted leave-one-out statistic of every
    piece, against which a compared text is ranked."""
    out = {}
    for size in SCALES:
        per = [(run, features(run)) for _, run in _doc_units(by_doc, size)]
        per = [(run, fe["f"]) for run, fe in per if fe]
        if len(per) < MIN_CHUNKS:
            continue
        sc = {"n": len(per), "words": statistics.fmean(f["_words"] for _, f in per),
              "sentences": statistics.fmean(f["_sentences"] for _, f in per),
              "paragraphs": statistics.fmean(len(run) for run, _ in per),
              "features": _stats([f for _, f in per])}
        sc["null"] = _null([f for _, f in per], sc)
        out[str(size)] = sc
    return out


def _t(x: float, mean: float, sd: float, floor: float, n: int) -> float:
    """A piece's prediction t against n others with this mean and sd."""
    return (x - mean) / (max(sd, floor) * math.sqrt(1.0 + 1.0 / n))


def _null(per: list[dict], sc: dict) -> dict:
    """For each family, every piece's statistic (its largest |t| over the
    family's features) against the other n - 1 pieces, sorted. A text's
    family p-value is its rank among these: a conformal test, exact whatever
    the features' skew or correlation, where a normal t over a skewed count
    like colons per sentence flagged 12% of the author's own mail (I189)."""
    n = len(per)
    keys = list(sc["features"])
    sums = {k: sum(f.get(k, 0.0) for f in per) for k in keys}
    sqs = {k: sum(f.get(k, 0.0) ** 2 for f in per) for k in keys}
    floors = {k: _sd_floor(k, sc) for k in keys}
    fams = {}
    for k in keys:
        fams.setdefault(family(k), []).append(k)
    null = {name: [] for name in fams}
    for f in per:
        for name, ks in fams.items():
            worst = 0.0
            for k in ks:
                x = f.get(k, 0.0)
                m = (sums[k] - x) / (n - 1)
                var = max(0.0, (sqs[k] - x * x - (n - 1) * m * m) / max(1, n - 2))
                worst = max(worst, abs(_t(x, m, math.sqrt(var), floors[k], n - 1)))
            null[name].append(round(worst, 3))
    return {name: sorted(v) for name, v in null.items()}


def _conformal_p(stat: float, null: list[float]) -> float:
    """(1 + the pieces at least this extreme) / (n + 1)."""
    import bisect
    return (1 + len(null) - bisect.bisect_left(null, round(stat, 3))) / (len(null) + 1)


def _grams(text: str, n: int) -> set:
    w = re.findall(r"[a-z0-9']+", fold(text).lower())
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def containment(a: str, b: str, n: int = 5) -> float:
    """The share of a's n-word runs that also occur in b."""
    ga = _grams(a, n)
    return len(ga & _grams(b, n)) / len(ga) if ga else 0.0


def shared_run(a: str, b: str, n: int = 8) -> str:
    """The first run of n words the two texts share, or ''."""
    common = _grams(a, n) & _grams(b, n)
    return min(common) if common else ""


NEAR_DUPLICATE = 0.2  # 5-word-run containment at which one text holds a real part of another


def near_duplicates(samples: list[dict], held_texts: list[str]) -> set:
    """Ids of samples that carry a real part of any held-out text, either way
    round: a reply quoting the held-out email, or the held-out email quoting it.
    Excluding by id alone let a same-thread near-copy through as training data
    and as a top exemplar (I159)."""
    out = set()
    for s in samples:
        for h in held_texts:
            if containment(s["text"], h) >= NEAR_DUPLICATE or containment(h, s["text"]) >= NEAR_DUPLICATE:
                out.add(s["id"])
                break
    return out


def _refuse(msg: str):
    sys.stderr.write(f"fingerprint: {msg}\n")
    raise SystemExit(2)


def build(samples_dir: str, provenance=("hand", "captured"), surface=None, exclude=(), allow_approved=False) -> dict:
    import samples as smp
    unknown = sorted(set(provenance) - set(smp.PROVENANCE))
    if unknown:
        _refuse(f"unknown provenance {', '.join(unknown)} (known: {', '.join(smp.PROVENANCE)})")
    if "approved" in provenance and not allow_approved:
        _refuse("approved samples are AI-assisted and are never built from; pass --allow-approved to build from them anyway")
    if exclude:
        # a mistyped id would hold nothing out and the test would score text the profile saw
        missing = sorted(set(exclude) - {s["id"] for s in smp.load(samples_dir)["samples"]})
        if missing:
            _refuse(f"--exclude names id(s) not in the manifest: {', '.join(missing)}")
    sample_list = load_samples(samples_dir, tuple(provenance), surface, tuple(exclude))
    near = set()
    if exclude:
        held = [s["text"] for s in load_samples(samples_dir, ("hand", "captured", "approved"), None) if s["id"] in set(exclude)]
        near = near_duplicates(sample_list, held)
        sample_list = [s for s in sample_list if s["id"] not in near]
    if not sample_list:
        sys.exit("fingerprint: no samples match (check --samples, --provenance, --surface)")
    fp = {"tool": "pherkad-fingerprint", "version": _tool_version(), "built": datetime.date.today().isoformat(),
          "chunk_words": CHUNK_WORDS, "provenance": list(provenance), "allow_approved": bool(allow_approved),
          "excluded": sorted(set(exclude)),
          "excluded_near_duplicates": sorted(near),
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
# nearer to. The first version, an unregularised equal-variance discriminant fit
# on 14 reference chunks, put the author above his flattening 16 of 16 times on
# held-out mail; it was neither cross-validated nor calibrated (I190), and the
# model below replaces it.
def build_reference(paths: list[str], name: str = "reference") -> dict:
    """A profile of a reference corpus from loose Markdown files (flattenings,
    impostors): chunked like the author's samples, same features."""
    by_file = []
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as fh:
            by_file.append((_stem(os.path.basename(p)), prose_paragraphs(fh.read())))
    per = [fe["f"] for fe in (features(run) for run in chunks([para for _, ps in by_file for para in ps])) if fe]
    if len(per) < MIN_CHUNKS:
        sys.exit(f"fingerprint: the reference needs at least {MIN_CHUNKS} chunks of {CHUNK_WORDS} words")
    stats = _stats(per)
    keys = sorted(stats)
    file_sha = {}
    for p in paths:
        with open(p, "rb") as fh:
            file_sha[os.path.basename(p)] = hashlib.sha256(fh.read()).hexdigest()
    return {"tool": "pherkad-fingerprint-reference", "version": _tool_version(), "built": datetime.date.today().isoformat(),
            "name": name, "files": [os.path.basename(p) for p in paths], "file_sha256": file_sha,
            "stems": sorted({_stem(os.path.basename(p)) for p in paths}), "chunks": len(per),
            "words": sum(x["_words"] for x in per), "features": stats,
            "vectors": _vectors(by_file, keys)}


def _stem(name: str) -> str:
    """The piece a file comes from: email-1f93cb21.2.md and email-1f93cb21.md are both email-1f93cb21."""
    base = name[:-3] if name.endswith(".md") else name
    return re.sub(r"\.\d+$", "", base)


def leakage(case_paths: list[str], fp: dict | None = None, reference: dict | None = None) -> list[str]:
    """Why a measured verdict on these cases would be scored against itself (I158):
    a case that is, or is a flattening of, a file the reference was built from,
    and a case whose text is one of the fingerprint's own samples. Empty when clean."""
    problems = []
    ref_stems = set((reference or {}).get("stems") or {_stem(f) for f in (reference or {}).get("files", [])})
    ref_sha = set(((reference or {}).get("file_sha256") or {}).values())
    fp_sha = {s.get("sha256") for s in (fp or {}).get("samples", []) if isinstance(s, dict)}
    fp_ids = {s.get("id") for s in (fp or {}).get("samples", []) if isinstance(s, dict)}
    for p in case_paths:
        name = os.path.basename(p)
        stem = _stem(name)
        with open(p, "rb") as fh:
            raw = fh.read()
        sha = hashlib.sha256(raw).hexdigest()
        if stem in ref_stems or sha in ref_sha:
            problems.append(f"{name}: the reference was built from this piece or a flattening of it")
        if stem in fp_ids or sha in fp_sha or hashlib.sha256(raw.decode("utf-8", "replace").rstrip().encode() + b"\n").hexdigest() in fp_sha:
            problems.append(f"{name}: this piece is one of the fingerprint's own samples")
    return problems


def _bh(ps: list[float], q: float) -> tuple[set, float]:
    """Benjamini-Hochberg at level q: the indices rejected, and the p cutoff."""
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    m, cut, k = len(ps), 0.0, 0
    for rank, i in enumerate(order, 1):
        if ps[i] <= rank / m * q:
            k, cut = rank, ps[i]
    return set(order[:k]), cut


FAMILIES = (("sentence length", ("sent_", "short_after")), ("paragraphs", ("para_",)), ("openers", ("open_",)),
            ("punctuation", ("punct_", "question")), ("constructions", ("con_",)), ("vocabulary", ("word_len", "type_token")),
            ("function words", ("fw_",)))


def family(key: str) -> str:
    """The family a feature belongs to: correlated features of one property are
    tested as one family, so one habit is not counted as several deviations (I187)."""
    return next((name for name, prefixes in FAMILIES if key.startswith(prefixes)), "other")


def _sd_floor(key: str, scale: dict) -> float:
    """The smallest spread a feature is given at a chunk size: one occurrence's
    worth, so a feature the author never shows is not a certain deviation."""
    words = max(1.0, scale["words"])
    sents = max(1.0, scale["sentences"])
    paras = max(1.0, scale["paragraphs"])
    if key.startswith(("con_", "fw_")) or key == "question_rate":
        return 1000.0 / words
    if key.startswith(("open_", "punct_")) or key in ("sent_short_share", "sent_long_share", "short_after_long"):
        return 1.0 / sents
    if key.startswith("para_"):
        return 1.0 / paras
    if key == "word_len":
        return 0.05
    if key == "type_token":
        return 0.01
    return 0.5  # sentence-length statistics, in words


# --- the discriminant ----------------------------------------------------------
# Nearest shrunken centroids (Tibshirani, Hastie, Narasimhan and Chu, 2002) on
# standardised features, equal priors. The shrinkage, which also selects the
# features, is chosen by grouped cross-validation, so no piece of writing is
# on both sides of a fold, and the held-out scores are Platt-calibrated, so the
# score is a log-odds the cross-validation stands behind (I190). A diagonal
# model counts correlated features twice; the calibration absorbs that, and
# the cross-validated AUC says how well it separates at all.
_MODELS = {}
FOLDS = 5


def _nsc_fit(rows: list[list[float]], ys: list[int]) -> dict:
    n, p = len(rows), len(rows[0])
    mu = [statistics.fmean(r[j] for r in rows) for j in range(p)]
    raw_sd = [statistics.pstdev([r[j] for r in rows]) for j in range(p)]
    live = [x > 1e-12 for x in raw_sd]  # a feature constant over the training chunks carries nothing
    sig = [x if ok else 1.0 for x, ok in zip(raw_sd, live)]
    z = [[(r[j] - mu[j]) / sig[j] for j in range(p)] for r in rows]
    cls = {c: [z[i] for i in range(n) if ys[i] == c] for c in (0, 1)}
    cen = {c: [statistics.fmean(r[j] for r in cls[c]) for j in range(p)] for c in (0, 1)}
    ss = [sum((r[j] - cen[c][j]) ** 2 for c in (0, 1) for r in cls[c]) for j in range(p)]
    s = [math.sqrt(x / max(1, n - 2)) for x in ss]
    s0 = max(1e-3, statistics.median([x for x, ok in zip(s, live) if ok] or [1.0]))
    sk = [x + s0 for x in s]
    m = {c: math.sqrt(1.0 / len(cls[c]) - 1.0 / n) for c in (0, 1)}
    overall = [statistics.fmean(r[j] for r in z) for j in range(p)]
    d = {c: [(cen[c][j] - overall[j]) / (m[c] * sk[j]) if live[j] else 0.0 for j in range(p)] for c in (0, 1)}
    return {"mu": mu, "sig": sig, "sk": sk, "m": m, "overall": overall, "d": d,
            "dmax": max(abs(v) for c in (0, 1) for v in d[c])}


def _nsc_shrink(fit: dict, delta: float) -> list[tuple[int, float, float]]:
    """(feature, weight, midpoint) for every feature whose shrunken centroids
    differ; the rest carry no evidence. A feature's log-odds contribution,
    ((v - c_ref)^2 - (v - c_author)^2) / (2 s^2), is weight * (v - midpoint)."""
    out = []
    for j, sk in enumerate(fit["sk"]):
        c = {}
        for k in (0, 1):
            dk = fit["d"][k][j]
            shrunk = math.copysign(max(0.0, abs(dk) - delta), dk)
            c[k] = fit["overall"][j] + fit["m"][k] * sk * shrunk
        if c[0] != c[1]:
            out.append((j, (c[1] - c[0]) / (sk * sk), (c[0] + c[1]) / 2.0))
    return out


def _nsc_terms(fit: dict, active: list, x: list[float]) -> list[tuple[float, int]]:
    """Each active feature's log-odds contribution, author over reference."""
    mu, sig = fit["mu"], fit["sig"]
    return [(w * ((x[j] - mu[j]) / sig[j] - c), j) for j, w, c in active]


def _auc(scores: list[float], ys: list[int]) -> float:
    """Area under the ROC curve (Mann-Whitney, ties shared)."""
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks, i = [0.0] * len(scores), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        for t in range(i, j + 1):
            ranks[order[t]] = (i + j) / 2.0 + 1.0
        i = j + 1
    n1 = sum(ys)
    n0 = len(ys) - n1
    if not n1 or not n0:
        return 0.5
    return (sum(r for r, y in zip(ranks, ys) if y) - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def _platt(scores: list[float], ys: list[int]) -> tuple[float, float]:
    """a, b so that a * score + b is a calibrated log-odds, each class weighted
    to half, as the equal priors assume. Platt's smoothed targets and a small
    ridge keep the fit finite when the held-out scores separate the classes
    completely; the scores are standardised first and the Newton steps are
    halved until the loss falls."""
    n1 = max(1, sum(ys))
    n0 = max(1, len(ys) - sum(ys))
    w = [0.5 / n1 if y else 0.5 / n0 for y in ys]
    tgt = [(n1 + 1.0) / (n1 + 2.0) if y else 1.0 / (n0 + 2.0) for y in ys]
    mu = statistics.fmean(scores)
    sd = statistics.pstdev(scores) or 1.0
    z = [(s - mu) / sd for s in scores]
    ridge = 1e-3

    def loss(a, b):
        tot = ridge * (a * a + b * b) / 2.0
        for zi, t, wi in zip(z, tgt, w):
            e = a * zi + b
            tot += wi * (math.log1p(math.exp(-abs(e))) + max(e, 0.0) - t * e)
        return tot

    a, b = 1.0, 0.0
    cur = loss(a, b)
    for _ in range(100):
        ga, gb, haa, hab, hbb = ridge * a, ridge * b, ridge, 0.0, ridge
        for zi, t, wi in zip(z, tgt, w):
            e = max(-35.0, min(35.0, a * zi + b))
            pr = 1.0 / (1.0 + math.exp(-e))
            g, h = wi * (pr - t), wi * pr * (1.0 - pr)
            ga, gb = ga + g * zi, gb + g
            haa, hab, hbb = haa + h * zi * zi, hab + h * zi, hbb + h
        det = haa * hbb - hab * hab
        if det <= 0:
            break
        da, db = (hbb * ga - hab * gb) / det, (haa * gb - hab * ga) / det
        step = 1.0
        while step > 1e-6:
            na, nb = a - step * da, b - step * db
            new = loss(na, nb)
            if new <= cur:
                break
            step /= 2.0
        if step <= 1e-6:
            break
        a, b, done = na, nb, abs(cur - new) < 1e-12
        cur = new
        if done:
            break
    # back to the raw score: a * (s - mu) / sd + b
    return a / sd, b - a * mu / sd


def _slog(x: float) -> float:
    """A signed log: a diagonal model's raw log-odds runs to thousands when a
    feature barely varies within a class, and Platt scaling needs it tamed."""
    return math.copysign(math.log1p(abs(x)), x)


def _fold(group: str) -> int:
    return int(hashlib.sha256(group.encode("utf-8")).hexdigest()[:8], 16) % FOLDS


def fit_discriminant(author: dict, reference: dict, min_reference_chunks: int = MIN_REFERENCE_CHUNKS) -> dict:
    """The author-against-reference model, or {"error": why not}. Memoised per
    pair of profiles, since cross-validation costs a few seconds."""
    key = (id(author), id(reference), min_reference_chunks)
    if key in _MODELS:
        return _MODELS[key]
    a, r = author.get("vectors"), reference.get("vectors")
    if not a or not r:
        model = {"error": "the fingerprint or the reference was built without chunk vectors; rebuild it with this version"}
    elif len(r["rows"]) < min_reference_chunks:
        model = {"error": f"the reference has {len(r['rows'])} pieces of {MIN_COMPARE_WORDS} words or more; the discriminant "
                          f"needs {min_reference_chunks}, from texts disjoint from every test"}
    else:
        model = _fit(a, r)
    _MODELS[key] = model
    return model


def _fit(a: dict, r: dict) -> dict:
    keys = [k for k in a["keys"] if k in set(r["keys"])]
    ai = [a["keys"].index(k) for k in keys]
    ri = [r["keys"].index(k) for k in keys]
    rows = [[row[j] for j in ai] for row in a["rows"]] + [[row[j] for j in ri] for row in r["rows"]]
    ys = [1] * len(a["rows"]) + [0] * len(r["rows"])
    folds = [_fold("a:" + g) for g in a["groups"]] + [_fold("r:" + g) for g in r["groups"]]
    full = _nsc_fit(rows, ys)
    grid = [full["dmax"] * i / 20.0 for i in range(20)]
    cv = {i: ([], []) for i in range(len(grid))}
    for f in range(FOLDS):
        train = [i for i in range(len(rows)) if folds[i] != f]
        test = [i for i in range(len(rows)) if folds[i] == f]
        if not test or len({ys[i] for i in train}) < 2 or min(sum(ys[i] for i in train), len(train) - sum(ys[i] for i in train)) < 2:
            continue
        fit = _nsc_fit([rows[i] for i in train], [ys[i] for i in train])
        for gi, delta in enumerate(grid):
            active = _nsc_shrink(fit, delta)
            for i in test:
                cv[gi][0].append(sum(t for t, _ in _nsc_terms(fit, active, rows[i])))
                cv[gi][1].append(ys[i])
    aucs = [(_auc(*cv[gi]) if cv[gi][0] else 0.5, gi) for gi in range(len(grid))]
    best_auc = max(x for x, _ in aucs)
    gi = max(g for x, g in aucs if x >= best_auc - 1e-9)  # the most shrinkage at the best AUC
    pa, pb = _platt([_slog(s) for s in cv[gi][0]], cv[gi][1]) if cv[gi][0] else (1.0, 0.0)
    return {"keys": keys, "fit": full, "delta": grid[gi], "active": _nsc_shrink(full, grid[gi]),
            "platt": [pa, pb], "cv_auc": round(best_auc, 3), "author_chunks": len(a["rows"]),
            "reference_chunks": len(r["rows"])}


def discriminant(f: dict, author: dict, reference: dict, min_reference_chunks: int = MIN_REFERENCE_CHUNKS) -> dict:
    """The calibrated log-odds that the text is the author's rather than the
    reference's (positive: nearer the author), with the cross-validated AUC it
    rests on and the features pulling each way. The score is None, with the
    reason, when the reference is too small to fit on."""
    model = fit_discriminant(author, reference, min_reference_chunks)
    if "error" in model:
        return {"score": None, "error": model["error"], "features_used": 0, "for_author": [], "for_reference": []}
    x = [f.get(k, 0.0) for k in model["keys"]]
    terms = _nsc_terms(model["fit"], model["active"], x)
    raw = sum(t for t, _ in terms)
    a, b = model["platt"]
    score = a * _slog(raw) + b
    terms.sort()
    name = model["keys"]
    return {"score": round(score, 3), "p_author": round(1.0 / (1.0 + math.exp(-max(-35.0, min(35.0, score)))), 3),
            "cv_auc": model["cv_auc"], "features_used": len(model["active"]),
            "author_chunks": model["author_chunks"], "reference_chunks": model["reference_chunks"],
            "for_author": [name[j] for t, j in terms[-5:][::-1] if t > 0],
            "for_reference": [name[j] for t, j in terms[:5] if t < 0]}


# --- compare ------------------------------------------------------------------
def _basis(fp: dict, surface: str | None) -> tuple[dict, str, str]:
    """The profile a surface is measured against, its name, and a note when a
    named surface has none of its own and falls back to the pooled profile (I192)."""
    if surface and surface in fp["surfaces"]:
        return fp["surfaces"][surface], surface, ""
    if not surface:
        return fp["pooled"], "pooled", ""
    words = {}
    for s in fp.get("samples", []):
        words[s["surface"]] = words.get(s["surface"], 0) + s.get("words", 0)
    total = sum(words.values()) or 1
    mix = ", ".join(f"{k} {100 * v / total:.0f}%" for k, v in sorted(words.items(), key=lambda kv: -kv[1])[:3])
    return fp["pooled"], "pooled", (f"no {surface} profile in the fingerprint; measured against the pooled profile"
                                    + (f" ({mix})" if mix else ""))


def _scale_for(prof: dict, words: int) -> tuple[int, dict] | None:
    scales = prof.get("scales") or {}
    if not scales:
        return None
    size = min(scales, key=lambda s: abs(math.log(int(s)) - math.log(max(1, words))))
    return int(size), scales[size]


def compare(text: str, fp: dict, surface: str | None = None, fdr: float = FDR, reference: dict | None = None,
            min_reference_chunks: int = MIN_REFERENCE_CHUNKS) -> dict:
    """Deviation of a text from the fingerprint at the size of piece nearest
    the text's length. Each feature gets a prediction t against the author's
    pieces of that size; each family's statistic, its largest |t|, gets a
    conformal p-value from its rank among the same statistic over the author's
    own pieces, left out one at a time; Benjamini-Hochberg at `fdr` runs across
    the families, function words included. fw_distance and shape_distance are
    within-author mean |t|, over the function words and over the shape families."""
    if not 0.0 < fdr < 1.0:
        raise ValueError(f"fdr must be between 0 and 1, not {fdr}")
    prof, basis, note = _basis(fp, surface)
    fe = features(prose_paragraphs(text))
    if not fe:
        return {"basis": basis, "error": "no prose to measure"}
    f = fe["f"]
    if f["_words"] < MIN_COMPARE_WORDS:
        return {"basis": basis, "words": f["_words"],
                "error": f"{f['_words']} words of prose; the measure needs at least {MIN_COMPARE_WORDS}"}
    picked = _scale_for(prof, f["_words"])
    if picked is None or "null" not in picked[1]:
        return {"basis": basis, "error": "the fingerprint was built by an older fingerprint.py, without per-size nulls; rebuild it"}
    size, sc = picked
    n = sc["n"]
    devs, fams = [], {}
    for k, st in sc["features"].items():
        if k not in f:
            continue
        s = max(st["sd"], _sd_floor(k, sc))
        t = _t(f[k], st["mean"], st["sd"], _sd_floor(k, sc), n)
        d = {"feature": k, "family": family(k), "value": round(f[k], 4), "author_mean": round(st["mean"], 4),
             "author_sd": round(s, 4), "z": round(t, 2), "p": _conformal_p(abs(t), sc["null"][family(k)])}
        devs.append(d)
        fams.setdefault(d["family"], []).append(d)
    rows = []
    for name, ds in sorted(fams.items()):
        lead = max(ds, key=lambda d: abs(d["z"]))
        rows.append((name, lead["p"], ds, lead))
    hit, cut = _bh([r[1] for r in rows], fdr)
    flagged, fw_flagged = [], []
    for i in sorted(hit, key=lambda i: rows[i][1]):
        name, pf, ds, lead = rows[i]
        if name == "function words":
            fw_flagged = sorted((d for d in ds if d["p"] <= cut), key=lambda d: -abs(d["z"]))[:10]
            for d in fw_flagged:  # each flagged word in a sentence of the text, and in one of the author's
                d["quote"] = (fe["ev"].get(d["feature"]) or [""])[0][:240]
                d["author_quote"] = (prof["evidence"].get(d["feature"]) or [{"quote": ""}])[0]["quote"]
            continue
        d = dict(lead, p_family=pf)
        d["also"] = [x["feature"] for x in sorted(ds, key=lambda x: -abs(x["z"])) if x is not lead and x["p"] <= cut]
        # quoted from the first feature of the family that has a passage to quote, so a flag led by
        # "no short sentences" still shows a sentence from the text
        keys = [lead["feature"]] + d["also"] + [x["feature"] for x in ds]
        d["quote"] = next((fe["ev"][k][0][:240] for k in keys if fe["ev"].get(k)), "")
        d["author_quote"] = next((prof["evidence"][k][0]["quote"] for k in keys if prof["evidence"].get(k)), "")
        flagged.append(d)
    for d in devs:
        d["p"] = round(d["p"], 4)
    fw = fams.get("function words", [])
    shape = {k: v for k, v in fams.items() if k != "function words"}
    out = {"basis": basis, "scale": size, "chunks": n, "words": f["_words"], "sentences": f["_sentences"],
           "fw_distance": round(statistics.fmean(abs(d["z"]) for d in fw), 3) if fw else 0.0,
           "shape_distance": round(statistics.fmean(statistics.fmean(abs(d["z"]) for d in ds) for ds in shape.values()), 3) if shape else 0.0,
           "fdr": fdr, "flagged": flagged, "function_words_flagged": fw_flagged,
           "n_features": len(devs), "n_families": len(shape)}
    floor_p = 1.0 / (n + 1)  # the smallest p a rank among n pieces can give
    if floor_p > fdr / max(1, len(rows)):
        out["resolution_note"] = (f"only {n} pieces of about {size} words in the {basis} profile, so the smallest p is {floor_p:.3f}; "
                                  + ("no family can be flagged at this rate" if floor_p > fdr else
                                     "one family alone cannot be flagged, only several together"))
    if note:
        out["basis_note"] = note
    if reference:
        disc = discriminant(f, prof, reference, min_reference_chunks)
        # the passage behind each feature that pulls the score, so the log-odds is not a bare number
        disc["passages"] = {k: fe["ev"][k][0][:240] for k in disc["for_author"] + disc["for_reference"] if fe["ev"].get(k)}
        out["discriminant"] = dict(disc, reference=reference.get("name", "reference"))
    return out


def render(result: dict, path: str = "") -> str:
    if "error" in result:
        return f"fingerprint: {result['error']}"
    lines = [f"fingerprint: {path or 'text'}: {result['words']} words, {result['sentences']} sentences, "
             f"basis {result['basis']} at {result['scale']}-word chunks (n = {result['chunks']}); "
             f"function-word distance {result['fw_distance']}, shape distance {result['shape_distance']} "
             f"(within-author mean |t| over {result['n_features']} features in {result['n_families']} shape families and the function words)"]
    for key in ("basis_note", "resolution_note"):
        if result.get(key):
            lines.append(f"  note: {result[key]}")
    d = result.get("discriminant")
    if d and d.get("score") is None:
        lines.append(f"  discriminant against {d['reference']}: not computed; {d['error']}")
    elif d:
        side = "nearer the author" if d["score"] > 0 else "nearer the reference"
        lines.append(f"  discriminant {d['score']:+.2f} log-odds (p author {d['p_author']:.2f}) against {d['reference']}, "
                     f"cross-validated AUC {d['cv_auc']:.2f}, {d['features_used']} features: {side}"
                     + (f"; for the author: {', '.join(d['for_author'])}" if d["for_author"] else "")
                     + (f"; for the reference: {', '.join(d['for_reference'])}" if d["for_reference"] else ""))
        for k, q in list((d.get("passages") or {}).items())[:3]:
            lines.append(f"      {k}: \"{q[:110]}\"")
    if not result["flagged"] and not result["function_words_flagged"]:
        lines.append(f"  no family deviates from the author at a false discovery rate of {result['fdr']}")
    for d in result["flagged"]:
        direction = "more" if d["z"] > 0 else "less"
        lines.append(f"  {d['family']:16} {d['feature']:26} t {d['z']:+5.1f}  p {d['p_family']:.2g}  {direction} than the author "
                     f"({d['value']} against {d['author_mean']} ± {d['author_sd']})"
                     + (f"; also {', '.join(d['also'])}" if d["also"] else ""))
        if d["quote"]:
            lines.append(f"      text:   \"{d['quote'][:120]}\"")
        if d["author_quote"]:
            lines.append(f"      author: \"{d['author_quote'][:120]}\"")
    if result["function_words_flagged"]:
        lines.append("  function words: " + ", ".join(f"{d['feature'][3:]} {d['z']:+.1f}" for d in result["function_words_flagged"]))
        for d in result["function_words_flagged"][:3]:
            if d.get("quote"):
                lines.append(f"      {d['feature'][3:]}: \"{d['quote'][:110]}\"")
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
        statefile.write_text(args.out, text + "\n")
        print(f"fingerprint: prose profile written to {args.out}")
    else:
        print(text)
    return 0


# --- CLI ----------------------------------------------------------------------
def cmd_build(args) -> int:
    fp = build(args.samples, tuple(p.strip() for p in args.provenance.split(",") if p.strip()), args.surface,
               tuple(x.strip() for x in (args.exclude or "").split(",") if x.strip()), args.allow_approved)
    statefile.write_json(args.out, fp, indent=1, sort_keys=True, ensure_ascii=True)
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
    statefile.write_json(args.out, ref, indent=1, sort_keys=True, ensure_ascii=True)
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
    res = compare(text, fp, args.surface, args.fdr, ref)
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
    b.add_argument("--exclude", help="comma-separated sample ids to hold out (a test set the profile never sees); an unknown id is an error")
    b.add_argument("--allow-approved", action="store_true", help="permit --provenance approved (AI-assisted text); recorded in the output")
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
    c.add_argument("--fdr", type=float, default=FDR, help="false discovery rate across the feature families (default 0.05)")
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
