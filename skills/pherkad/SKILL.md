---
name: pherkad
description: Validate or draft prose in the user's own voice rather than generic or flattened writing. Validation mode triggers on a voice check, voice audit, tone check, "does this sound like me," or a draft submitted to check whether it sounds like them. Authoring mode triggers when the user asks to write, draft, or rewrite prose in their voice, or wants text they will send as themselves (emails, posts, papers) to come out in their voice. Also triggers to build or update the voice profile from samples. First run builds the profile; later runs draft from it and validate against it.
---

# Pherkad

Run a structured review of whether written output matches one specific person's voice profile.

Pherkad runs a structured diagnostic against text to surface generic phrasing, voice drift, and tone misalignment. It produces an actionable report with cited evidence, never a bare score.

Five parts do the work:

- **The tell catalog** (this skill plus `references/ai_tells.md`): documented AI-writing tells and the scoring protocol. Generic, shared by every user.
- **The voice profile** (`Voice_Profile.md` in the user's working folder): what this one writer actually sounds like. Personal, built once, refined over time. Never part of this repository.
- **The mechanical linter** (`tools/voicelint.py`): the configurable, regex-based subset of the catalog. It finds literal patterns and a small number of heuristic context checks. The model must review technical uses, quotations, and other cases that need judgment.
- **The structural checker** (`tools/structlint.py`): the half of the catalog that has no string to match. It reads sentence and header shape, so it catches the clipped balanced parallel, a run of three or more short sentences, and a header that strikes a pose rather than naming its subject. Everything it reports is a warning, because these are judgment calls that over-fire by design. Run it alongside the linter, never instead of it.
- **The combined runner** (`tools/pherkad.py check`): both mechanical engines in one command, one finding list with a stable `rule_id` on every row, one density over both. This is the command to run; the two engines still run alone when only one is wanted.

## Modes

Pherkad runs in two directions against the same profile and the same tell catalog.

- **Validation**: check an existing draft and report, with cited evidence and a verdict. Validation has two depths, **quick** and **full**, chosen in Step 0b.
- **Authoring** (`references/authoring.md`): draft or rewrite prose in the writer's voice in the first place, then self-validate before returning it. Use this whenever the user asks for a draft or rewrite in their voice, or wants text they will send as themselves.

Both begin by loading `Voice_Profile.md`. Without it, build the profile first.

## When to use

- Before finalizing a paper, blog post, application letter, or any prose that should sound like its author
- When the user asks "does this sound like me?"
- When reviewing AI-assisted drafts for voice authenticity
- As a final advisory review before publication

## Step 0: Check for a voice profile

Look for `Voice_Profile.md` in the user's working folder.

- **Missing:** run the profile-builder interview in `references/profile_builder.md` before validating anything. Validating without a profile produces a generic AI-tell scan at best; say so plainly if the user wants a scan anyway, and label the output as profile-less.
- **Present:** load it. Its markers drive Dimensions 1 through 4, 6, and 7 below. `references/example_profile.md` shows the expected shape (the persona in it is fictional).
- **Companion files:** if `voice-rules.md` or `voice-authoring.md` sit in the same folder, load them too. A profile may be split across the three: `Voice_Profile.md` holds the personal markers, `voice-rules.md` the bans, `voice-authoring.md` the drafting guidance. Together they are the profile.

## Step 0b: Choose the depth, quick or full

Most checks are on a short piece the writer is about to send, and for those the seven-dimension audit is more report than the draft is worth: six fingerprint sentences and a rewrite for every flag, on a four-paragraph email, buries the two things that matter. **Quick** is the default. **Full** (Steps 1 through 6) is for a deliberate audit.

| Choose | When |
|---|---|
| **Quick** | The draft is under about 600 words; or it is a chat reply, an email, a message, a slide, a README section; or the user asked for a check, a look, a pass, "does this read as me" |
| **Full** | The user asked for an audit, a validation report, or scores; or the draft is a paper, an essay, a chapter, a submission; or a quick pass found the voice missing across the piece rather than in spots |

Say which depth is running in the first line of the report. A user can ask for the other at any time.

## Quick mode

One command, one table, one line of verdict. Nothing is scored and nothing is rewritten that was not flagged.

1. **Run the mechanical layer once**, if a Python runtime is available: `python3 tools/pherkad.py check --format json <draft>`, with `--surface assistant-chat` when the draft is a reply to the user rather than prose written as them, or the project's overlay with `--config` when there is one. Every finding arrives with a `rule_id`.
2. **Read the draft once for the judgment-only rules that apply to its surface** (the table below), not the whole catalog: the antithesis and triplet families in `references/ai_tells.md` 5c and 5f, the counter-X and authenticity constructions in 5g and 5h, the structural artifacts in 5i, and whatever the profile's companion files ban that no regex expresses. Add a row for each supported hit, with `judgment` as its rule reference.
3. **Decide each row.** A finding is not a fault until it has been read. The decision is one of:
   - `fix`: the tell is real here; the row carries a proposed edit.
   - `intentional`: the writer's own move (a deliberate contrast, a fragment for emphasis, a term of art). No edit.
   - `literal`: the flagged phrase is used in its plain sense (a load-bearing wall, an API key). No edit.
   - `not applicable`: the rule does not apply to this surface (a scene-setting opener in a bug report; a missing positive marker in a technical answer). No edit.
   - `quoted`: someone else's words. No edit.
4. **Read the positive register only where the surface expects it** (table below). Where it does, and the draft shows none of the profile's markers, add one row `positive-register` with decision `fix` and a proposed place to put one marker; that is the flattening signal from Step 3 of full mode, reported once, not as a verdict on every paragraph.
5. **Verdict**: `PASS` when no row is `fix`; `REVISE` when any is; `REWRITE` only when the `positive-register` row is `fix` and three or more other rows are `fix`, in which case say so and offer full mode.

**Output.** One table, then the verdict line:

```
QUICK VOICE CHECK  (surface: email; profile loaded; 412 words)

| rule_ref | quote | decision | rationale | proposed_edit |
|---|---|---|---|---|
| honest-framing | "The honest answer is that we slipped." | fix | announces candour instead of exercising it | "We slipped." |
| soft.is-the-point | "That is the point of the audit." | intentional | the sentence is the point, and the writer's own construction | |
| structure.two-beat | "None of them wrong. None of them ours." | fix | the clipped symmetry is the tell, and the profile's rhythm runs longer | "None of them were wrong, and none of them were ours." |
| judgment (5c) | "Not a failure, but a lesson." | fix | the antithesis frame | "A lesson." |
| positive-register | | not applicable | a status email; no invented scene expected | |

VERDICT: REVISE (3 fix). Everything else stands as written.
```

A proposed edit changes no fact, name, number, date, source, or emphasis. When the user confirms an `intentional` or `literal` row in a project that keeps a decision file, record it once with `python3 tools/pherkad.py decide --decisions <file> --reason "<the rationale>" <path>:<line>:<rule_id>` so it stays quiet until the line or the rule changes.

**Positive markers apply by surface.** A draft is not flat for lacking a scene the surface never wanted.

| Surface | Positive register expected | Notes |
|---|---|---|
| assistant-chat (a reply to the user) | no | Bans, dashes, honest-X, and the chat-only rules apply; no missing-marker row; short-reply cadence is advisory |
| technical answer, bug report, commit message, README section | no | Precision is the register; hold to the tell catalog and accuracy |
| email, message to a person | where the profile shows it in that register | One marker is enough; a status email needs none |
| post, essay, talk, application letter | yes | The frame and the close carry the writer; the core may be plain |
| paper, submission | in the frame and transitions only | The technical core is held to accuracy, per Genre calibration |
| fiction | by the work's own voice document, not this profile | See the project's voice law; the personal profile does not apply |

## Full mode: Steps 1 through 6

The audit. Every step below runs; the output is the VOICE VALIDATION REPORT.

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
python3 tools/pherkad.py check --format json <draft>
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

The verdict follows from the dimension scores (Step 2) and the signals (Steps 3 and 4), not from a general impression. "Voice dimensions" below means 1 to 4, 6, and 7; Dimension 5 is the tell read.

- **PASS**: every voice dimension scores 4 or 5, Dimension 5 is 4 or 5, and there is no density warning and no cluster warning. Minor surface edits only.
- **REVISE**: the core voice is present but a section drifts. Any one of: a voice dimension at 3; exactly one voice dimension at 2 or below (whether from a missing-markers flattening or one off-profile score); a density warning; a cluster warning; or three or more individual hits.
- **REWRITE**: the voice has flattened or drifted across the piece. Two or more voice dimensions at 2 or below, or a density warning together with two or more cluster warnings.

When the signals point at different verdicts, take the more serious one and say which signal drove it.

## Step 6: Deliver targeted rewrites

For every flagged sentence, provide a rewrite that preserves the meaning, matches the profile's markers, and names the specific correction. Do NOT rewrite the whole piece; fix only the misaligned sentences.

A voice rewrite must not change content: never add or drop facts, names, numbers, dates, or sources, and preserve the original's emphasis (urgency, authority, caveats). Keep terms of art; do not paraphrase them away.

## Output format

Quick mode's output is the table and verdict line shown under Quick mode. Full mode's is this report:

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

## Calibration notes

Pherkad is not a generic AI detector and never polices someone else's text. It validates against one voice, its own user's. A passage can be entirely human-written and still fail because it does not sound like this writer; an assisted passage can pass because it does.

A single antithesis construction or one banned phrase does not force a REVISE. The validator weighs density and clustering, not lone hits. Writers use contrast; models overuse it.

**Genre calibration.** Distinctiveness lives in the frame, the transitions, and the close; a precise legal or technical core is correct when it is plain and must not be flagged for failing to be vivid. A finished piece is often deliberately uneven, a distinctive frame around an exact middle, and that unevenness is the design, not a defect. Read the frame and the transitions for the writer's positive register; hold the technical core to accuracy and the tell catalog, not to the archetype.

The profile is the user's data. It lives in their folder, is never committed to this repository, and updates only when they ask or when they correct a flag ("that one is actually me"). Corrections append to the profile, so a later run can apply the recorded correction instead of repeating the flag.
