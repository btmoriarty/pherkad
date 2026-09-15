# Changelog

## v0.5.12 (2026-09-15)

Item 10 of `docs/ROADMAP.md`, the correction ledger.

- **`tools/corrections.py`**, new. A JSONL ledger, project-owned and never committed here, one record per correction: before, after, context, source, surface, kind, rationale, the proposed field and matcher, the examples, the trial, the status, and a history. `add` records a correction and classifies it (literal, templated, structural, judgment, preference, factual, exception; `--kind` overrides the guess), proposing the matcher and a `fires`/`clean` pair from the context. `trial` counts the candidate on a corpus with the pattern alone (under the full set a shipped rule wins a shared span on a tie and the candidate looks silent), stores hits, files, rate, and contexts on the record, checks the examples, and names any shipped rule that overlaps. `promote` refuses an untrialled rule, refuses a factual correction however often it recurs, and otherwise writes the overlay entry (an `add_<field>` object with id, rationale, since, fires, clean), which is where the fixtures live, and appends the mined-corrections line under a dated, sourced heading in the prose file; a judgment or preference kind gets the prose line only. `list`, `show`, `retire`.
- **The prose is generated from the record.** The ledger is the transaction log; the mined-corrections section is a view of it.
- **`pherkad.py check-overlay` runs an overlay's fixtures**, each rule alone, so a promoted correction's tests run wherever the overlay is checked.
- A promotion into the shipped base joins the list itself rather than an `add_`; the tool says to write the manifest, count it, and record it.
- `tools/test_corrections.py`, 16 tests, in CI. `corrections.jsonl` is gitignored beside the personal voice documents.
- `VERSION` 0.5.12.

## v0.5.11 (2026-09-15)

Item 9 of `docs/ROADMAP.md`, the compact judgment mode. A change to the skill's instructions, not to code.

- **Quick mode is the default depth of validation.** `SKILL.md` gains Step 0b (choose quick or full) and a Quick mode section: one run of `pherkad.py check --format json`, one read of the draft for the judgment-only rules that apply to its surface, and one table with a row per finding: `rule_ref`, `quote`, `decision`, `rationale`, `proposed_edit`. Decisions are `fix`, `intentional`, `literal`, `not applicable`, or `quoted`; only a `fix` row carries an edit. The verdict is one line. Nothing is scored, no fingerprint is produced, and nothing is rewritten that was not flagged. A confirmed `intentional` or `literal` row in a project with a decision file is recorded with `pherkad.py decide`.
- **Full mode is the audit**, Steps 1 through 6 unchanged, for a paper, an essay, a chapter, an explicit request for scores, or a quick pass that found the voice missing across the piece.
- **Positive markers apply by surface.** A table in Quick mode says where the positive register is expected: not in an assistant's reply, a technical answer, a bug report, a commit message, or a status email; in the frame and close of a post or letter; in the frame and transitions of a paper; never from the personal profile in fiction, which has its own voice document. `references/authoring.md` rule 5 says the same from the drafting side: a scene added to a technical answer to fit the profile is worse than none.
- **The blanket chat exemption is gone.** `references/ai_tells.md` now exempts informal messages between people, and names an assistant's reply as the `assistant-chat` surface, checked by `replycheck.py` and judged in quick mode.
- Step 3 of full mode runs `pherkad.py check --format json` once instead of two commands. The cheat sheet gains rows for the quick check, the combined CLI, and the reply preflight.
- `VERSION` 0.5.11.

## v0.5.10 (2026-09-15)

Item 8 of `docs/ROADMAP.md`, the release manifest and the overlay check, which closes row 12 of `docs/priority-fixes.md` and phase 2 of the roadmap.

- **`tools/bundle-manifest.json`**, new, written by `pherkad.py manifest --write` at release: the version, a schema number, the sha256 of every vendored file (the five a gate needs, plus replycheck, its hook, corpusscan, and the surfaces), and every rule id the shipped base runs. `pherkad.py manifest --verify` fails when a file beside the script no longer matches, when a file is missing or unlisted, when the version differs from `VERSION`, or when the rule ids differ from the shipped config. CI runs it, so a release that edits a tool and forgets the manifest fails its own tests; the first run of the test did exactly that.
- **`pherkad.py check-overlay OVERLAY`** loads a downstream overlay on the shipped base and reports what would silently do nothing: a `remove_<field>` naming a rule that is not here (error), an `add_<field>` duplicating a shipped rule (warning), a whole-list replacement where `add_`/`remove_` would inherit (warning), a structure key the base does not know (config error). The saga overlay checks clean; the shipped `assistant-chat` surface checks clean.
- **The saga's `sync-voicelint.sh --check`** now verifies three things: the six vendored files against its own sha record, pherkad's manifest against the copies, and the saga overlay against the vendored base. Any one failing exits non-zero, and `lint-voice.sh` reports it at the top of every run.
- `test_pherkad.py` grows by 10 cases.
- `VERSION` 0.5.10.

## v0.5.9 (2026-09-15)

Item 7 of `docs/ROADMAP.md`, the decision file, which closes row 7 of `docs/priority-fixes.md` by giving a downstream corpus a way to triage its advisory warnings once.

- **`pherkad.py check --decisions FILE`** hides, and stops counting, every finding the author has ruled on. A decision is a record `{rule_id, path, context_hash, rule_hash, count, disposition, reason, decided}`: the context is the whole line the finding sits on with whitespace collapsed, the rule hash is the rule's pattern, and the record covers up to `count` occurrences on that line. A changed line, a changed rule, or an extra occurrence makes the finding new again. `--show-decided` prints the hidden ones; the summary reports `N decided (a accepted, b intentional, c deferred)` so the debt stays visible; `--format json` carries each finding's decision and `--format sarif` omits decided findings. Paths are relative to `--root`, default the decision file's directory.
- **`pherkad.py decide --decisions FILE --reason "..." path:line[:rule_id]`** is the only thing that writes a decision, and it refuses an empty reason and a location with no finding. Dispositions: `accepted` (the author's usage), `intentional` (a deliberate choice), `deferred` (known, fix later). Deciding a line covers every occurrence of that rule on it; naming a rule id covers that rule only.
- **`pherkad.py decisions --decisions FILE FILES...`** reports which records still match and why the others do not (line changed or finding gone, rule changed, rule gone); `--prune` drops the stale ones and nothing is pruned without it.
- **The saga gate passes `--decisions voice-decisions.json --root <repo>`** when that file exists at the repo root. It does not exist yet; the 293 advisory warnings and 6 errors there are the author's to rule on, one `decide` at a time, and nothing in the tool rules on them for him.
- `test_pherkad.py` grows by 11 decision cases.
- `VERSION` 0.5.9.

## v0.5.8 (2026-09-15)

Item 6 of `docs/ROADMAP.md`, the combined runner.

- **`tools/pherkad.py check`**, new. Runs voicelint and structlint over each file, folds the findings into one list in one schema (line, col, severity, rule, match, message, rule_id, engine), removes the overlap between the engines, computes one density over both, and prints one format: text, `--format json` (voicelint's envelope plus tool version, config sha256, and the advisory prefixes), or `--format sarif` (SARIF 2.1.0, advisory findings as `note`). `--advisory PREFIX` reports rule ids under a prefix without counting them, which is how a gate keeps the structural checks visible but non-blocking; `--strict`, `--no-structure`, `--quiet`, `--surface`, `--config`, and `-` for stdin as elsewhere. Exit codes are voicelint's. `pherkad.py rules` lists every rule both engines run.
- **Density is computed once**, over both engines' findings, against `structure.density_per_100`; structlint's own per-document density is dropped from the combined list. **Overlap**: a structlint `header` finding whose heading contains the text of a voicelint finding on the same line is the same tell twice, and the voicelint one, which names the rule, is kept.
- **`replycheck` runs on the shared core** (`pherkad.run_text`) and splits by engine; its verdict and output are unchanged.
- **The saga gate calls one command.** `lint-voice.sh` runs `pherkad.py check --config <overlay> --advisory structure.` in place of the separate voicelint and structlint steps, and no longer resolves a world-specific structlint path. `sync-voicelint.sh` vendors five files: `pherkad.py`, `voicelint.py`, `structlint.py`, `mdmask.py`, `voice_config.json`. The whole-tree run reports 6 errors, 293 warnings, 116 advisory, the same numbers the two steps gave.
- `tools/test_pherkad.py`, 16 tests, in CI.
- `VERSION` 0.5.8.

## v0.5.7 (2026-09-15)

Item 5 of `docs/ROADMAP.md`, the shared Markdown extraction layer, which closes row 4 of `docs/priority-fixes.md`.

- **`tools/mdmask.py`**, new. One reading of Markdown structure for both linters: `line_kinds(text)` classifies every line (code, blockquote, table, heading, field, list, blank, prose) and `mask(text, kinds)` blanks the named kinds, and inline code spans, to same-length whitespace so offsets never move. Fences are backtick or tilde, three or more, closed by a fence of the same character at least as long, or by the end of the file; a `>` inside a fence is code.
- **voicelint imports it** and now masks blockquotes as well as code. A quoted passage is someone else's words, which voice-rules.md exempts, and structlint already skipped it; the two tools no longer disagree on what is prose. Inline quotation marks are still linted: in fiction the dialogue is the author's voice, and adjudicating a direct quote stays with the judgment layer. On the saga corpus no finding sat on a blockquoted line, so voicelint's count is unchanged at 6 errors and 293 warnings.
- **structlint imports it** for code, blockquote, table, heading, field, and list detection, and drops its own copies of those regexes and its unused `QUOTED` constant. One consequence: an inline code span now keeps its width when a sentence is measured, where the old stripper collapsed it to one space, so a sentence that was only "short" because its code collapsed no longer counts. Two staccato findings on the saga corpus went away for that reason (118 to 116); both were sentences carrying a code span.
- The saga's `sync-voicelint.sh` vendors `mdmask.py` beside `voicelint.py`; a vendored voicelint without it fails at import, loudly, rather than running with less.
- `tools/test_mdmask.py`, 14 tests, in CI; voicelint gains cases for blockquote masking and for inline quotation staying prose.
- `VERSION` 0.5.7.

## v0.5.6 (2026-09-15)

Item 4 of `docs/ROADMAP.md`, the structlint fixes, which close rows 1, 2, 3, and 9 of `docs/priority-fixes.md`.

- **The two-beat check tests shape, not length.** Two short sentences count as a parallel only when they share an opener, both carry a negation, share a closing word, or have the same token count with a repeated content word. "The meeting starts at nine. Lunch follows at noon." no longer fires; "None of them wrong. None of them ours." still does. On the saga corpus two-beats went from 31 to 12, and every one of the 19 that vanished was an ordinary pair.
- **Spans are masked, lines are kept.** A URL, a DOI, an arXiv id, a year in parentheses, a page run, or a long quoted span is blanked in place and the rest of the line is still checked, so a staccato run beside a link is visible. A whole bibliographic entry (author-and-initial opener, or two or more markers) is still dropped as before.
- **Two header patterns tightened.** `The real X` and `The actual X` fire only on a stance noun (problem, question, issue, reason, point, story, answer, and so on), so `The actual results` is left alone; `Where X sits` needs an abstract or pointer subject (`Where this sits`, `Where Stage 3 Sits`, `Where the argument stands`), so `Where the chair sits` is a chair.
- **Thresholds are configurable**, in the same file voicelint reads, under a `structure` object with the same overlay semantics: `short_chars`, `two_beat_diff`, `staccato_run`, `density_per_100`, `interrogative_pct`, `interrogative_min`. The shipped `voice_config.json` carries the defaults; `structlint --config OVERLAY` and `replycheck` pick up an overlay's values; voicelint validates the object and rejects an unknown threshold.
- **Findings carry voicelint's shape**: line, col, severity, rule, match, message, rule_id, with ids `structure.<check>`. The text line reads `path:line:col [warning] two-beat (structure.two-beat): ...` and `--json` uses voicelint's `{"suppressed", "files"}` envelope, so one consumer reads both tools. `excerpt` remains as a read-only alias.
- `test_structlint.py` grows from 23 to 42 tests: a case for each false positive above, for each threshold, and for the finding shape.
- `VERSION` 0.5.6.

## v0.5.5 (2026-09-15)

Item 3 of `docs/ROADMAP.md`: the corpus scan and release diff, so the count that every rule change is supposed to carry is one command rather than an afternoon.

- **`tools/corpusscan.py`**, new. `scan DIR...` counts every rule over a corpus (hits, files, hits per 1,000 words, sorted); `--rule ID` narrows to one rule with sampled contexts; `--candidate "field:pattern"` (or a JSON rule object) tries a rule that is not in the config yet, and refuses one that already is. `diff DIR --old A.json --new B.json` runs two base rule sets under the same overlay and reports rules added, removed, and renamed (same pattern, new id), per-rule deltas, and the findings that appear and vanish, with contexts for the new ones. `--json` adds the tool version, the sha256 of every config involved, and the corpus size, which is what a dated snapshot should keep. Every number is labelled a raw hit; nothing promotes a rule.
- **`voicelint.load_config(path, base=...)`** takes another base file, for the corpus tools only. The linter's own CLI still always runs the shipped base, so a vendored copy cannot be pointed at a stale one.
- Today's calibration reproduced by the tool, the 0.5.1 rule set against 0.5.5 on the saga's shareable tree (202 Markdown files, 273,455 words, saga overlay, both run under the current linter so only the rule changes show): errors 6 to 6, warnings 300 to 293, 62 findings appear and 69 vanish; 15 rules added, 21 removed, 5 renamed. The hand count earlier today read 313 to 294 because it also carried the 0.5.2 and 0.5.3 code changes (overlap collapse, directive blanking). The three `named` soft phrases from `docs/priority-fixes.md` row 7 score 0 hits on the corpus and stay.
- The count command is in the repository `CLAUDE.md`, so a rule change without a count is a visible omission.
- `tools/test_corpusscan.py`, 11 tests, in CI.
- `VERSION` 0.5.5.

## v0.5.4 (2026-09-15)

Item 2 of `docs/ROADMAP.md`: the reply preflight, for the gap where nothing checked an assistant's chat replies.

- **`tools/replycheck.py`**, new. Both scanners over a drafted reply under a surface overlay, one line per finding, a verdict (`PASS` exits 0, `FIX` exits 1, could-not-run exits 2), `--strict`, `--json`, `--no-structure`. Structural findings are advisory and never change the verdict; a checker that fails every terse answer gets switched off.
- **`tools/surfaces/assistant-chat.json`**, new. An overlay for an assistant speaking to the author: the demonstrative pointer, `worth noting` and `worth saying`, question praise, markdown links, tilde paths, the section sign, the `plainly` tag, the coy withhold. Each rule carries an id, a rationale, and examples the tests run. Chat-only rules live here so the shipped defaults stay general.
- **`tools/replycheck-hook.py`**, new. A Claude Code `Stop` hook: reads the assistant text since the last human message from the transcript, runs the same check, and on an error exits 2 with the findings so the assistant sends a corrected follow-up. One enforced revision per reply (`stop_hook_active` is honoured), warnings block only under `REPLYCHECK_STRICT=1`, and a hook that cannot read its input exits 0 rather than wedging the session.
- **`banned_phrases` and `engagement_bait` accept `re:` patterns**, as `soft_phrases` already did, with no word-edge guard on a regex. A banned finding's message shows the rule's rationale when it has one.
- **`docs/reply-preflight.md`** and a repository `CLAUDE.md` carry the recipe: draft to a file, check, revise at most three times, send the exact buffer that passed, and a check that did not run is not a pass. The habit it will keep catching is quoting a banned phrase in plain quotation marks; backticks are masked.
- Evidence from the session that built it: two of eight long assistant replies would have been sent back, all on quoted examples.
- `tools/test_replycheck.py`, 22 tests, in CI.
- `VERSION` 0.5.4.

## v0.5.3 (2026-09-15)

Item 1 of `docs/ROADMAP.md`: stable rule ids, as additive metadata. The string lists and the `add_`/`remove_` contract are unchanged, so a vendored copy and its overlay keep working as they were.

- **Every rule has an id.** A string entry derives one from its pattern (`banned.game-changer`, `soft.worth-more-to-word-than`; a regex gets `soft.re-<8 hex>`); two strings that slug alike (`gut-check`, `gut check`) stay distinct. The fixed rules are `dash`, `dash-density`, `load-bearing-context`, `honest-framing`, `loaded-adverb`, `overuse.<word>`, and `source.<domain>`.
- **An entry may be an object** `{"id", "pattern", "rationale", "since", "fires", "clean"}`. The five shipped regex rules are now objects with ids (`soft.mystery-tail-no-way`, `soft.mystery-tail-never-said`, `soft.mystery-tail-could-not-say`, `soft.abstract-landscape`, `soft.authenticity-tag`), a rationale, and examples. The test suite runs every `fires` and `clean` example, so a rule with examples is a tested rule. A duplicate explicit id, an unknown key, or a missing pattern is a config error.
- **Findings carry `rule_id`**, in the JSON and in the text line (`soft-cliche (soft.abstract-landscape)`). A soft finding's message shows the rule's rationale when it has one, instead of the raw regex.
- **`remove_<field>` accepts an id**, so an overlay drops a shipped regex without pasting it. `add_<field>` skips an entry whose id or pattern is already present. An inline `ignore-line` can name an id as well as a family.
- **`--list-rules`** prints every rule the effective config runs (id, family, severity, pattern, rationale), or the same as JSON with `--json`.
- A read directive comment is blanked before matching, so `ignore-line banned.game-changer` no longer lints its own words.
- The saga corpus reports 6 errors and 293 warnings against 0.5.2's 294, with 4 suppressed against 9: the five findings that used to fire on directive comments and then be suppressed are gone, and so is one that fired inside an allow-comment's own text and was never suppressed.
- `VERSION` 0.5.3.

## v0.5.2 (2026-09-15)

The second half of the Codex review: the rule-level bugs, then a calibration of the shipped set against a 200-file downstream corpus. Everything in the calibration was counted before it was kept.

- **The honest-framing error covers the family voice-rules.md states**, `[det] honest [adj] NOUN` with the nouns that name an utterance (answer, take, look, note, framing, part, case, move, position, summary, and so on), plus the copular form `[det] honest NOUN is that` whatever the noun. It had been twelve literals beginning "the", so `One Honest First Look` and `the honest obstacle is that` walked past it. Subject-matter nouns (broker, assessment, accounting) do not fire, and the broad `honest \w+` warning is gone: 39 corpus hits, most of them literal adjectives.
- **Overlapping phrase hits collapse to one finding.** `This is what it buys you` produced four warnings for one tic. Errors beat warnings, the longer match wins at equal severity, and the counting rules (overuse, dash density, source, load-bearing context) are left alone so a soft phrase cannot swallow a real count.
- **`voicelint-allow` matches whole words.** Allowing `land` used to silence a `landscape` finding.
- **A numeric en-dash range is not a dash hit.** `Pages 10–12` was an error; the prose rule allows it.
- **`[verb]` means a gerund.** `worth nothing` no longer matches `worth [verb]`. `it is worth noting` is banned with or without `that`.
- **Calibration, dropped:** `the one that` (25 corpus hits, all ordinary relative clauses), the bare `lands at/in/on` and `land here/there` placement forms (the plane lands at noon), the good/great/fair-question block. `landscape` is narrowed to the abstract forms (`the current landscape`, `landscape of`). `rhymes with` and `the mirror image of` are warnings, since their literal senses were errors. Kept on the evidence: `is the whole`, `is the point`, `the part that`, `the thing that`, 136 corpus hits that read as the announcing-significance tell.
- **Calibration, added**, the bans voice-rules.md states that nothing enforced: `important` and the boosters (`very`, `really`, `extremely`) as filler; `in all honesty` banned; `frankly`, `candidly`, `truthfully`, `to be honest` warned in their comma-tagged form only (bare `answers it truthfully` is literal); `the truth is,` as bait in its comma form only (`the truth is stupider than the myth` is a sentence); `moreover`, `furthermore`, `in recent years` as warnings; clause-final `quietly` on by default rather than opt-in.
- Net on the corpus: warnings 313 to 294, errors 1 to 6, every new error a real instance of the honest-framing tell.
- `VERSION` 0.5.2.

## v0.5.1 (2026-09-15)

A Codex review of the tools, recorded in `docs/codex-review-2026-09-15.md`, found four correctness bugs. This release fixes those four and nothing in the rule set; the calibration findings in that review wait on a separate decision.

- **The Python copy of the defaults is gone.** `voicelint.py` carried a `FALLBACK_CONFIG` that had drifted from `voice_config.json` (13 soft phrases against 115, 26 banned phrases against 34), and every `--config` was merged onto that stale copy rather than the shipped file. Any user config, however small, silently ran with a fraction of the rules. The shipped JSON beside the script is now the only base; a missing base exits 2 instead of running with less. The overlay is `--config`, or `./voice_config.json` in the working directory when it is a different file. `--print-config` prints the effective set.
- **The `rules-file` marker is read after code masking**, and only as an HTML comment on its own line. Before, the marker inside backticks, or mentioned in a sentence, silenced the whole file.
- **Fence masking covers tilde fences and unclosed fences.** A tilde block was linted as prose, and an unclosed backtick fence, which Markdown renders as code to the end of the file, was too.
- **Suppression directives survive HTML stripping.** `strip_html` removed every comment, so `ignore-line` and `voicelint-allow` did nothing in an `.html` input.
- **`frame` leaves the load-bearing exempt set.** The comment above the set already named "load-bearing frame of the argument" as the figurative case; the set contradicted it. It now draws the context warning like any other non-structural object.
- **`eval/study.py` scores the letter you typed.** Forced-choice picks resolved to the row the letter sat on, so entering `b` on row `a` counted as picking `a`. A pick now resolves to the named candidate; an unknown letter, two conflicting picks for one writer, or a rating outside 1 to 5 stops the run rather than scoring a guess. `eval/test_study.py` covers it.
- **Both test files are real `unittest` suites**, collected by `python3 -m unittest` and by pytest, with the old direct invocation unchanged for CI. The prior scripts ran at import time and were invisible to both runners. Every bug above has a regression case.
- `VERSION` 0.5.1.

## v0.5.0 (2026-08-20)

A structural checker joins the linter. `voicelint` matches phrases; the families that actually sink a draft have no string to match, and `voice-authoring.md` has said so since 2026-08-15 under "The linter is the last check, not the check" without anything enforcing it. Guidance lost to the default register in practice, so it becomes a tool.

- **`tools/structlint.py`, new.** Four checks with nothing to grep for: the clipped balanced parallel, a run of three or more short sentences, a header that strikes a pose rather than naming its subject, and density. Everything is a warning, because these are judgment calls that over-fire by design, and the output is a list for a glance rather than a verdict.
- **It reads paragraphs, not lines.** Hard-wrapped markdown puts one sentence across several lines, and a line-by-line read saw a sentence ending mid-line as a two-beat that was not there. Blockquotes, list items, bold run-in labels and clauses ending in a colon are all skipped for the same reason: a checker that cries wolf gets ignored.
- **`tools/test_structlint.py`, new**, wired into the test workflow beside the voicelint suite. The negative cases outnumber the positive ones, which is the right ratio for a tool whose failure mode is noise.
- **The land heuristic is merged into `voice_config.json`**, closing a queued item, and rescoped. The queued version covered the "it did not land with the team" sense and caught 5 of 71 metaphorical uses in a real corpus; the dominant construction is "X lands somewhere."
- **`actually` and `silently` become watch words capped at two per document** rather than bans. Both already had rules with no tooling. A ban on `silently` would have broken "silent failure," which is literally true of software.
- **Soft phrases added** for the empty-emphasis frame, the forward pointer, the named-nominalization, and the "what it buys you" sales register.
- **`carries` deliberately did not get a phrase ban.** Four of five uses in a real corpus's titles were precise; the header check catches the abstract one and leaves the rest.
- `VERSION` 0.5.0.

## v0.4.9 (2026-07-24)

A third Codex round refined the evaluation design. The verdict has held across rounds (a sound advisory tool, the judgment layer unproved), so this closes the doc-review loop; the remaining work is running the study, not editing it.

- **The primary outcome is a paired within-writer contrast.** The 0.4.8 "frozen" outcome still averaged authentic and flattened items together, which cancels the two cases the study exists to separate. It is now the discrimination margin (authentic rating minus flattened rating, and authentic minus impostor) under the correct profile minus the same margins under the pooled controls. The estimand matches.
- **Reader reliability is a measured outcome.** Added to the metrics: writer-versus-reader and reader-versus-reader agreement on the blind pairwise judgments, with uncertainty and a fixed rule for disputed pairs. The human reference is only as good as its agreement.
- **The harness and the protocol are told apart.** `eval/README.md` now states plainly what `study.py` implements (correct/wrong/none, one rater, one run) and what stays manual (shuffled control, validation case types, repeated runs, multiple readers), so "the harness scales to it" is not read as "it is implemented."
- **A failed holdout is diagnosed, not auto-widened.** `profile_builder.md` no longer says "widen them" on a missed holdout; it revises a marker only if a fresh control shows better authentic recognition without accepting an impostor, since widening trades specificity for recall.
- `VERSION` 0.4.9.

## v0.4.8 (2026-07-24)

A second Codex round on 0.4.7 confirmed the earlier fixes and found four smaller things. All docs.

- **The verdict map covers every state.** REVISE listed a voice dimension at 3 and a missing-markers score at 2 or below, but not one off-profile dimension at 2 or below for any other reason, while REWRITE needs two or more. REVISE now includes "exactly one voice dimension at 2 or below," so no score pattern falls through.
- **The blind-eval primary outcome is one frozen formula.** It said "mean rating (or discrimination margin)," which is two outcomes. The primary is now the mean 1-to-5 rating, correct profile minus the equally weighted controls, with the discrimination margin and any verdict score named as secondary and a fixed verdict encoding if one is used.
- **The local holdout runs blind.** Step 4b listed each case beside its expected verdict, so a validating pass could return the expected answer from the cue. The check now shuffles the items, strips the labels and expectations from the validating pass, and reveals them only for the comparison.
- **The cheat sheet stops promising fidelity it cannot enforce.** "Facts ... stay exactly as you had them" is now stated as a requirement to check, not a guarantee, since nothing enforces exact preservation and rewrite fidelity is still an unmeasured outcome.
- `VERSION` 0.4.8.

## v0.4.7 (2026-07-24)

A cross-vendor review (Codex, GPT-5.6) caught issues the Claude reviews missed. All docs.

- **Sample count matches the holdout.** The profile builder reserves one sample before extraction (0.4.6), but the docs still said "3 to 5 samples," which leaves only two to build from at the low end. README, `profile_builder.md`, and both cheat sheets now say at least four (five or more for multiple registers), with one reserved.
- **The eval harness stops overclaiming.** `eval/README.md` opened by calling itself "the harness that turns ... into a result you can trust," but `study.py` is a blinded single-rater pilot, not the confirmatory study. The opening now says so and points to `docs/blind-eval.md` for the multi-writer design.
- **Flattening no longer strips content.** The holdout and blind-eval flattening steps said "remove personal examples," but examples are often the evidence, so removing them confounds a thinner text with a flatter voice. Both now preserve facts and concrete examples, neutralize only framing, syntax, hedging, transitions, and rhythm, and require a facts-and-detail equivalence check before a flattening is used.
- **The blind-eval protocol has a preregistration.** `docs/blind-eval.md` gains an estimand, the writer as the analysis unit, the primary-outcome formula, an interval method, a multiplicity rule, a power statement, and fixed failure criteria, all set before the run.
- `VERSION` 0.4.7.

## v0.4.6 (2026-07-24)

A review confirmed the mechanical layer is sound and put the weight on the judgment layer, the holdout, and the evaluation design. This pass is docs and one test, no linter code.

- **Provenance residue removed.** README no longer says Pherkad "makes it visible" or that a failure means "the machine's habits crept in"; a REVISE or REWRITE is described as a weak profile match or too many configured patterns, never as evidence of how a draft was produced. `SKILL.md`'s central line is now "run a structured review of whether written output matches one specific person's voice profile," Dimension 5 is "Generic or flattened patterns," and the output heading is "GENERIC OR FLATTENED PATTERN FLAGS."
- **Score anchors and an explicit verdict map.** The seven dimensions now share a stated 1-to-5 anchor scale, so a score is reproducible rather than a feeling, and the PASS/REVISE/REWRITE rules are tied to specific dimension scores and signals instead of "a handful" or "heavy hits."
- **The profile holdout is repaired.** The holdout is chosen and isolated before markers are extracted (a read sample cannot be made unseen); a failed holdout is spent, so a profile changed to fix it is confirmed on a new untouched sample; the flattened rewrite is produced by an editor or model blind to the profile, preserving facts and order within 10 percent length, not by deleting the profile's markers; and the impostor check uses several closely matched writers.
- **The blind-eval protocol became a study design.** `docs/blind-eval.md` now leads with correct-profile lift (run every item under the correct, a wrong, a shuffled, and no profile, plus linter-only) as the primary result, since a pass proves nothing if the wrong profile does as well. Added within-writer register coverage, independent blind flattening with at least two variants, several hard impostors, external blinded pairwise reader judgment, role separation across model families, frozen definitions (light REVISE, run count, model and sampling, stability, thresholds), a twelve-item measurement list, an authoring arm, and pilot-versus-confirmatory sizing.
- **Test.** Added a regression case that an empty watch-word key exits 2.
- **Evaluation harness.** New `eval/study.py` and `eval/README.md`: a blinded voice-authoring study that measures correct-profile lift (a draft written with the writer's own profile against wrong-profile and no-profile controls, plus a real held-out anchor), the concrete way to run the `docs/blind-eval.md` design. Data lives under `eval/data/` and is gitignored; the code and protocol are shareable.
- `VERSION` 0.4.6 (the eval harness is repo tooling, not part of the skill bundle).

## v0.4.5 (2026-07-24)

A fourth review found the mechanical layer sound and pointed the real work at the judgment layer. This pass closes the remaining linter holes, stops the linter and docs from implying provenance, and starts the highest-value work: evidence that the "sounds like you" verdict generalizes.

- **Config validation is semantic, not just structural.** A negative watch-word cap (which used to crash at runtime) and an empty configured phrase (which used to match at every character) are now rejected with exit 2, along with empty watch-word keys. A validated config no longer reaches a runtime failure or a match-everywhere rule.
- **Suppression is comment-scoped and code-aware.** A `voicelint: ignore` directive is recognized only inside an HTML comment, and directives are read from the code-masked text, so a backticked or in-prose token can no longer silence a real finding.
- **`load-bearing` is warning-only.** A regex reading one word cannot tell `load-bearing frame of the argument` (figurative) from `load-bearing case` (a literal enclosure), so the hard-error tier is gone. A clear physical member is exempt; everything else is a soft `load-bearing-context` warning, and whether an ambiguous use is really figurative is left to the judgment layer.
- **Provenance language removed.** The linter and docs no longer imply they detect AI authorship. README leads with "helps you review whether a draft still sounds like you"; `SKILL.md` surfaces "generic phrasing" rather than "AI-generated flatness"; `profile_builder.md` and `ai_tells.md` describe positive markers as evidence of profile match, not of how a passage was produced. A hit or a verdict is about voice fit, never about provenance.
- **Profile holdout check.** `profile_builder.md` gains Step 4b: reserve one sample the profile never saw, then confirm the profile recognizes it, revises a flattened rewrite of it, and does not accept another writer's piece, before the profile is trusted. It catches an overfit profile that only matches its own extraction set.
- **Blind-evaluation protocol.** New `docs/blind-eval.md`: the plan for the multi-writer blind set that would move the judgment layer from advisory to dependable, with the case types, the run method, the pass bar, and a requirement to report failures. The protocol is written; the dataset needs real samples. `docs/review-followups.md` is updated to match.
- `VERSION` 0.4.5.

## v0.4.4 (2026-07-24)

A third external review found an over-correction from 0.4.3 and several older bugs. This pass grades `load-bearing` instead of guessing, hardens the config loader, makes the linter safe for real technical and multilingual prose, and adds a way to silence a checked false positive.

- **`load-bearing` is graded in three tiers.** 0.4.3 over-corrected: `member`, `frame`, and `assembly` are ordinary engineering nouns but were hard-errored as figurative. Now a physical member (wall, beam, column, joist, truss, slab, stud, lintel, girder, rafter, member, frame, assembly, footing, pier) is exempt; a clear argument word (argument, assumption, claim, thesis, premise, idea, reasoning, logic, case, and the like) is an error; everything else, including ambiguous nouns and predicate use, is a soft `load-bearing-context` warning that asks for a look rather than declaring the metaphor.
- **The mathematical minus sign is no longer called a dash.** U+2212 left the prose-dash set, so `5 − 3` does not raise a dash error.
- **Decomposed Unicode is handled.** The phrase-edge guard now counts combining marks (category M) as part of the preceding letter, so a phrase after an NFD accent no longer slips the boundary.
- **Config validation is strict.** Boolean fields (`no_dashes`, `flag_loaded_quietly`, `load_bearing_literal_only`) are type-checked, and an unknown top-level key (a typo like `no_dash`) is rejected with exit 2 instead of silently ignored. Comment keys still start with `_`.
- **No shared mutable default state.** `load_config` and the deep-merge now `deepcopy` the built-in fallback, so mutating one returned config cannot bleed into the next load (matters for imports and tests, not the one-shot CLI).
- **Hostname matching tolerates a trailing dot.** A fully qualified `www.msn.com.` now matches; path, query, and userinfo still do not. Only scheme-bearing URLs are scanned, and that limit is documented.
- **Inline suppression.** A `voicelint: ignore-line` or `voicelint: ignore-next-line` directive (optionally naming rules) silences a checked false positive; the summary and JSON report the suppressed count. This gives the standalone linter a real answer for a legitimate quotation or term instead of "the model will sort it out."
- **JSON output shape.** `--json` now returns `{"suppressed": N, "files": {path: [findings]}}` rather than a bare path map, so a consumer can see suppressions. A breaking change for anyone parsing the old top-level map.
- **Honest defaults and docs.** The news-brief closers (`that's the news`, `watch the move`, `note the framing`, `read this under`, `is the move`) moved from the generic defaults to `examples/news-brief.json`. `SKILL.md` describes the linter as heuristic where it is heuristic and drops "final quality gate" for "final advisory review." The stale example comments and the `review-followups.md` opening are corrected.
- `VERSION` 0.4.4.

## v0.4.3 (2026-07-24)

A second external review caught two regressions from 0.4.2 and three older bugs. This pass fixes the mechanical layer to match its own release notes and pulls source-quality policy out of the generic defaults.

- **`load-bearing` regression fixed.** 0.4.2 widened the literal exemption too far: `structure`, `capacity`, `member`, `frame`, and `assembly` read as metaphor as often as engineering (`the load-bearing structure of the argument`), so they wrongly silenced the tell. The exemption is now only unambiguously physical members (wall, beam, column, joist, truss, slab, stud, lintel, girder, rafter); figurative use fires again.
- **Density floor regression fixed.** The linter's dash-density warning still used a 100-word floor while `SKILL.md` and the changelog said 150. The linter now requires 150+ words and 3+ dash hits, matching the judgment layer.
- **Domain matching reads the host, not the whole URL.** The old regex flagged an aggregator name anywhere after `https://`, so `https://example.com/path/msn.com/story` fired on `msn.com`. Matching now parses the hostname with `urllib.parse.urlsplit` and compares host suffixes and labels, so a domain in the path or query is ignored.
- **Phrase edges are Unicode-aware.** The 0.4.2 boundary guard used an ASCII character class, so a phrase wedged between accented letters slipped through. The guard now tests the neighboring character with `str.isalnum`, which is Unicode-aware.
- **Source policy left the generic defaults.** `aggregator_domains` is now empty and the `live` watch word is gone from `voice_config.json` and the built-in fallback; both live in `examples/news-brief.json`. Source provenance is not voice, so it should not ship as a generic voice rule.
- **Tests and honesty.** Added regression cases for the ambiguous-noun `load-bearing`, the 149/150-word and 2/3-hit density thresholds, host-versus-path domain matching, and Unicode edges. The "covers every rule and promised exception" claim is corrected to "core rules, CLI behavior, and documented examples," and the test docstring says plainly that the judgment layer is not tested here.
- **Doc accuracy.** README and the cheat sheet now describe the real exit-code contract (a warning exits 0 unless `--strict`; usage, IO, and config errors exit 2). README's provenance section is retitled Origins and no longer implies public validation. `SKILL.md` Step 3 asks for each sentence with a *supported* tell, not "every" tell.
- `VERSION` 0.4.3.

## v0.4.2 (2026-07-24)

Correctness pass on the mechanical linter after an external repo review, plus honest-scope wording in the docs. The linter now overreaches less and the judgment layer keeps the calls it should keep.

- **Phrase matching respects word boundaries.** A banned or engagement-bait phrase whose edge is alphanumeric is now guarded, so `is the move` no longer fires inside `movement`. Punctuation-edged phrases (`picture this:`, `in conclusion,`) still match as written.
- **Code spans are masked before matching.** Fenced blocks and inline `code` become same-height whitespace, so a doc can name a banned phrase in backticks without tripping the linter. Line and column offsets are unchanged. Ordinary quotations are deliberately not exempted; adjudicating a direct quote stays with the judgment layer.
- **`load-bearing` recognizes real structural context.** The literal exemption widened past `walls` to beams, columns, members, structures, assemblies, capacity, joists, trusses, slabs, frames, studs, lintels, and girders. Figurative use still fires.
- **`flag_loaded_quietly` is off by default.** Clause-final position alone cannot separate an insinuating `quietly` from a plain manner adverb (`shut the door quietly`), which produced false positives. It is now an opt-in house rule; overuse is still caught by the `quietly` watch word, and the pre-modifier case stays in `references/ai_tells.md`.
- **Config deep-merges.** A user config now merges onto the defaults key by key: setting one entry in `watch_words` no longer wipes the others. New `add_<field>` / `remove_<field>` keys amend a shipped list without restating it. `examples/relaxed.json` demonstrates both.
- **Density needs a floor of text.** The judgment-layer density verdict (`SKILL.md` Step 4) applies only to a draft of 150+ words with 3+ findings, so a lone hit in a short passage no longer forces a REVISE against the stated lone-hit calibration. The linter's dash-density warning gained the same floor.
- **Tests and CI.** `tools/test_voicelint.py` rewritten as a table-driven suite over the core rules, CLI behavior, and documented examples (boundaries, load-bearing context, code masking, dash and density modes, deep-merge and list ops, domain matching, HTML stripping, JSON, `--strict`, exit codes, invalid config, line/column). A new `.github/workflows/test.yml` runs it on Python 3.8 through 3.12 on every push and pull request.
- **Honest-scope wording.** README no longer says "flags every tell" (now "checks the full catalog"); "the validator gets more accurate with use" became "a later run applies the recorded correction"; the module and `--help` descriptions and `ai_tells.md` no longer claim to detect provenance; the self-lint claim now names its scope (README and the cheat sheet).
- `VERSION` 0.4.2.

## v0.4.1 (2026-07-17)

- **Split profiles.** Pherkad loads `voice-rules.md` and `voice-authoring.md` from the working folder when present, alongside `Voice_Profile.md`. A profile can split across the three (personal markers in the profile, bans in `voice-rules.md`, drafting guidance in `voice-authoring.md`), so a writer keeps one canonical copy of each rule instead of duplicating them into the profile.
- `SKILL.md` Step 0 and `references/authoring.md` load the companion files.
- `VERSION` 0.4.1.

## v0.4.0 (2026-07-17)

- **Authoring mode.** Pherkad now drafts and rewrites in the writer's voice, not only validates. New `references/authoring.md`: write from the profile's positive markers, avoid the product-marketing register by default, choose words by a meaning-versus-decoration condition rather than a fixed list, restore the writer's hedging, anchor in a concrete witnessed detail, and self-validate the draft before returning it.
- `SKILL.md` gains a Modes section: validation (Steps 0 to 6) and authoring (`references/authoring.md`), both reading the same `Voice_Profile.md`.
- Weighted preferences are documented as authoring guidance and corpus-level monitoring, never a per-document lint rule, since a ratio is not checkable in a single document.
- `VERSION` bumped to 0.4.0.

## v0.3.1 (2026-07-17)

- **voicelint: the "quietly" rule now flags the trailing position, not the pre-modifier.** A pre-modifier "quietly + verb" ("quietly building") cannot be told mechanically from a legitimate stance ("quietly skeptical," "quietly noticing"), so the old rule fired on good prose. The linter now flags "quietly" only when it ends a clause or sentence ("shut it down quietly," "the numbers moved quietly"), the insinuating position that implies concealed intent. The pre-modifier case moves to the judgment layer in `references/ai_tells.md`.
- `references/ai_tells.md`: the single loaded-adverb line splits into a mechanical trailing-quietly entry and a judgment-layer pre-modifier entry.
- Added `tools/test_voicelint.py`, a dependency-free regression test that locks in the trailing-versus-pre-modifier behavior plus core smoke tests.
- `VERSION` bumped to 0.3.1.

## v0.3 (2026-07-16)

- **Positive register: calibrate toward, not only against.** `references/ai_tells.md` gains a Positive register section. Validation now reads whether a draft carries the writer's own distinctive markers, not only whether it is clean of tells. A draft clean of every tell but showing none of the writer's markers has flattened toward a generic default, and that is a REVISE-level signal in its own right. Generalized from a private single-writer rubric; the examples (concrete before concept, flat consequence, the telling detail, owned not deflected) describe the shape, and the profile carries each writer's own version.
- **Genre calibration.** Added to `references/ai_tells.md` and the skill's Calibration notes: distinctiveness lives in the frame, the transitions, and the close, while the analytical, legal, or technical core stays plain and precise and must not be flagged for failing to be vivid. A finished piece is often deliberately uneven by design, a distinctive frame around an exact middle.
- `references/profile_builder.md`: new Step 2b captures the writer's positive markers (the archetype), so a profile records what the voice does, not only what it bans.
- `skills/pherkad/SKILL.md`: Step 3 and the Calibration notes wire the positive-register read and genre calibration into the diagnostic and the verdict.
- Added a `VERSION` file (0.3.0) so an install self-identifies.

## v0.2 (2026-07-15)

- **voicelint: soft-cliche warnings.** A new warning layer for phrasings that are hard to ban outright but recur far too often in AI-assisted text. New `soft_phrases` config field, matched as warnings rather than errors, with readable placeholders: `[word]` matches one token, `[verb]` matches a gerund. Seeded set: `it's worth [verb]`, the `I want to be plain / clear / honest / upfront / direct / transparent` opener family, `gut-check` and `gut check`, `where your [word] lives`, `names a way`, and `the [word] that never bends`.
- A soft hit that lands on a stronger banned phrase (for example `it's worth noting that`) is dropped as redundant, so the phrase reports once, as an error.
- Config validation now covers `soft_phrases`. Warnings still exit 0 unless `--strict`, so the layer is safe in CI.
- Reworded the two cheat-sheet footer labels the new rule flagged in Pherkad's own docs (`Where your data lives` -> `Your data`, `The rule that never bends` -> `The one rule`), so `README.md` and the cheat sheet still exit 0 under the default linter (the scope CI checks; the changelog and catalog quote the patterns by name and are exempt).

## v0.1 (2026-07-15)

First public version, generalized from a private single-writer validator.

- Split the validator into a generic engine and a personal voice profile. The engine (SKILL.md protocol plus `references/ai_tells.md`) ships here; the profile is built per user and never enters the repo.
- `references/profile_builder.md`: a short interview that builds `Voice_Profile.md` from 3 to 5 real writing samples, every marker backed by a quoted sentence. Corrections append over time.
- `references/example_profile.md`: a fictional persona (Rosa Vantani, field ecologist) showing the profile shape, including catalog overrides (deliberate em dash use, domain vocabulary exemptions).
- Tell catalog carried over intact: categories 5a-5i, the density meta-rule (2.0 flagged constructions per 100 words), cluster warnings, and the caveats (technical-literal uses, quotes, single instances, the validator-internals exception). At the judgment layer, em dash flagging is profile-conditional: full flagging unless the profile shows deliberate dash use with evidence.
- All references to the original writer's private source documents removed; personal markers replaced by the profile mechanism.
- Merged in **voicelint** (`skills/pherkad/tools/voicelint.py`), a dependency-free mechanical linter for the regex-able subset of the catalog, from a working draft built for a different project. The full observed rule set ships as the defaults (hard dash ban, banned phrases, watch-word caps, source-domain list); every rule was built from tells seen across many AI-assisted documents, not one writer's preference, so none of it was demoted in the generalization. Defaults also gained the catalog's generic tells (scene-setting openers, engagement bait). What generalization added instead is a documented relaxation path: `tools/examples/relaxed.json` shows loosening a default the writer's profile contradicts (with the dash-density cap replacing the hard ban for deliberate dash users), `tools/examples/news-brief.json` shows team-specific additions, and any relaxation should match an evidence-backed override in `Voice_Profile.md` so the linter and the judgment layer agree. The skill's Step 3 runs the linter first when Python is available; the profile builder can emit a personal config.
- Catalog additions from the voicelint rule set: self-narrating closers, reader stage-directions, analogy connectives, loaded adverb + verb, and crutch-word overuse.
- Meaning guardrail on rewrites, from the voicelint rules doc: a voice edit never adds or drops facts, names, numbers, dates, or sources, and preserves emphasis.
- README gained two author sections: **Why these defaults** (the rules come from tells observed across many AI-assisted documents, they ship strict, and customizing to purpose is a JSON edit away) and **Why this exists** (informed use of AI lets people on the fence write and build things they would not otherwise have tried; the fix for flattened prose is knowing what the tools do to your sentences, not abstaining).
- One-page cheat sheet in `docs/` (`CHEATSHEET.md`, `.html`, `.pdf`): every mode, what to say, what you get, matching the Kochab cheat-sheet format.
- Repo scaffolding: README, MIT LICENSE, `build.sh` (one-command packaging of `pherkad.skill`).
