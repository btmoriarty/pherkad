# Changelog

## v0.1 — 2026-07-15

First public version, generalized from a private single-writer validator.

- Split the validator into a generic engine and a personal voice profile. The engine (SKILL.md protocol plus `references/ai_tells.md`) ships here; the profile is built per user and never enters the repo.
- `references/profile_builder.md`: a short interview that builds `Voice_Profile.md` from 3 to 5 real writing samples, every marker backed by a quoted sentence. Corrections append over time.
- `references/example_profile.md`: a fictional persona (Rosa Vantani, field ecologist) showing the profile shape, including catalog overrides (deliberate em dash use, domain vocabulary exemptions).
- Tell catalog carried over intact: categories 5a-5i, the density meta-rule (2.0 flagged constructions per 100 words), cluster warnings, and the caveats (technical-literal uses, quotes, single instances, the validator-internals exception). Em dashes moved from a hard personal ban to a profile-conditional flag.
- All references to the original writer's private source documents removed; personal markers replaced by the profile mechanism.
- Merged in **voicelint** (`skills/pherkad/tools/voicelint.py`), a dependency-free mechanical linter for the regex-able subset of the catalog, from a working draft built for a different project. Generalized for any writer: the hard dash ban became an opt-in (`no_dashes`) with a generic dash-density warning as the default, and source domains and watch-word caps moved out of the defaults into `tools/examples/news-brief.json`, since which words a writer over-uses and which sources a team trusts are context-bound by definition. The banned-phrase lists stay in the defaults in full; they were built from tells observed across many documents, not one writer's preference. Defaults also gained the catalog's generic tells (scene-setting openers, engagement bait). The skill's Step 3 runs the linter first when Python is available; the profile builder can emit a personal config.
- Catalog additions from the voicelint rule set: self-narrating closers, reader stage-directions, analogy connectives, loaded adverb + verb, and crutch-word overuse.
- Meaning guardrail on rewrites, from the voicelint rules doc: a voice edit never adds or drops facts, names, numbers, dates, or sources, and preserves emphasis.
- Repo scaffolding: README, MIT LICENSE, `build.sh` (one-command packaging of `pherkad.skill`).
