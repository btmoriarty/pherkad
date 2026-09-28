# Pherkad full mode: Steps 1 through 6

The audit, loaded from SKILL.md only when full mode runs. Every step below runs; the output is the VOICE VALIDATION REPORT.

## Step 1: Extract a voice fingerprint

Read the submitted text. Before scoring anything, identify:

1. **Three sentences that sound most like the writer.** Quote them.
2. **Three sentences that sound least like the writer.** Quote them, each with a reason.

This forces pattern recognition before judgment.

## Step 2: Run the seven-dimension diagnostic

Score each dimension 1 to 5. Dimensions 1-4, 6, and 7 are judged against the markers in `Voice_Profile.md`; Dimension 5 is judged against `references/ai_tells.md`.

| Dimension | What it measures |
|-----------|------------------|
| 1. Grounding and authority | Where the writer's authority comes from (lived observation, argument, research, craft) and whether this text claims it the same way |
| 2. Epistemic calibration | How the writer hedges and how confident they allow themselves to be |
| 3. Texture | The concrete specifics characteristic of this writer (settings, artifacts, sensory or operational detail) |
| 4. Sentence mechanics | Rhythm, length variation, punctuation habits, fragments, humor style |
| 5. Generic or flattened patterns | Matches against the tell catalog in `references/ai_tells.md` |
| 6. Structural habits | How the writer opens, builds, and ends; what they leave implicit |
| 7. Tonal identity | The overall feel, matched against the profile's tone description |

Every score MUST cite a specific passage from the text as evidence. No dimension may be scored without a quote.

**What the 1 to 5 means** (the same anchors for every dimension, so a score is reproducible and not a feeling):

- **5**: the profile's markers for this dimension are clearly present; the text matches the writer here.
- **4**: mostly matches; one marker is weak or missing.
- **3**: mixed; some of the writer's markers, some generic or off. The dimension neither confirms nor denies the voice.
- **2**: mostly generic or off-profile; a marker appears only faintly.
- **1**: none of the writer's markers for this dimension; reads as anyone, or as a different writer.

For Dimension 5 the scale inverts to the tell catalog: 5 means clean of tells, 1 means dense with them. Cite the quote that fixes the score at that anchor, not one step above or below.

## Step 3: Flag generic or flattened sentences (individual hits)

If a Python runtime is available, first run the mechanical layer for exact line-numbered hits, both engines in one call:

```
python3 <skill dir>/tools/pherkad.py check --surface <surface> --format json <draft>
```

(`tools/voicelint.py` and `tools/structlint.py` still run alone when only one is wanted; the combined runner already removes their overlap and computes one density.) Then walk the full catalog in `references/ai_tells.md` (categories 5a through 5i) and flag each sentence with a supported tell, including the structural families the linter cannot see. List each flagged sentence with the specific tell identified. Deduplicate against the mechanical findings; count each construction once.

Apply the catalog's caveats: technical-literal uses, direct quotes, single isolated constructions, informal-register exceptions, and the validator-internals exception (never flag a pattern inside a line that quotes, names, or defines it). Where the profile overrides a default (for example, a writer who uses em dashes on purpose), the profile wins.

**Positive register.** Absence of tells is necessary, not sufficient. Also read whether the draft carries the writer's own distinctive markers, from the profile and the "Positive register" section of `references/ai_tells.md`. A draft clean of every tell but showing none of the writer's markers has flattened toward a generic default; treat that as a REVISE-level signal even when no single hit fires.

## Step 4: Compute the density signal

Apply the density verdict only to a draft of at least 150 words with at least 3 flagged constructions. A rate per 100 words is meaningless on a short passage: one hit in 40 words reads as 2.5 and would force a REVISE that a single stray phrase should never force (see Calibration notes). Below either floor, report the individual findings and skip the density warning.

1. Count total flagged constructions across the document.
2. Count total words.
3. Density = (flagged constructions / words) * 100.
4. For a draft of 150 or more words with 3 or more findings, density above 2.0 per 100 words raises a DENSITY WARNING. Otherwise there is no density warning.

Clustering weighs separately: two or more antithesis constructions (5c) or two or more triplet noun piles (5f) inside one paragraph raises a CLUSTER WARNING for that paragraph.

## Step 5: Produce the verdict

The verdict follows from the dimension scores (Step 2) and the signals (Steps 3 and 4), not from a general impression. "Voice dimensions" below means 1 to 4, 6, and 7; Dimension 5 is the read for tells.

- **PASS**: every voice dimension scores 4 or 5, Dimension 5 is 4 or 5, and there is no density warning and no cluster warning. Minor surface edits only.
- **REVISE**: the core voice is present but a section drifts. Any one of: a voice dimension at 3; exactly one voice dimension at 2 or below (whether from a missing-markers flattening or one off-profile score); a density warning; a cluster warning; or three or more individual hits.
- **REWRITE**: the voice has flattened or drifted across the piece. Two or more voice dimensions at 2 or below, or a density warning together with two or more cluster warnings.

When the signals point at different verdicts, take the more serious one and say which signal drove it.

## Step 6: Deliver targeted rewrites

For every flagged sentence, provide a rewrite that preserves the meaning, matches the profile's markers, and names the specific correction. Do NOT rewrite the whole piece; fix only the misaligned sentences.

A voice rewrite must not change content: never add or drop facts, names, numbers, dates, or sources, and preserve the original's emphasis (urgency, authority, caveats). Keep terms of art; do not paraphrase them away.

## Output format

Full mode's output is this report:

```
VOICE VALIDATION REPORT
=======================

PROFILE: [Voice_Profile.md loaded / MISSING - profile-less scan]

FINGERPRINT
  Most like the writer:
    1. `[sentence]`
    2. `[sentence]`
    3. `[sentence]`

  Least like the writer:
    1. `[sentence]`: [reason]
    2. `[sentence]`: [reason]
    3. `[sentence]`: [reason]

DIAGNOSTIC SCORES
  [table from Step 2, with evidence quotes]

GENERIC OR FLATTENED PATTERN FLAGS (individual hits)
  [list from Step 3, grouped by category 5a-5i]

POSITIVE REGISTER
  [which of the writer's own markers are present or absent, with quotes]

DENSITY SIGNAL
  Total flagged constructions: [N]
  Total words: [M]
  Density: [N/M*100] per 100 words
  Threshold: 2.0 per 100 words
  DENSITY WARNING: [YES / NO]

CLUSTER WARNINGS
  [paragraphs where 2+ antithesis or 2+ triplet constructions co-occur]

VERDICT: [PASS / REVISE / REWRITE]

TARGETED REWRITES
  [from Step 6, only when verdict is REVISE or REWRITE]
```
