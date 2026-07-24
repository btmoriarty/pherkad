# Changelog

## v0.4.2 (2026-07-24)

Correctness pass on the mechanical linter after an external repo review, plus honest-scope wording in the docs. The linter now overreaches less and the judgment layer keeps the calls it should keep.

- **Phrase matching respects word boundaries.** A banned or engagement-bait phrase whose edge is alphanumeric is now guarded, so `is the move` no longer fires inside `movement`. Punctuation-edged phrases (`picture this:`, `in conclusion,`) still match as written.
- **Code spans are masked before matching.** Fenced blocks and inline `code` become same-height whitespace, so a doc can name a banned phrase in backticks without tripping the linter. Line and column offsets are unchanged. Ordinary quotations are deliberately not exempted; adjudicating a direct quote stays with the judgment layer.
- **`load-bearing` recognizes real structural context.** The literal exemption widened past `walls` to beams, columns, members, structures, assemblies, capacity, joists, trusses, slabs, frames, studs, lintels, and girders. Figurative use still fires.
- **`flag_loaded_quietly` is off by default.** Clause-final position alone cannot separate an insinuating `quietly` from a plain manner adverb (`shut the door quietly`), which produced false positives. It is now an opt-in house rule; overuse is still caught by the `quietly` watch word, and the pre-modifier case stays in `references/ai_tells.md`.
- **Config deep-merges.** A user config now merges onto the defaults key by key: setting one entry in `watch_words` no longer wipes the others. New `add_<field>` / `remove_<field>` keys amend a shipped list without restating it. `examples/relaxed.json` demonstrates both.
- **Density needs a floor of text.** The judgment-layer density verdict (`SKILL.md` Step 4) applies only to a draft of 150+ words with 3+ findings, so a lone hit in a short passage no longer forces a REVISE against the stated lone-hit calibration. The linter's dash-density warning gained the same floor.
- **Tests and CI.** `tools/test_voicelint.py` rewritten as a table-driven suite covering every rule and promised exception (boundaries, load-bearing context, code masking, dash and density modes, deep-merge and list ops, domain matching, HTML stripping, JSON, `--strict`, exit codes, invalid config, line/column). A new `.github/workflows/test.yml` runs it on Python 3.8 through 3.12 on every push and pull request.
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
