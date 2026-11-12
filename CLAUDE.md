# Pherkad

The voice tools live in `skills/pherkad/tools/`. Run the suites with `python3 <abs path>/test_voicelint.py`, `test_mdmask.py`, `test_structlint.py`, `test_pherkad.py`, `test_replycheck.py`, `test_corpusscan.py`, `test_corrections.py`, `test_samples.py`, `test_fingerprint.py`, `test_author.py`, `test_statefile.py`, `test_runner.py`, `test_gate.py`, `test_decks.py`, `test_capture.py`, and `eval/test_study.py`; all sixteen are unittest modules and pytest collects them too. `bash <repo>/tests/run-all.sh` runs the smoke test and all sixteen in one go (the pre-commit hook runs it); `PYTHON=/usr/bin/python3` checks the 3.8 floor.

## Reply preflight

Before sending any reply longer than a line or two, preflight it:

1. Write the reply to a file in the scratchpad.
2. Run `python3 <repo>/skills/pherkad/tools/replycheck.py --question "<the message being answered>" <that file>`. A `length:` advisory is not a FIX, but trim the wrapper before sending.
3. While it says `FIX`, revise and rerun, at most three times.
4. Send the exact text that passed. Keep the check output out of the reply.
5. If the check could not run (exit 2), that is not a pass; fix the cause or say the reply is unchecked.

Quote any banned phrase you need to mention in backticks; plain quotation marks are prose and fire. Full recipe and the Stop hook: `docs/reply-preflight.md`.

## Rule changes

Every change to `voice_config.json` is counted against a reference corpus before it ships, and the count goes in the CHANGELOG. The count is one command:

```
python3 <repo>/skills/pherkad/tools/corpusscan.py diff <corpus>/canon <corpus>/deliverables --config <corpus-overlay>.json --exclude '[0-9][0-9]-*.md' --ext .md --old <previous voice_config.json> --new skills/pherkad/tools/voice_config.json
```

with `<previous voice_config.json>` from `git show <last release>:skills/pherkad/tools/voice_config.json`. A candidate rule is tried before it is added with `corpusscan.py scan ... --candidate "field:pattern" --contexts 8`. The numbers are raw hits; read the contexts before calling one a violation. To turn them into precision, `corpusscan.py review ... --out labels.jsonl` exports a sample for the author to label and `score-review` scores it; only the author labels. The ban list does not grow for migrating habits; those go to the judgment layer or corpus monitoring. Chat-only rules go in `tools/surfaces/assistant-chat.json`, never the shipped defaults.

## Corrections

When the author corrects a phrase (`X -> Y`, in an edit, an email, or a review), it goes into the ledger, never by hand into `voice-rules.md`:

```
python3 <repo>/skills/pherkad/tools/corrections.py add --ledger <repo>/corrections.jsonl --before "X" --after "Y" --context "<the sentence>" --source "<where>" --surface <email|post|paper|chat> --rationale "<why>"
```

When the correction is a whole edited draft rather than one phrase, `corrections.py mine <draft> <edited> --ledger <ledger> --source "<where>" --surface <surface>` reads the candidates out of the diff (`--dry-run` first); each still needs a rationale from the author or a retirement. Then `trial` it on the reference corpus (`... trial --ledger <ledger> <id> <corpus>/canon <corpus>/deliverables --config <corpus-overlay>.json --exclude '[0-9][0-9]-*.md'`), read the contexts, and only on the author's say-so `promote --overlay skills/pherkad/tools/voice_config.json --prose voice-rules.md`, which writes the rule with its fixtures and generates the mined-corrections line. A promotion into the shipped base is a release: `pherkad.py manifest --write`, the corpus count, the CHANGELOG. A factual correction never becomes a rule; a recast of meaning is judgment-only and gets prose only.

## The measured profile

The author's own writing lives in `<profile-dir>/samples/` (private), recorded with `samples.py add ... --provenance hand|captured|approved --surface S`; the tool never guesses either. `fingerprint.py build --samples <profile-dir>/samples --out <profile-dir>/fingerprint.json` computes the measured profile from `hand` and `captured` samples (never `approved`), and `pherkad.py check --fingerprint <that file> --reference <profile-dir>/reference-flattened.json` reports advisory `voice.*` findings, one per feature family that deviates from his own pieces of the same length at a 5% false discovery rate, plus the discriminant (the calibrated odds that the text is his rather than generic prose; off while the reference has fewer than 50 pieces). Held-out ids for the mail test are in `<profile-dir>/holdout-email-ids.json`; `fingerprint-heldout.json` is the profile built without them. `fingerprint.py prose <fingerprint> --surface email,email-personal --reference <reference> --out <profile-dir>/Voice_Profile.measured.md` renders the numbers view; pass it to `review-pack --measured <that file>`. Surfaces in the samples: `email` (work, 2015 on), `email-early` (before 2015), `email-personal` , `narrative` (saga verbatim); the two extra email registers are surfaces through `--surfaces <profile-dir>/surfaces.json` (or `PHERKAD_SURFACES`), which puts them on the shipped email overlay and picks the fingerprint basis of the same name. Design and status: `docs/measured-profile.md`, roadmap phase 6.

## Authoring from the numbers

`pherkad.py author <notes> --surface <s> --fingerprint <profile-dir>/fingerprint.json --reference <profile-dir>/reference-flattened.json --samples <profile-dir>/samples --profile-dir <profile-dir> --runner <repo>/eval/runners/claude.sh --out <file>` writes from notes in the measured voice: the packet carries the constraints the numbers impose, the archetype, and the three nearest hand-written exemplars; the runner drafts; the draft is scored (mechanical check, discriminant) and revised up to `--rounds` times, and the best is kept with its record in `<file>.author.json`. Without `--runner` it prints the packet. `eval/author_pilot.py` is the test against a bare prompt; the feature stays only while it wins there.
