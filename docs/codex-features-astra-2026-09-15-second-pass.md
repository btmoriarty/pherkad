# Codex feature pass on 0.5.15, Astra, second attempt, 2026-09-15 evening

Run with `codex exec --sandbox read-only -m gpt-6-astra` at reasoning effort `ultra` (codex-cli 0.154.0) against commit `2616634`, with a prompt that named everything shipped in 0.5.1 through 0.5.15 and asked for the next features, which judgment findings from the two lecture decks could become mechanical, what is weak in what shipped, and the smallest real run of the two experiments. The prompt is kept below.

**The run did not finish.** After 97,113 tokens of reading (the changelog, every tool, the tests, the eval harness) it hit the account's Codex usage limit and stopped before writing its report; the limit resets at 12:08 AM on 2026-09-16. No ranked list was produced. Its test runs failed for a sandbox reason (no writable temporary directory), not a code reason; every suite passes here.

## What it did say, verbatim, in its interim messages

1. "I'll read the changelog first, then split the code review while I run the tests and check the repository's docs with the tools. I'll keep recommendations separate from anything already shipped."
2. "The roadmap marks all thirteen items shipped. I'm checking whether the new pieces work together, especially decisions, surface-aware calibration, and evaluation runs."
3. "The test commands hit a sandbox limit: temporary directories cannot be created. The Markdown suite passed, and other suites ran some read-only cases before fixture setup failed; I'll report those separately and use in-memory probes for the integration checks."
4. "A reproduced integration bug affects the gate: structural findings marked advisory still feed a blocking density warning. Deciding every local finding also leaves that density warning active. The evaluation scorer has a similar problem: it drops revisions with fidelity failures from the primary average, which can make an unreliable arm look better."

## What was done with it

Message 4 was verified and fixed the same evening, as 0.5.16: the combined density is computed over the findings that count (not advisory, not decided), and the revision scorer's primary contrast scores a flagged draft as 1 rather than dropping it. A third defect surfaced while testing the fix: a decision record covered only the occurrences on the line named, not every line in the file with the same text; `decide` now counts all of them.

The rest of the prompt is unanswered. Re-run after the limit resets.

## The prompt

You are reviewing the repository at /Users/moriarty/Documents/kochab/pherkad, read-only. Do not modify files.

Pherkad is a writing-voice toolkit for one author who uses AI assistance for most of what he writes. Read CHANGELOG.md first: versions 0.5.1 through 0.5.15 all shipped on 2026-09-15 in response to two earlier Codex reviews (docs/codex-review-2026-09-15.md, docs/codex-features-2026-09-15.md, docs/codex-features-astra-2026-09-15.md, docs/feature-review-comparison-2026-09-15.md), and docs/ROADMAP.md records all thirteen roadmap items as done. Do not propose anything those documents already list as shipped; verify against the code, not the prose, if you doubt a claim.

What now exists, in skills/pherkad/tools/: voicelint.py (phrase linter, stable rule ids, id-bearing rule objects with fires/clean examples), structlint.py (shape checks, thresholds in config), mdmask.py (one reading of Markdown structure for both), pherkad.py (the combined runner: one schema, one dedup, one density, text/json/sarif, --advisory, a per-occurrence decision file with decide/decisions/--prune, surfaces with --surface and a user surfaces.json, a release manifest with --verify, check-overlay that runs overlay fixtures), replycheck.py and replycheck-hook.py (assistant-reply preflight and a Claude Code Stop hook, installed and in use), corpusscan.py (per-rule corpus counts, candidate trials, release diffs), corrections.py (a JSONL ledger: add / trial / promote, generating the overlay entry, its fixtures, and the mined-corrections prose line). In eval/: study.py with three tasks (author, revise, detect) and detect.py, with provenance on every item and a preregistration file. The skill (SKILL.md) has a quick mode (one table, one verdict) and names its surface. A downstream fiction project vendors six files plus the surfaces via a sync script that verifies sha records, the manifest, and its overlay; its gate runs one pherkad.py check with structural findings advisory.

How it is used: the author writes in Claude Code sessions; every reply he receives is preflighted and hook-checked under the assistant-chat surface; his own prose is checked under email, post, paper, slides, or technical; the fiction corpus (202 files, ~275k words) is the calibration corpus every rule change is counted against; corrections he makes go into the ledger. Today the tools were used for the first time on two real lecture decks (slides surface): the mechanical layer found nothing on either, and the model's judgment pass found the same two things on both, a recurring "X, not Y" antithesis frame across five or six slide titles, and presenter narration ("We read what comes back") in student-facing slides. Both decks were fixed at the source and rebuilt.

Ignore _to_delete/, *.bak*, __pycache__, .pytest_cache, pherkad.rebuilt.skill, zi6TDEjL, eval/data/.

Task: propose the NEXT features. Read the code and the docs, run the test suites (python3 skills/pherkad/tools/test_*.py and python3 eval/test_study.py), and try the tools on the repository's own docs. Then report:

1. The five to eight features that would most increase the tools' value now, ranked. For each: what it is in two sentences, the concrete gap in a named file or a named workflow, a design sketch (interfaces, data shapes, where it lives, what it reuses), effort in days, and the risk of noise. Prefer features that reuse what exists.
2. The judgment layer found what the linters could not on two real decks (cross-slide repetition of a frame; narration). Which of those findings could become mechanical, in structlint or a new document-level checker, and which should stay judgment? Sketch the mechanical ones.
3. What is weak or wrong in what shipped today. Be specific: a design that will not scale, a schema that will need to change, an abstraction in the wrong place, a test that proves less than it looks like it proves, a docstring that overclaims. Cite file and line.
4. The two experiments (eval/study.py revise and detect) have never been run on real data. What is the smallest run that would produce a number worth reporting, and what in the harness would make that run harder than it should be?
5. Anything that should be removed or replaced rather than extended.

Be specific and terse. No praise. Do not restate what the project does.
