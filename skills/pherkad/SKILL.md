---
name: pherkad
description: Validate that papers, blog posts, and other prose sound like the user's own human voice rather than AI-generated or AI-flattened writing. Trigger when the user asks for a voice check, voice audit, or tone check, asks "does this sound like me," or submits a draft and asks whether it sounds human or sounds like them. Also trigger when the user wants to build or update their voice profile from writing samples. First run builds the profile; later runs validate drafts against it.
---

# Pherkad

Validate that written output sounds like one specific person's voice.

Pherkad runs a structured diagnostic against text to detect AI-generated flatness, voice drift, and tone misalignment. It produces an actionable report with cited evidence, never a bare score.

Two parts do the work:

- **The engine** (this skill plus `references/ai_tells.md`): a catalog of documented AI-writing tells and the scoring protocol. Generic, shared by every user.
- **The voice profile** (`Voice_Profile.md` in the user's working folder): what this one writer actually sounds like. Personal, built once, refined over time. Never part of this repository.

## When to use

- Before finalizing a paper, blog post, application letter, or any prose that should sound like its author
- When the user asks "does this sound like me?"
- When reviewing AI-assisted drafts for voice authenticity
- As a final quality gate before publication

## Step 0: Check for a voice profile

Look for `Voice_Profile.md` in the user's working folder.

- **Missing:** run the profile-builder interview in `references/profile_builder.md` before validating anything. Validating without a profile produces a generic AI-tell scan at best; say so plainly if the user wants a scan anyway, and label the output as profile-less.
- **Present:** load it. Its markers drive Dimensions 1 through 4, 6, and 7 below. `references/example_profile.md` shows the expected shape (the persona in it is fictional).

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
| 5. Absence of AI artifacts | Matches against the tell catalog in `references/ai_tells.md` |
| 6. Structural habits | How the writer opens, builds, and ends; what they leave implicit |
| 7. Tonal identity | The overall feel, matched against the profile's tone description |

Every score MUST cite a specific passage from the text as evidence. No dimension may be scored without a quote.

## Step 3: Flag AI-artifact sentences (individual hits)

If a Python runtime is available, first run the mechanical layer for exact line-numbered hits:

```
python3 tools/voicelint.py --json --strict <draft>
```

Then walk the full catalog in `references/ai_tells.md` (categories 5a through 5i) and flag every sentence exhibiting a tell, including the structural families the linter cannot see. List each flagged sentence with the specific tell identified. Deduplicate against the linter's findings; count each construction once.

Apply the catalog's caveats: technical-literal uses, direct quotes, single isolated constructions, informal-register exceptions, and the validator-internals exception (never flag a pattern inside a line that quotes, names, or defines it). Where the profile overrides a default (for example, a writer who uses em dashes on purpose), the profile wins.

## Step 4: Compute the density signal

1. Count total flagged constructions across the document.
2. Count total words.
3. Density = (flagged constructions / words) * 100.
4. Density above 2.0 per 100 words raises a DENSITY WARNING.

Clustering weighs separately: two or more antithesis constructions (5c) or two or more triplet noun piles (5f) inside one paragraph raises a CLUSTER WARNING for that paragraph.

## Step 5: Produce the verdict

- **PASS**: reads as the writer's voice throughout. Minor surface edits only. No density warning, no cluster warning.
- **REVISE**: core voice present but artifacts or drift in specific sections. Density warning OR cluster warning OR a handful of individual hits.
- **REWRITE**: voice has flattened or drifted substantially. Density warning AND multiple cluster warnings, or heavy hits across multiple dimensions.

## Step 6: Deliver targeted rewrites

For every flagged sentence, provide a rewrite that preserves the meaning, matches the profile's markers, and names the specific correction. Do NOT rewrite the whole piece; fix only the misaligned sentences.

A voice rewrite must not change content: never add or drop facts, names, numbers, dates, or sources, and preserve the original's emphasis (urgency, authority, caveats). Keep terms of art; do not paraphrase them away.

## Output format

```
VOICE VALIDATION REPORT
=======================

PROFILE: [Voice_Profile.md loaded / MISSING - profile-less scan]

FINGERPRINT
  Most like the writer:
    1. "[sentence]"
    2. "[sentence]"
    3. "[sentence]"

  Least like the writer:
    1. "[sentence]": [reason]
    2. "[sentence]": [reason]
    3. "[sentence]": [reason]

DIAGNOSTIC SCORES
  [table from Step 2, with evidence quotes]

AI ARTIFACT FLAGS (individual hits)
  [list from Step 3, grouped by category 5a-5i]

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

## Calibration notes

Pherkad is not a generic AI detector and never polices someone else's text. It validates against one voice, its own user's. A passage can be entirely human-written and still fail because it does not sound like this writer; an assisted passage can pass because it does.

A single antithesis construction or one banned phrase does not force a REVISE. The validator weighs density and clustering, not lone hits. Writers use contrast; models overuse it.

The profile is the user's data. It lives in their folder, is never committed to this repository, and updates only when they ask or when they correct a flag ("that one is actually me"). Corrections append to the profile so the validator gets more accurate with use.
