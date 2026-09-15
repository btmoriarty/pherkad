# Codex review of the voice tools, 2026-09-15

Produced by `codex exec --sandbox read-only` (gpt-5.6-sol, reasoning high) against commit 4f0126a. Prompt: propose improvements to voicelint, structlint, the config, the prose-rule gap, and the eval harness. Claims in section 1 and section 2 were spot-checked by Claude Code on the same day with the concrete inputs given; every checked claim reproduced. Codex could not run test_voicelint.py in its sandbox (the test writes temp dirs at import); both test files pass outside it.

## 1. Bugs and correctness problems

- [`voicelint.py:449`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voicelint.py:449) checks the raw text for the whole-file escape before masking code. `` `<!-- voicelint: rules-file -->` `` followed by `This is a game-changer.` returns no findings.
- [`voicelint.py:56`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voicelint.py:56) duplicates, and has drifted from, the JSON defaults. [`load_config():268`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voicelint.py:268) merges explicit user configs into this stale fallback, not the shipped JSON. With `{"add_banned_phrases":["circle back"]}`, `That's the news.` is missed although it is a shipped ban.
- [`voicelint.py:256`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voicelint.py:256) always prefers the config beside the script over `./voice_config.json`. A personal config saved beside the profile, as documented, is silently ignored unless `--config` is supplied.
- [`voicelint.py:583`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voicelint.py:583) applies whole-file allowances by substring and across rule IDs. `<!-- voicelint-allow: land (literal: aircraft) -->` suppresses the unrelated `landscape` finding in `The desert landscape changed.`
- [`voicelint.py:289`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voicelint.py:289) masks only closed triple-backtick fences. `~~~\ngame-changer\n~~~` and an unclosed ```` ```\ngame-changer ```` both produce errors.
- [`voicelint.py:119`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voicelint.py:119) exempts `frame`, despite the preceding comment explicitly identifying “load-bearing frame of the argument” as figurative. `The load-bearing frame of the argument failed.` is clean.
- [`voicelint.py:508`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voicelint.py:508) implements only `the honest NOUN`, while [`voice-rules.md:389`](/Users/moriarty/Documents/kochab/pherkad/voice-rules.md:389) requires `[determiner] honest [optional adjective] NOUN`. `One Honest First Look` gets only the broad soft warning, not the promised hard error.
- [`strip_html():278`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voicelint.py:278) removes suppression comments before checking HTML. `<p>This is a game-changer. <!-- voicelint: ignore-line --></p>` still errors under `--html`.
- [`structlint.py:220`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/structlint.py:220) discards an entire prose line if it contains any URL, citation marker, long quotation, or field label. `See https://example.com. It failed. It broke. It stopped.` misses the staccato run.
- [`structlint.py:260`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/structlint.py:260) calls two sentences “parallel” using only character lengths and capitalization. `The meeting starts at nine. Lunch follows at noon.` falsely triggers.
- [`structlint.py:65`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/structlint.py:65) and [`structlint.py:76`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/structlint.py:76) overmatch ordinary headings: `## The actual results` and `## Where the chair sits` both trigger.

## 2. Miscalibrated `voice_config.json` rules

- [`soft_phrases:95-181`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voice_config.json:95) treats literal placement as metaphor: `The plane lands at noon.`
- `landscape` is unconditional although the prose limits the ban to abstract use: `The desert landscape changes after rain.`
- `is the point`, `is the moment`, and `is the whole` are bare fragments with high ordinary-prose incidence: `That is the point on the map.`
- `a named cost`, `a named criterion`, and `as a named` flag normal technical writing: `We assigned a named cost center.`
- [`voice_config.json:183`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voice_config.json:183) bans routine conversational acknowledgments: `She asked a fair question about the invoice.`
- [`voice_config.json:86`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voice_config.json:86) flags almost every `honest + word`, including the documented exemptions: `It was an honest assessment.`
- [`voice_config.json:19`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voice_config.json:19) and line 20 hard-ban literal senses: `Cat rhymes with hat.` and `The scan is the mirror image of the original.`
- [`filler_words:194-210`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voice_config.json:194) ignores technical context: `This result is statistically significant.` and `The protocol requires robust error handling.`
- `[verb]` means `\w+ing`, not a gerund ([`voicelint.py:368`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voicelint.py:368)): `It is worth nothing to us.` triggers as though `nothing` were a verb.
- Overlapping rules are not deduplicated: `This is what it buys you.` produces four warnings; `That would land easier.` produces two; `worth more to you than` produces duplicate identical warnings.
- The hard ban includes only `it is worth noting that`; `It is worth noting the discrepancy.` receives merely a soft warning.
- [`no_dashes:true`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voice_config.json:3) rejects allowed numeric en dashes: `Pages 10–12 contain the tables.`
- Obvious documented tells are absent: `This is very important.`, `In recent years, the rate fell.`, `Moreover, the build passed.`, and `The truth is, it failed.` are all clean.
- [`flag_loaded_quietly:false`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voice_config.json:218) contradicts the canonical positional rule: `They shut it down quietly.` is clean.
- A single insinuating `silently` is clean because it is only a cap-2 watch word: `The service silently dropped the request.`

## 3. Prose-versus-enforcement gaps

Bans with no effective mechanical rule:

- Most of the claimed “union” in [`voice-rules.md:17`](/Users/moriarty/Documents/kochab/pherkad/voice-rules.md:17): `important`, adjective `key`, `vital`, `pivotal`, `holistic`, `nuanced`, `underscores`, `aligns with`, `fundamentally`, `speaks to`, `synergy`, `impactful`, `journey`, `world-class`, `transformative`, and others.
- All boosters in [`voice-rules.md:23`](/Users/moriarty/Documents/kochab/pherkad/voice-rules.md:23), including `very`, `really`, `extremely`, `thrilled to`, and `excited to`.
- Most authenticity signals at line 27: `truthfully`, `frankly`, `candidly`, `to be honest`, and `in all honesty`.
- Copulative avoidance, elegant variation, antithesis density, triplet piling, `Imagine…`, paragraph connectives, watching constructions, participial significance tails, hedge stacking, counter-X, harsh dismissals, reflexive praise, register drops, comma-series fragments, compressed-pronoun antithesis, copular vehicles, and announced `plainly`/`straight` ([`voice-rules.md:70-237`](/Users/moriarty/Documents/kochab/pherkad/voice-rules.md:70)).
- Capitalization after colons, colon stack-ups, prior-context parentheticals, and Arial ([`voice-rules.md:247-261`](/Users/moriarty/Documents/kochab/pherkad/voice-rules.md:247)).
- Surface rules such as research-paper first person, email greetings, `responsible for`, acronym expansion, reserved vocabulary, and factual invention.
- The global “more than two constructions per 100 words” rule is not global: [`structlint.py:303`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/structlint.py:303) counts only structlint findings, never voicelint findings.
- Caveats for direct quotations, technical senses, numeric en dashes, and rule-teaching documents are not parsed mechanically.

Config entries without a rationale in the three canonical prose documents include:

- `writes itself`, `needs no embellishment`, `is the move`, `note the framing`, `read this under`, `that's the news`, and `watch the move` ([`voice_config.json:31-37`](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/voice_config.json:31)).
- The epistemic regexes `no way to say/tell/know`, `never said … which`, and `could not say …`.
- `names a way`, `the [word] that never bends`, pause commands such as `give it a beat`, ownership phrases such as `stays yours`, “named” phrases, and the entire good/great/fair-question block.
- `straightforward` as filler.

The self-lint demonstrates the mismatch: `README.md` is clean; `voice-authoring.md` reports nine warnings; `voice-rules.md` reports 21 errors and 53 warnings despite its own teaching-document exemption.

## 4. Structural and architectural improvements

- Replace the mixed string schema with versioned rule objects: stable ID, matcher type, pattern, severity, scope, rationale/doc reference, exceptions, and examples. Exact-string `remove_*` overrides are too fragile.
- Establish explicit layering: immutable packaged defaults  then  project config  then  user config  then  CLI overrides. Add `--print-effective-config`; remove the Python fallback copy.
- Make structlint rules and thresholds configurable and return the same finding schema as voicelint. A shared runner should compute combined density.
- Parse Markdown once into prose, code, quotations, headings, lists, and tables. Both tools currently maintain incompatible masking heuristics.
- Convert tests to real `unittest.TestCase` or pytest tests. Pytest would not execute either script’s `main()`, and unittest discovers no actual test methods.
- Add negative-corpus calibration tests and regression cases for bypass markers, tilde/unclosed fences, literal senses, overlapping rules, config precedence, fallback parity, HTML suppression, and broad structural exclusions.
- Add rule-level precision/recall evaluation against labeled authentic prose and synthetic tell fixtures; the current eval measures authoring voice, not linter quality.
- Fix [`eval/study.py:267`](/Users/moriarty/Documents/kochab/pherkad/eval/study.py:267): forced-choice scoring ignores the entered candidate letter and scores the row containing it. Entering `b` on row `a` selects `a`.
- The eval also needs rating validation, missing-draft/holdout failures, repeated generations, multiple readers, agreement statistics, model/prompt provenance, and genre-matched anchors.
- Ship voicelint as a versioned executable/library; downstream repositories should pin it and keep only overlays. Validate downstream configs against the schema in compatibility CI.
- CI should lint all canonical docs with both tools, verify generated fallback/config parity, test artifact freshness, and exercise the eval scorer. Current CI checks only README and CHEATSHEET mechanically.

Verification: `test_structlint.py` passed. Pytest was unavailable; unittest could not import `test_voicelint.py` in the enforced read-only environment because the test creates temporary directories at import time ([lines 168 and 214](/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/test_voicelint.py:168)). The working tree remained clean.

## 5. Ranked top 10

1. Remove the raw `rules-file` bypass and replace it with parsed, scoped example/rule-list suppression.
2. Eliminate `FALLBACK_CONFIG`; load one packaged default and apply explicit project/user overlays in documented order.
3. Convert both test scripts to real tests and add regression coverage for every correctness failure above.
4. Replace string arrays with a versioned, ID-based rule schema carrying rationale, severity, scope, and exceptions.
5. Prune or context-gate the high-noise `land*`, honest, question-praise, named-cost, and literal-idiom rules.
6. Implement the missing high-signal canonical bans, beginning with `important`, boosters, paragraph connectives, and trailing `quietly`.
7. Use one Markdown-aware extraction layer for code, quotations, HTML, lists, headings, and suppression directives.
8. Make structlint configurable, require actual syntactic parallelism, and compute density jointly with voicelint.
9. Repair and extend the eval harness with correct forced-choice scoring, validation, repetitions, multiple readers, and provenance.
10. Publish a pinned linter API for downstream overlays and enforce config compatibility plus canonical self-linting in CI.
