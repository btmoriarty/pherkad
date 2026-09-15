# Codex feature pass on the voice tools, Astra run, 2026-09-15

Produced by `codex exec --sandbox read-only -m gpt-6-astra` at reasoning effort `ultra` (codex-cli 0.154.0, the ChatGPT app's bundled binary; the npm 0.145.0 rejects this model), against commit 4d07588. Same prompt, word for word, as `docs/codex-features-2026-09-15.md` (gpt-5.6-sol at `high`). 68,047 tokens against Sol's 123,095. The two are compared in `docs/feature-review-comparison-2026-09-15.md`.

## 1. Ranked features

Estimates are developer-days, excluding author review time. All commands and data shapes below are proposals. No files were modified.

### 1. Preflight for assistant replies

Check a buffered reply before the assistant sends it. Apply the author’s preferences for assistant speech without imposing his narrative voice on a coding update.

- **Gap:** The catalog exempts chat, while mined corrections explicitly apply to Claude’s on-screen statements. See [ai_tells.md:168](skills/pherkad/references/ai_tells.md:168) and [voice-rules.md:384](voice-rules.md:384).
- **Design:** A thin `tools/voicecheck.py --surface assistant-chat --json -` calls existing `check_counting()` and `check_text()`. Add a short assistant instruction reference covering buffering, checking, adjudicating warnings, and sending the checked revision.
- **Effort:** 2 to 3 days.
- **Noise risk:** Medium with every shipped rule; lower with chat-specific scope and advisory structural findings.

### 2. Correction capture and rule promotion

Record each correction once, with its context and intended scope. Generate a reviewable proposal containing enforcement, examples, rationale, and corpus impact.

- **Gap:** Corrections accumulate as prose bullets, while tests and config require separate transcription. [“Give it a spin”](voice-rules.md:370) illustrates why capturing the particular idiom matters.
- **Design:** `tools/corrections.py` maintains local JSONL records and offers `add`, `trial`, and `promote`. Reuse existing matchers, overlays, and test fixtures; generate the mined-corrections sections from approved records.
- **Effort:** 5 to 7 days.
- **Noise risk:** High if every edit becomes a ban; manageable with explicit classification and promotion.

### 3. Corpus reports for calibration, upgrades, and drift

Make today’s corpus calibration repeatable. Use the same scanner to preview rule upgrades and monitor changes across recent writing.

- **Gap:** The calibration evidence is currently a dated [config comment](skills/pherkad/tools/voice_config.json:214); [voice-authoring.md:75](voice-authoring.md:75) explicitly requests corpus-level vocabulary monitoring.
- **Design:** Add corpus reporting around the existing checker functions: counts, affected documents, context excerpts, and reviewed labels. Compare old/new vendored releases using the same overlay; record tool/config/corpus hashes. Report vocabulary distributions against approved writing, separated by register.
- **Effort:** 3 to 5 days.
- **Noise risk:** Low if advisory. Raw occurrence counts must remain distinct from confirmed violations.

### 4. A nightly gate that remembers reviewed warnings

Remember particular warnings the author has accepted. Require attention when the occurrence, applicable rule, or surrounding text changes.

- **Gap:** Current policy offers warnings or global `--strict`, although [structlint explicitly over-fires](skills/pherkad/tools/structlint.py:27).
- **Design:** Extend `voicecheck.py` with a project-owned decision file: `{rule_id, path, context_hash, occurrence_count, rule_hash, disposition, reason}`. Check complete changed documents, preserve whole-document checks, and report new findings separately; retain the existing bash chain and project-specific checkers.
- **Effort:** 3 to 5 days after the shared runner.
- **Noise risk:** Reduces repeated noise. Never automatically accept all existing warnings or exempt newly copied occurrences.

### 5. Evaluation of feedback effectiveness

Measure whether each checking layer improves revisions and saves the author work. Keep authoring-profile evaluation as a separate experiment.

- **Gap:** [study.py:98](eval/study.py:98) varies profiles, while [its prompts](eval/study.py:169) request self-validation in every condition.
- **Design:** Add `plan --task revise|validate` to the existing manifest, prompt, sheet, and scoring workflow. Store source IDs, treatments, repetitions, version hashes, human decisions, and editing time.
- **Effort:** 4 to 7 days, plus rating time.
- **Noise risk:** Low operationally; misleading conclusions become likely if success means only fewer lint hits.

### 6. Explicit surfaces and approved examples

Select the applicable register before drafting or checking. Supply a small set of approved examples from the same surface or series.

- **Gap:** [Voice_Profile.md:53](Voice_Profile.md:53) separates narrative and analytical registers; [voice-authoring.md:161](voice-authoring.md:161) asks for the last approved artifact.
- **Design:** A local surface manifest maps `assistant-chat`, `email`, `fiction`, `paper`, and `slides` to existing overlay paths, relevant guidance, and approved excerpts. Distinguish audience, register, and whether the assistant is speaking to Brian or writing as Brian.
- **Effort:** 2 to 3 days.
- **Noise risk:** Generally reduces it. Examples should guide style without becoming mandatory templates.

### 7. Compact judgment with recorded decisions

Offer a short review of supported changes and uncertainties for everyday use. Retain the full seven-dimension diagnostic for deliberate audits.

- **Gap:** [SKILL.md:43](skills/pherkad/SKILL.md:43) requires six fingerprint sentences, and [Step 6](skills/pherkad/SKILL.md:114) requests a rewrite for every flagged sentence.
- **Design:** Add `quick|full` review modes. Quick output contains `{rule_ref, quote, decision, rationale, proposed_edit}`; it considers mechanical findings and relevant judgment-only rules, including clean-but-generic prose. Permit “not applicable” and “intentional usage.”
- **Effort:** 2 to 4 days.
- **Noise risk:** Lower pressure to invent faults; evaluate whether shorter reviews miss broader voice drift.

## 2. From correction to tested rule

Use one record through the entire process:

```text
id, before, after, context, surface, source
kind, rationale, rule_id, matcher, exceptions
positive_cases, negative_cases, status, supersedes
corpus_hash, config_hash, hits, documents, reviewed, confirmed, rejected
```

The workflow:

1. **Capture automatically.** The assistant records the edit and nearby text when the author corrects it. Accept pasted `X -> Y` or a before/after document diff.
2. **Classify.** Route it to literal rule, contextual warning, judgment guidance, positive preference, factual correction, or exception. A factual correction should not create a style rule.
3. **Propose.** Reuse an existing rule where possible. Generate a narrow matcher, rationale, rejected example, accepted replacement, and legitimate near-misses.
4. **Trial.** Run the candidate against the chosen corpus. Show hit count, document count, new findings versus current rules, and context excerpts for author labeling.
5. **Approve one packet.** The author confirms scope and treatment together. Frequency alone cannot justify an error-level rule.
6. **Promote.** Generate the overlay change, regression cases, and mined-correction entry. Keep candidate-specific assertions: the accepted replacement need only stop triggering that rule.
7. **Track disposition.** Every correction becomes `enforced`, `judgment-only`, `preference`, `pending`, or `retired`.

Attach stable IDs through additive metadata while preserving string lists and `add_`/`remove_` compatibility. Downstream projects can continue vendoring identical release files.

Keep unseen documents outside rule development. Passing examples extracted from the correction proves implementation, not generalization.

## 3. Checking chat output

**Feasible immediately:** Both scripts already accept stdin. The assistant can prepare a reply, run both, review supported findings, revise, recheck, and send those exact checked bytes.

For the feature:

- Check assistant-authored prose; preserve code, commands, logs, paths, and attributed quotations.
- Include commentary as well as final replies where buffering is practical.
- Bound repair attempts; do not force structural warnings to zero.
- Keep check reports out of the reply unless relevant.
- Treat a failed or skipped check as unperformed, never as a pass.

**Enforcement limit:** Shell access supports cooperative checking. Python cannot intercept already streamed text or guarantee the assistant invokes it; compulsory checking requires a host-provided pre-send interception point.

## 4. Evaluation changes that answer the useful questions

### Revision experiment

Create each source draft once, freeze its profile, and compare:

| Treatment | Purpose |
|---|---|
| Untouched draft | Original reference |
| Generic self-review | Controls for another editing pass |
| Both linters’ feedback | Measures mechanical feedback |
| Judgment feedback, mechanical calls disabled | Measures model review |
| Both layers | Measures the combined workflow |

Use the same editing model and revision budget. Blind the author to treatment.

**Primary outcome:** Preference over generic self-review, with factual preservation required. Also record useful edits, unnecessary edits, author editing time, repair iterations, and cost. A passing nightly gate is a process outcome, not proof of better prose.

### Detection experiment

Use held-out approved prose, rejected/corrected pairs, technical exceptions, deliberate stylistic choices, and meaning-preserving flattened drafts.

- **Linters:** Per-rule precision, recall on independently labeled violations, and false flags per 1,000 words.
- **Judgment:** Supported diagnoses, unnecessary proposed edits, recognition of unusual authentic prose, and verdict/reason stability across repeated runs.
- **Recognition controls:** Correct/wrong/no-profile comparisons on a smaller subset.

Extend manifest items with `source_id`, `surface`, `treatment`, `repeat`, and provenance hashes; extend ratings with separate factual, certainty, caricature, usefulness, and time fields. Reuse the existing blind sheets and CSV workflow.

Start with this author’s chat, email, fiction, and technical writing. Report uncertainty across source documents or series; reserve the multi-writer study for broader claims. Much of the desired measurement is already specified in [docs/blind-eval.md:64](docs/blind-eval.md:64).

## 5. Replace rather than extend

- **Manual transcription into three places:** Generate learned prose sections, config additions, and fixtures from approved correction records.
- **Global strictness as warning policy:** Use explicit occurrence decisions and rule-specific blocking.
- **Mandatory full scoring and rewriting every flag:** Default to compact adjudication.
- **Blanket chat exemption:** Replace it with explicit assistant-chat applicability.
- **Unconditional scene insertion:** Apply positive markers by surface; technical replies need no invented scene.
- **More phrase bans for migrating habits:** Route functional patterns to judgment and recurring preferences to corpus monitoring.
- **Entangled eval prompts:** Make authoring, linting, judgment, and revision separately selectable stages.

Keep stdlib execution, byte-for-byte vendoring, and small overlays. These features do not require a service, package registry, or new model backend.
