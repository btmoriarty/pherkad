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

Every command below runs from the skill's own folder: `<skill dir>` is the base directory the skill loader reports for this skill, so `python3 <skill dir>/tools/pherkad.py` works wherever the skill is installed.

## Modes

Pherkad runs in two directions against the same profile and the same tell catalog.

- **Validation**: check an existing draft and report, with cited evidence and a verdict. Validation has two depths, **quick** and **full**, chosen in Step 0b.
- **Authoring** (`references/authoring.md`): draft or rewrite prose in the writer's voice in the first place, then self-validate before returning it. Use this whenever the user asks for a draft or rewrite in their voice, or wants text they will send as themselves.

Both begin with `Voice_Profile.md`. Without it, build the profile first. In quick mode with a runtime, the packet carries the profile, so do not load it a second time.

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

## Step 0a: Name the surface

Every check and every draft names its surface before anything is judged: what the text is, who is speaking (the assistant to the writer, or the writer as himself), and whether the positive register is expected. The shipped surfaces are `assistant-chat`, `technical`, `email`, `post`, `paper`, `slides`, and `fiction`; a user's `surfaces.json` can add more or point a name at its own overlay and a few approved excerpts from the same series. `python3 <skill dir>/tools/pherkad.py surfaces` lists them with their guidance. Say the surface in the first line of any report. Do not infer one from the text when the user has not said and it is not obvious from the request; ask, since a wrong surface changes what is a fault. An unknown surface is an error, not a guess.

For authoring, a surface's approved excerpts are the examples to write beside: the same register, the same series, the writer's own. Use them for rhythm and register, never as a template to fill.

## Step 0b: Choose the depth, quick or full

Most checks are on a short piece the writer is about to send, and for those the seven-dimension audit is more report than the draft is worth: six fingerprint sentences and a rewrite for every flag, on a four-paragraph email, buries the two things that matter. **Quick** is the default. **Full** (Steps 1 through 6) is for a deliberate audit.

| Choose | When |
|---|---|
| **Quick** | The draft is under about 600 words; or it is a chat reply, an email, a message, a slide, a README section; or the user asked for a check, a look, a pass, "does this read as me" |
| **Full** | The user asked for an audit, a validation report, or scores; or the draft is a paper, an essay, a chapter, a submission; or a quick pass found the voice missing across the piece rather than in spots |

Say which depth is running in the first line of the report. A user can ask for the other at any time.

## Quick mode

One command, one table, one line of verdict. Nothing is scored and nothing is rewritten that was not flagged.

0. **Where a runtime is available, assemble the packet first**: `python3 <skill dir>/tools/pherkad.py review-pack --surface <surface> <draft>` prints one prompt carrying everything below, the surface and its guidance, the profile files, the approved excerpts, the mechanical findings with the author's decisions applied, the judgment-only rules for the surface, these instructions, and the output schema, with a hash of every input. Run that and follow it: step 1 is done in it, step 2's rules are listed in it, and the context is the same every time. `--out DIR` writes `pack.json` and `prompt.md` instead. When the author has read and ruled on every row, `python3 <skill dir>/tools/pherkad.py review-import <table> --file <draft> --decisions <file> --confirmed` records them, and the next packet for that draft lists them under "already ruled"; the author rules, the tool only records.
1. **Run the mechanical layer once**, if a Python runtime is available: `python3 <skill dir>/tools/pherkad.py check --surface <surface> --format json <draft>`, with the surface named in Step 0a (`assistant-chat` when the draft is a reply to the user rather than prose written as them), and the project's overlay with `--config` when there is one. Every finding arrives with a `rule_id`.
2. **Read the draft once for the judgment-only rules that apply to its surface** (the table below), not the whole catalog. A syntactic frame recurring across a document's titles or sentences (`X, not Y` on five slides) is now mechanical, `structure.frame.*`; read for it only where the check is under its threshold and the repetition still reads as a template. Then: the antithesis and triplet families in `references/ai_tells.md` 5c and 5f, the counter-X and authenticity constructions in 5g and 5h, the structural artifacts in 5i, and whatever the profile's companion files ban that no regex expresses. Add a row for each supported hit, with `judgment` as its rule reference.
3. **Decide each row.** A finding is not a fault until it has been read. The decision is one of:
   - `fix`: the tell is real here; the row carries a proposed edit.
   - `intentional`: the writer's own move (a deliberate contrast, a fragment for emphasis, a term of art). No edit.
   - `literal`: the flagged phrase is used in its plain sense (a load-bearing wall, an API key). No edit.
   - `not applicable`: the rule does not apply to this surface (a scene-setting opener in a bug report; a missing positive marker in a technical answer). No edit.
   - `quoted`: someone else's words. No edit.
4. **Read the positive register only where the surface expects it** (table below). Where it does, and the draft shows none of the profile's markers, add one row `positive-register` with decision `fix` and a proposed place to put one marker; that is the flattening signal from Step 3 of full mode, reported once, not as a verdict on every paragraph.
5. **Verdict**: `PASS` when no row is `fix`; `REVISE` when any is, since a `fix` row is a hit already read and judged real; `REWRITE` only when the `positive-register` row is `fix` and three or more other rows are `fix`, in which case say so and offer full mode.

**Output.** One table, then the verdict line:

```
QUICK VOICE CHECK  (surface: email; profile loaded; 412 words)

| rule_ref | line | quote | decision | rationale | proposed_edit |
|---|---|---|---|---|---|
| honest-framing | 3 | `The honest answer is that we slipped.` | fix | announces candour instead of exercising it | `We slipped.` |
| soft.is-the-point | 3 | `That is the point of the audit.` | intentional | the sentence is the point, and the writer's own construction | |
| structure.two-beat | 7 | `None of them wrong. None of them ours.` | fix | the clipped symmetry is the tell, and the profile's rhythm runs longer | `None of them were wrong, and none of them were ours.` |
| judgment (5c) | 9 | `Not a failure, but a lesson.` | fix | the antithesis frame | `A lesson.` |
| positive-register | | | not applicable | a status email; no invented scene expected | |

VERDICT: REVISE (3 fix). Everything else stands as written.
```

The `line` is the finding's line from the packet, or for a judgment row the line the quote sits on; `review-import` binds a ruling to it, and without it a quote that appears twice is refused. A proposed edit changes no fact, name, number, date, source, or emphasis. When the user confirms an `intentional` or `literal` row in a project that keeps a decision file, record it once with `python3 <skill dir>/tools/pherkad.py decide --decisions <file> --disposition intentional --reason "<the rationale>" <path>:<line>:<rule_id>` (`--disposition accepted` for a `literal` row) so it stays quiet until the line or the rule changes.

**Positive markers apply by surface.** A draft is not flat for lacking a scene the surface never wanted. This table mirrors the `positive_register` field each shipped surface carries; `pherkad.py surfaces --json` is the authority when a runtime is available.

| Surface | Positive register expected | Notes |
|---|---|---|
| assistant-chat (a reply to the user) | no | Bans, dashes, honest-X, and the chat-only rules apply; no missing-marker row; short-reply cadence is advisory |
| technical answer, bug report, commit message, README section | no | Precision is the register; hold to the tell catalog and accuracy |
| email, message to a person | where the profile shows it in that register | One marker is enough; a status email needs none |
| post, essay, talk, application letter | yes | The frame and the close carry the writer; the core may be plain |
| paper, submission | in the frame and transitions only | The technical core is held to accuracy, per Genre calibration |
| slides | in the frame and transitions only | A deck is its titles; time boxes, presenter cues and structural narration are not slide content |
| fiction | by the work's own voice document, not this profile | See the project's voice law; the personal profile does not apply |

## Full mode

The audit (Steps 1 through 6: the fingerprint, the seven-dimension scores, the flags, the density, the verdict, the rewrites) and its report template are in `references/full_mode.md`. Load it only when full mode runs.

## Calibration notes

Pherkad is not a generic AI detector and never polices someone else's text. It validates against one voice, its own user's. A passage can be entirely human-written and still fail because it does not sound like this writer; an assisted passage can pass because it does.

In full mode, a single antithesis construction or one banned phrase does not force a REVISE: the validator weighs density and clustering, not lone unread hits. In quick mode each row has been read, and one `fix` is enough. Writers use contrast; models overuse it.

**Genre calibration.** Distinctiveness lives in the frame, the transitions, and the close; a precise legal or technical core is correct when it is plain and must not be flagged for failing to be vivid. A finished piece is often deliberately uneven, a distinctive frame around an exact middle, and that unevenness is the design, not a defect. Read the frame and the transitions for the writer's positive register; hold the technical core to accuracy and the tell catalog, not to the archetype.

The profile is the user's data. It lives in their folder, is never committed to this repository, and updates only when they ask or when they correct a flag ("that one is actually me"). Corrections append to the profile, so a later run can apply the recorded correction instead of repeating the flag.
