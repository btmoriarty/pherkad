# Roadmap (2026-09-15)

Status, end of 2026-09-15: all thirteen items shipped, 0.5.3 through 0.5.15. What remains is not code: the saga's six prose errors, the README's two warnings, and running the two experiments on real data.

One ordered list, drawn from `docs/priority-fixes.md` (what is still wrong) and `docs/feature-review-comparison-2026-09-15.md` (what to build, and which of two reviews' designs to take). Ordered by dependency first, then by value per day. Each item names what it unblocks and how it is judged done. Effort is developer days, author review time excluded.

## Standing rules for everything below

- Stdlib Python, byte-for-byte vendoring, small overlays. No service, no package registry, no new model backend.
- Every rule change is counted against the saga corpus before it ships, and the count goes in the CHANGELOG.
- Nothing in the linters rewrites prose.
- The ban list does not grow for migrating habits; those go to the judgment layer or to corpus monitoring.

## Phase 1: foundations (unblocks everything after)

| # | Item | Depends on | Done when | Effort |
|---|---|---|---|---|
| 1 | Done, 0.5.3. **Stable rule IDs**, as additive metadata. A list entry may be a string (ID derived from the pattern) or an object `{id, pattern, rationale, since, fires, clean}`. Findings carry `rule_id`; `remove_<field>` accepts an ID; duplicate IDs are a config error; `fires`/`clean` examples are run by the test suite. | nothing | The saga overlay can remove a shipped regex by ID; `--list-rules` prints every rule with its ID; JSON findings carry `rule_id`. | 1 |
| 2 | Done, 0.5.4. **Assistant-reply preflight.** `tools/replycheck.py --surface assistant-chat -` runs both scanners over a drafted reply, with a chat-scoped overlay (personal bans, dashes, honest-X, short-reply cadence; no density, no missing-marker verdict) and a CLAUDE.md recipe: draft to a file, check, revise, return that exact buffer. A failed or skipped check is not a pass; repair attempts are bounded; the report stays out of the reply. | 1 | Used in this repository's own CLAUDE.md; a reply with a banned phrase is caught before it is shown. | 2 |
| 3 | Done, 0.5.5. **Corpus scan and release diff.** `voicelint --scan DIR [--candidate RULE_ID]` reports hits, files, rate per 1,000 words, sampled contexts; `--diff-config OLD NEW DIR` reports what a release changes on a corpus. Raw counts stay distinct from confirmed violations. | 1 | Today's hand calibration is reproducible by one command and its output is what goes in the CHANGELOG. | 3 |

## Phase 2: one runner, remembered decisions

| # | Item | Depends on | Done when | Effort |
|---|---|---|---|---|
| 4 | Done, 0.5.6. **structlint fixes**: syntactic parallel test for the two-beat check, mask spans rather than drop lines, tighten the header check; thresholds configurable; findings in the voicelint JSON shape with `rule_id`. | 1 | The three false-positive inputs in `docs/priority-fixes.md` rows 1 to 3 are silent; the true positives still fire. | 1.5 |
| 5 | Done, 0.5.7. **Shared Markdown extraction** for both tools: code, blockquotes, tables, headings, lists, directives, masked once. voicelint stops linting quoted text. | 4 | One masking function, tested once, imported by both. | 1 |
| 6 | Done, 0.5.8. **Combined runner.** `pherkad.py check --surface X --format text|json|sarif FILE...`: both engines, one finding schema, one dedup, one density over both. | 4, 5 | `lint-voice.sh` calls one command and parses one format. | 3 |
| 7 | Done, 0.5.9. **Decision file.** A project-owned record `{rule_id, path, context_hash, occurrence_count, rule_hash, disposition, reason}`; an accepted warning stays quiet until the text, the rule, or the count changes; new findings are reported separately; never auto-accept. | 6 | The saga's 294 advisory warnings can be triaged once and stay triaged. | 3 |
| 8 | Done, 0.5.10. **Release manifest and overlay check.** `bundle-manifest.json` with version, schema, hashes, rule IDs; `--check-overlay` reports `remove_` entries that match nothing; `sync-voicelint.sh` verifies against the manifest. | 1 | A downstream `remove_` for a dropped rule fails loudly. | 1 |

## Phase 3: the judgment layer and the loop

| # | Item | Depends on | Done when | Effort |
|---|---|---|---|---|
| 9 | Done, 0.5.11. **Compact judgment mode** in SKILL.md: `quick` returns `{rule_ref, quote, decision, rationale, proposed_edit}` per finding, allows "intentional" and "not applicable"; `full` keeps the seven dimensions for audits. Positive markers apply by surface; a technical reply needs no invented scene. | 2 | The skill's default run on a short draft is one table, not six fingerprint sentences and a rewrite per flag. | 1 |
| 10 | Done, 0.5.12. **Correction ledger.** `tools/corrections.py add|trial|promote` over a local JSONL `{id, before, after, context, surface, kind, rationale, rule_id, matcher, fires, clean, status, supersedes, corpus counts}`. `add` captures; `trial` runs 3 against a corpus; `promote` writes the overlay entry, the fixture cases, and the mined-corrections prose. A factual correction never becomes a style rule. | 1, 3 | A correction goes from `X -> Y` to a tested, counted rule with one approval and no hand transcription. | 6 |
| 11 | Done, 0.5.13. **Surfaces.** A small local map from surface (assistant-chat, email, fiction, paper, slides) to overlay path, guidance, and a few approved excerpts from the same series; distinguishes speaking to the author from writing as him. | 2, 9 | Every gate and every skill run names its surface; unknown surfaces are rejected, not guessed. | 2 |

## Phase 4: evidence

| # | Item | Depends on | Done when | Effort |
|---|---|---|---|---|
| 12 | Done, 0.5.14. **Revision experiment** in `eval/study.py`: same drafts, arms for untouched, generic self-review (the control), mechanical feedback, judgment feedback, both; same editing model and budget; blind rating with factual preservation required; manifest carries model, prompt, config hash, repeat. | 6, 9 | A number for whether the tools beat another editing pass, with the failures quoted. | 5 |
| 13 | Done, 0.5.15. **Detection experiment**: per-rule precision and false flags per 1,000 words for the linters; supported diagnoses, unnecessary edits, and repeat stability for the judgment layer. Protocol already in `docs/blind-eval.md`. | 12 | `docs/review-followups.md` item 2 closes. | 5 |

## Phase 5: from the review of 0.5.17 (`docs/codex-features-astra-2026-09-16.md`)

| # | Item | Depends on | Done when | Effort |
|---|---|---|---|---|
| 14 | Done, 0.5.19. **Repeated-frame check** in structlint: a syntactic template recurring across headings and subtitles, sentences, or paragraph closers; document-scoped, advisory, outside density. | 4, 7 | The pre-edit Week 3 deck and the NeurIPS paper fire; the edited deck, the saga, and this repo's docs do not. | 1 |
| 15 | Done, 0.5.20. **Judgment packet**: `pherkad.py review-pack --surface X` emits the prompt and bundle for a quick-mode run. | 11 | One command replaces the skill's context-assembly steps. | 1 |
| 16 | **Resumable eval runs**: `study.py run --jobs N` executes the judging prompts with status, validation, retries, hashes. | 13 | The 264-judgment detect pilot is an afternoon. | 1 |
| 17 | **Labelled calibration**: `corpusscan review` and `score-review`, precision per rule per surface. | 3 | A rule carries a precision number, not an impression. | 1.5 |
| 18 | **Persist judgment findings**: `pherkad.py review-import` records a quick-mode row into the decision store. | 7, 15 | A row ruled intentional stays ruled until the text changes. | 2 |
| 19 | The three weaknesses from that review: explicit scope with all evidence locations on rate findings; an implementation revision in every structural rule's hash; overlay fixtures asserted under the effective stack. | 7 | A decision cannot outlive the reason it was made. | 0.5 |

## Deferred, with the reason

- Moving `aggregator_domains` out of the voice schema: right, but it only matters to the news-brief example; do it when the surfaces land (11).
- SARIF output: cheap once the combined schema exists (6); not before.
- Multi-writer eval: after the single-author experiments (12, 13) have run once.

## Prose debt, not code

The six errors the calibrated set found in the saga (`docs/priority-fixes.md` row 6) and the three warnings in this repository's README and cheat sheet (row 10) are the author's prose and wait on him.
