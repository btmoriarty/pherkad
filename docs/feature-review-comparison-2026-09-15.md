# Two feature reviews compared (2026-09-15)

The same prompt, read-only over the same tree, to two Codex models: gpt-5.6-sol at `high` (`docs/codex-features-2026-09-15.md`, 123K tokens) and gpt-6-astra at `ultra` (`docs/codex-features-astra-2026-09-15.md`, 68K tokens). Neither modified a file. This note lines them up and says which version of each idea to build.

## Where they agree

Five of the seven features on each list are the same feature under a different name. The order differs.

| Feature | Sol rank, effort | Astra rank, effort | Difference in the design |
|---|---|---|---|
| Correction ledger: capture `X -> Y` once, classify, trial against a corpus, promote to config, fixtures, and the mined-corrections prose | 1, 6 to 9 days | 2, 5 to 7 days | Same record shape and the same seven-step loop. Astra adds a `supersedes` field, a `factual correction` class that must not become a style rule, and the rule that the accepted replacement need only stop triggering that one rule. |
| Assistant-reply preflight: check a drafted reply buffer with both scanners before it is shown | 2, 2 to 4 days | 1, 2 to 3 days | Sol scopes it to personal bans, dashes, and short-reply cadence, with no density verdict. Astra adds three operating rules: a failed or skipped check counts as not performed, never as a pass; bound the repair attempts; keep the check report out of the reply. Both say enforcement is cooperative only, since nothing can intercept text already streamed. |
| Corpus calibration and drift reports | 4, 4 to 6 days | 3, 3 to 5 days | Same command, same outputs (hits, files, rate per 1,000 words, sampled contexts, before/after). Astra adds comparing two vendored releases under the same overlay, and separating raw occurrence counts from confirmed violations. |
| Explicit surfaces (assistant chat, email, fiction, paper, slides) | 5, 4 to 6 days | 6, 2 to 3 days | Sol builds a layered manifest (base, author, project, surface) with structlint thresholds inside it and the resolved config hash in output. Astra keeps a small local map from surface to overlay path, guidance, and approved excerpts from the same series, and asks the one question Sol does not: is the assistant speaking to the author or writing as him. |
| Eval: a revision experiment in addition to the authoring study | 6, 8 to 12 days | 5, 4 to 7 days | Both randomise the same drafts across no feedback, mechanical feedback, judgment feedback, and both. Astra adds a generic self-review arm as the control, which is the arm that decides whether the tools beat another editing pass, and states that a passing gate is a process outcome, not proof of better prose. |

Both say the same things to replace: stop using the mined-corrections prose as the transaction log and generate it from the ledger; take the blanket chat exemption out of `ai_tells.md`; make the eval stages separately selectable.

## Where only one of them has it

| Only in Sol | Only in Astra |
|---|---|
| A combined checker with one finding schema and one dedup and density pass (`pherkad.py check --format text/json/sarif`). Astra assumes "the shared runner" exists in its item 4 without listing it. | A nightly gate that remembers reviewed warnings: a project-owned decision file `{rule_id, path, context_hash, occurrence_count, rule_hash, disposition, reason}` so an accepted warning stays quiet until the text, the rule, or the count changes. |
| Downstream lockfiles and differential baselines: a bundle manifest with hashes and rule IDs, `vendor verify`, `rules diff`, `baseline create/check` in new-findings-only mode. | A compact judgment mode: `quick` returns `{rule_ref, quote, decision, rationale, proposed_edit}` and allows "not applicable" and "intentional"; `full` keeps the seven dimensions for deliberate audits. Reduces the skill's pressure to invent a fault for every flag. |
| Compile the legacy JSON from ID-bearing rule objects. | Attach IDs as additive metadata and keep the string lists and `add_`/`remove_` compatibility, so downstream vendoring does not change. |
| Move `aggregator_domains` out of the voice schema. | Stop growing the phrase-ban list for migrating habits; route functional patterns to judgment and recurring preferences to corpus monitoring. |
| | Apply positive markers by surface; a technical reply needs no invented scene (a direct challenge to a rule in `voice-authoring.md`). |

## Where they disagree and which to take

| Question | Sol | Astra | Take |
|---|---|---|---|
| Rule IDs | Compile the JSON from rule objects | Add IDs as metadata beside the existing arrays | Astra. The saga vendors the JSON byte for byte and the `add_`/`remove_` contract is in use; a compiled format breaks both for no gain the ID alone does not give. |
| Old warnings in a legacy corpus | A baseline of debt that expires or stays visibly counted | A per-occurrence decision with a reason, invalidated when the text or rule changes | Astra. It records why, which is the review-record habit already used elsewhere, and it fails closed on change. Sol's release manifest and `rules diff` are still worth having under it. |
| Whether to keep adding bans | Neutral | Against, beyond the mechanically safe ones | Astra, and today's own calibration is the evidence: the boosters added 58 warnings to the saga in one release, all of them in dialogue. |
| The judgment layer | Not addressed | Add a quick mode | Astra. It is a change to SKILL.md, costs almost nothing, and it is the layer that actually runs on the author's drafts. |
| What comes first | The ledger | The preflight | Astra. The preflight is two days, it needs only the two scripts that exist, and it addresses the one gap the author has named repeatedly. The ledger is the larger build and depends on rule IDs. |

## The order to build

1. Rule IDs as additive metadata (both reviews need them; it is row 8 of `docs/priority-fixes.md`).
2. Assistant-reply preflight, with Astra's three operating rules and Sol's narrow scope.
3. Corpus scan and release diff, so every later rule change is counted the way today's was.
4. The combined runner (Sol) carrying the per-occurrence decision file (Astra).
5. Compact judgment mode in SKILL.md.
6. The correction ledger, on top of 1, 3, and 4.
7. Surfaces, then the revision experiment.

Astra's list is the cheaper one (21 to 34 days against 30 to 47) and reuses more of what exists. Sol's combined runner and release manifest are the two pieces worth taking from the longer list.
