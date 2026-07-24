# Voice-authoring evaluation

The harness for the voice-authoring study. It measures **correct-profile lift**: whether a draft written with the writer's own profile reads more like the writer than drafts written with a wrong profile or no profile. This is a blinded, single-rater pilot instrument, run on your own machine to prove the method and get a first signal; the confirmatory multi-writer, multi-reader design is `../docs/blind-eval.md`. Without the comparison and blinding, a single labeled draft cannot separate voice capture from competent prose.

`study.py` does the bookkeeping that keeps the judgment honest (conditions, randomization, hidden keys, arithmetic). The judgment itself is human. See `../docs/blind-eval.md` for the full study design; this is how you run it.

## Before you start

- **Consent and privacy.** You are collecting real people's writing. Get their permission, tell them how it is used, and keep it local. Everything under `eval/data/` is gitignored and never leaves your machine; the harness code and this protocol are the only shareable parts.
- **Build the profiles first.** Each writer needs a Pherkad voice profile built from their samples with `references/profile_builder.md`, holding one sample back (into `holdout/`) *before* marker extraction, per Step 4b. The profile is the thing under test; if it is sloppy, the result is about the profile, not the tool.

## The three steps, wired up

Maps to your plan (gather writers, have Pherkad write on a new subject, validate), with the controls that make it a test.

1. **Gather.** For each writer: `python3 study.py add-writer <id>`, then drop their samples in `data/writers/<id>/samples/`, one held-out piece in `holdout/`, and paste the built profile into `profile.md`.
2. **Write on a new subject.** Write a factual brief on something the writers have not covered: `python3 study.py add-brief <id>` and fill it in (facts and notes, not source prose, so authoring composes rather than imitates). Then:
   - `python3 study.py plan <run> --brief <id> --writers a,b,c --anchor`
     For each writer this creates three drafts to author (their own profile = `correct`, another writer's = `wrong`, and `none`), plus an `anchor` that is a real held-out piece by the writer (the ceiling). Blind IDs hide which is which.
   - `python3 study.py prompts <run>` emits an authoring prompt per draft. Run each through Pherkad authoring and save the output to the named `drafts/<blind_id>.md`.
3. **Validate, blind.** `python3 study.py sheet <run>` builds a rating sheet: for each writer it shows real reference writing, then the shuffled candidates. Rate each 1 to 5 for how much it sounds like the writer, and flag any that invents facts, over-claims certainty, or caricatures the writer's tics. Do not open `manifest.json` until you have rated everything. Then `python3 study.py score <run>`.

## Reading the score

- **Lift near zero:** the profile adds no writer-specific value; the tool is scoring general polish. The claim stays advisory.
- **Real lift that holds across writers and registers, fidelity intact:** evidence the authoring captures voice. A high-rated but fidelity-flagged draft does not count (caricature is not voice).
- **Anchor is the ceiling.** How close `correct` gets to the real held-out piece says how much of the writer's own voice the authoring reaches.

## Sizing, and the honest limit

You as sole validator on a few writers is a **pilot**: it proves the harness and gives a first signal, but one judge and a handful of writers is not the claim. The writer is the unit that counts. `docs/blind-eval.md` sets the bar for the confirmatory version: roughly 20 to 30 writers, preregistered, independent readers as well as the writer, wrong/shuffled/no-profile controls, within-writer register coverage, and an authoring arm reported at the writer level. Only that justifies a public "reliable voice validation" claim. The harness scales to it; the judgments are what cost real effort.

## What this implements, and what stays manual

`study.py` runs the pilot: the correct, wrong, and none conditions, one rater, one run per item, with an optional real anchor. The confirmatory design in `../docs/blind-eval.md` needs pieces this harness does not automate yet: a shuffled-profile control, the validation case types (atypical authentic, matched impostors, an override sample), repeated runs for stability, and multiple independent readers with an agreement measure. Read "the harness scales to it" as "the file layout and scoring extend to it," not "it is implemented." Those elements are manual, or a job for a separate validation-study harness, until one is built.

## Files

- `study.py`: the CLI (stdlib only).
- `data/`: writers, briefs, runs. Gitignored. Never committed.
