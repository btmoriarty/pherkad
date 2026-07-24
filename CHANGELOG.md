# Changelog

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
