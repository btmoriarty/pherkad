# Codex feature pass on the voice tools, 2026-09-15

Produced by `codex exec --sandbox read-only` (gpt-5.6-sol, reasoning high) against commit 477f437, after the 0.5.1 and 0.5.2 releases. Prompt: propose features, not fixes, given how the tools are used in practice (byte-for-byte vendoring with overlays, the 200-file downstream gate, corrections transcribed by hand into voice-rules.md, and no check at all on assistant chat replies). Companion to `docs/codex-review-2026-09-15.md` (bugs) and `docs/priority-fixes.md` (what remains).

The best return comes from shortening the path between a rejected phrase and enforceable policy, then putting that policy in the assistant’s reply path.

## Ranked features

### 1. Structured correction ledger and rule compiler

Capture each `X  then  Y` correction once as a candidate rule, then compile approved candidates into config, tests, and prose documentation. Keep candidates inactive until corpus evidence and negative examples support promotion.

- **Gap:** Corrections are hand-written into mined sections such as [voice-rules.md](voice-rules.md:363) and [voice-authoring.md](voice-authoring.md:167), while the skill only describes appending false-positive corrections to the profile at [SKILL.md](skills/pherkad/SKILL.md:172). Config entries have no stable ID, rationale, provenance, replacement, or examples ([voice_config.json](skills/pherkad/tools/voice_config.json:6)).
- **Design:** Add `corrections.jsonl` records shaped as `{id, before, after, context, surface, rationale, date, disposition, rule_kind}`. A `corrections.py propose|scan|approve` command classifies each as literal, templated, structural, judgment-only, or authoring-only; approval generates the overlay entry, fixture cases, and rendered mined-correction prose.
- **Effort:** 6 to 9 days.
- **Noise risk:** Medium. A single edit can be overgeneralized; require explicit scope, negative controls, corpus review, and approval before enforcement.

### 2. Assistant-reply preflight

Ship a small command and ready-to-paste assistant instruction that check the exact reply before it is shown. This targets coding-assistant chat without pretending ordinary informal human chat should use the same policy.

- **Gap:** The catalog explicitly exempts informal chat ([ai_tells.md](skills/pherkad/references/ai_tells.md:168)), even though assistant replies are the principal source of rejected phrasing in practice. The current workflow only checks submitted drafts.
- **Design:** `python3 tools/replycheck.py --surface assistant-reply FILE|-` reads the candidate once, runs both existing scanners, and emits a compact result. Include an `AGENTS.md`/`CLAUDE.md` recipe: draft into a temporary buffer, run preflight, revise, then return that exact buffer; do not rely on the model shell-escaping arbitrary prose into a command.
- **Effort:** 2 to 4 days.
- **Noise risk:** Medium. Short technical replies contain literals and quoted material; use a dedicated surface that enforces personal hard bans but disables irrelevant density and public-prose expectations.

### 3. One combined checker and finding schema

Provide one entry point for regex, structural checks, deduplication, density, and exit status. Preserve the two scanners internally, but make downstream consumers integrate one contract.

- **Gap:** The skill invokes two commands and asks the model to deduplicate them manually ([SKILL.md](skills/pherkad/SKILL.md:78)). Their findings have different shapes ([voicelint.py](skills/pherkad/tools/voicelint.py:99), [structlint.py](skills/pherkad/tools/structlint.py:164)), and document-level density is calculated in multiple places.
- **Design:** `pherkad.py check [--surface X] [--format text|json|sarif] FILE...`; import `check_counting()` and `check_text()`. Normalize to `{rule_id, engine, severity, file, line, col, excerpt, rationale, replacement, surface}`, deduplicate once, and calculate combined density/clusters once.
- **Effort:** 3 to 5 days.
- **Noise risk:** Low. It adds no detection; risk comes only from accidentally changing strict-mode semantics, so preserve current defaults.

### 4. Corpus calibration and drift reports

Add a reporting command that measures a candidate or released rule against real corpora before it becomes a gate. Use the same command to monitor vocabulary ratios and recurring assistant tics over time.

- **Gap:** Corpus monitoring is prescribed but not implemented ([voice-authoring.md](voice-authoring.md:75)); today’s config records one calibration narratively rather than reproducibly ([voice_config.json](skills/pherkad/tools/voice_config.json:214)).
- **Design:** `pherkad.py scan CORPUS --candidate RULE_ID` reports matches, files affected, rate per 1,000 words, sampled contexts, and before/after counts. `pherkad.py trend snapshots/*.json` tracks counts and weighted preferences; snapshots retain counts, versions, and hashes rather than corpus prose.
- **Effort:** 4 to 6 days.
- **Noise risk:** Low. It is advisory; its purpose is to prevent noisy rules from shipping.

### 5. Explicit surface policies

Let callers select named policies for assistant replies, fiction, email, papers, slides, and general prose. Do not infer the surface from the text.

- **Gap:** `voice-rules.md` carries substantial surface-specific policy beginning at [line 269](voice-rules.md:269), while `voicelint` accepts one overlay and `structlint` keeps thresholds and patterns in code ([structlint.py](skills/pherkad/tools/structlint.py:52)).
- **Design:** Add a small `pherkad.json` manifest with layered `base  then  author  then  project  then  surface` overlays and `structure` settings. Require `--surface` in automated gates; include the resolved surface and configuration hash in output.
- **Effort:** 4 to 6 days.
- **Noise risk:** Medium. Selecting the wrong surface changes legitimate findings; reject unknown or ambiguous selections rather than guessing.

### 6. Validation and intervention evaluation modes

Turn `study.py` into an experiment harness for three separate claims: authoring captures voice, validation distinguishes voice, and feedback improves a draft. The current authoring study remains one experiment type.

- **Gap:** The harness implements correct/wrong/none authoring with one rater and one run; it explicitly leaves validation cases, repeated runs, and multiple readers manual ([eval/README.md](eval/README.md:33)). Its scorer currently calculates only condition means and correct-profile lift ([study.py](eval/study.py:310)).
- **Design:** Add declarative experiment manifests, `authoring|validation|intervention` case types, repeated model runs, multiple raters, and import of structured judgment reports. Score writer-level paired lift, confusion cases, stability, agreement, factual fidelity, false-edit burden, and improvement from feedback.
- **Effort:** 8 to 12 days.
- **Noise risk:** None operationally; medium methodological risk if conditions or primary outcomes are chosen after seeing results.

### 7. Downstream lockfiles and differential baselines

Give vendored consumers a supported way to verify exact tool versions and adopt new rules without making every historical file fail immediately. Nightly generated prose can remain fully strict while legacy corpora use new-findings-only mode.

- **Gap:** Consumers currently maintain their own copying, hashing, and bash orchestration. There is no stable rule ID with which to baseline or explain changes across releases.
- **Design:** Publish `bundle-manifest.json` containing version, schema version, file hashes, and rule IDs. Add `vendor verify`, `rules diff`, and `baseline create|check`; baseline signatures should use `{path, rule_id, normalized-context-hash}` and report retained debt on every run.
- **Effort:** 3 to 5 days.
- **Noise risk:** Low; the larger danger is hiding old findings, so baselines should expire or remain visibly counted.

## Correction-to-enforcement loop

The minimal-hand-work path should be:

1. The assistant receives `X  then  Y` plus the surrounding sentence and surface.
2. It runs `corrections.py capture`, producing an immutable candidate record.
3. A proposal pass supplies the likely family, rationale, scope, replacement, and rule kind. It does not activate the rule.
4. `scan` counts occurrences across the author corpus and downstream corpus, reports affected files, and samples contexts.
5. The tool generates three fixture classes:
   - `X` must fire.
   - `Y` must not fire.
   - Plausible literal or nearby uses must not fire.
6. The author approves, narrows, or marks it judgment-only. That is the only required decision after supplying the correction.
7. `approve` compiles the appropriate config or structural rule, test fixtures, rationale entry, and downstream rule diff.
8. Suppressions and later rejected hits feed back as evidence for narrowing or demotion.

Corrections that describe meaning, invented facts, register, or anthropomorphism should remain judgment rules. Forcing them into regex would increase noise and give a misleading sense of coverage.

## Chat-output boundary

For shell-capable coding assistants, pre-delivery checking is feasible: check a completed reply buffer, revise it, and return that exact buffer. A post-output hook can collect evidence but cannot prevent the already-visible reply; hosted chat systems without a draft hook or shell cannot be covered mechanically.

The assistant-reply policy should initially enforce:

- Personal phrase bans and known correction families.
- Dashes and mechanically safe positional checks.
- Structural cadence checks that work on short replies.
- No general “missing positive marker” verdict and no density judgment on short technical answers.

The full model-based judgment layer is too expensive and unstable to run before every small reply. Reserve it for longer replies or explicit voice checks.

## Eval changes needed

Use two independent studies in addition to the current authoring arm:

- **Detection study:** Authentic holdouts, atypical authentic pieces, preserved-fact flattenings, matched impostors, and override samples under correct, wrong, shuffled, absent, and linter-only profiles. Repeat each judgment at least three times and capture the exact model, prompt, profile hash, tool hash, dimension scores, cited evidence, findings, and verdict.
- **Intervention study:** Randomize the same starting drafts to no feedback, regex feedback, structural feedback, combined mechanical feedback, judgment report, and all feedback. Have an independent editor revise from the assigned report, then rate outputs blind for voice, factual fidelity, unnecessary edits, accepted recommendations, and editing time.
- **Linter-specific calibration:** Maintain labeled positive and negative examples per rule and report precision, hits per 1,000 words, suppression rate, and downstream corpus impact. Do not claim recall over “AI-speak”; measure recall only for explicitly labeled rule families.
- **Analysis:** Writer is the unit; use paired comparisons and writer-clustered intervals. Publish failures and unstable explanations, not only pooled lift.

## Replace rather than extend

- Replace free-form mined-correction appendices and separate config editing with generated views from the correction ledger. Keep the interpretive prose, but stop using it as the transaction log.
- Stop adding anonymous strings directly to config arrays. Compile the legacy JSON from rules with stable IDs, rationale, scope, provenance, examples, and replacements.
- Remove document-level density and cross-engine deduplication from individual scanners; put them in the combined runner.
- Move `structlint` thresholds and surface-dependent patterns out of module constants and into the same resolved policy used by `voicelint`.
- Move `aggregator_domains` out of the voice schema into a project/source-quality checker; the config itself already acknowledges it is not voice policy ([voice_config.json](skills/pherkad/tools/voice_config.json:212)).
- Do not add automatic prose rewriting to the linters. Safe substitutions can be emitted as suggestions, but the existing meaning-preservation guardrail requires review.

No files were modified.
