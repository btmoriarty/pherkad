# Pherkad

A Claude skill that helps you review whether a draft still sounds like you.

AI-assisted writing drifts toward a house style that belongs to no one: balanced sentences, stock openers, three abstract nouns where one would do. The drift is gradual and hard to see from inside a draft. Pherkad runs a structured review, identifies sentences that may have flattened, and proposes local rewrites for you to inspect.

Pherkad is the sibling of [Kochab](https://github.com/btmoriarty/kochab), a job-search assistant built on the same ethos. Kochab and Pherkad are the Guardians of the Pole, the two bright stars at the front of the Little Dipper's bowl. Around 1100 BC, before Polaris drifted into position, they served together as the twin pole stars navigators steered by. Kochab keeps a job search pointed true north; Pherkad does the same for a writer's voice.

## How it works

Pherkad splits the problem in three:

- **A generic tell catalog** ([`references/ai_tells.md`](skills/pherkad/references/ai_tells.md)): banned filler, antithesis constructions, scene-setting openers, engagement-bait transitions, triplet noun piles, and a density rule that catches prose built from individually allowed words in characteristic clusters.
- **A personal voice profile**: built once from at least four samples of your real writing (five or more if you write in several registers) through a short interview ([`references/profile_builder.md`](skills/pherkad/references/profile_builder.md)). It records where your authority comes from, how you hedge, what concrete texture you use, your sentence mechanics, your structural habits, and your tone, each marker backed by a quoted sentence of yours. A fictional example profile shows the shape ([`references/example_profile.md`](skills/pherkad/references/example_profile.md)).
- **A mechanical linter** ([`skills/pherkad/tools/voicelint.py`](skills/pherkad/tools/voicelint.py)): the regex-able subset of the catalog as a dependency-free, stdlib-only Python script (3.8+). Exact line numbers, JSON output, CI-friendly exit codes. Runs standalone, no model needed.

A validation run fingerprints the draft (the three sentences most and least like you), runs the linter when Python is available, scores seven dimensions with quoted evidence, checks the full catalog, computes tell density per 100 words, and returns a verdict: PASS, REVISE, or REWRITE, with targeted rewrites of only the flagged sentences.

## The linter alone

One command runs both mechanical engines, the phrase linter and the structural checker, and prints one list in one format:

```sh
python3 skills/pherkad/tools/pherkad.py check draft.md                    # both engines, one list
python3 skills/pherkad/tools/pherkad.py check --format sarif draft.md     # for an editor or CI
python3 skills/pherkad/tools/pherkad.py check --advisory structure. --strict draft.md   # structural findings reported, never counted
```

Every finding carries the same fields (line, col, severity, rule, match, message, rule_id, engine), the two engines' overlap is removed, and one density is computed over both. A warning you have read and ruled on can be recorded once (`pherkad.py decide --decisions FILE --reason "..." path:line`) and stays quiet, uncounted, until the line, the rule, or the number of occurrences changes; `pherkad.py decisions` says which records still match and `--prune` drops the stale ones, and nothing writes a decision without a reason. Every check names its surface, what the text is and who is speaking: `--surface assistant-chat`, `technical`, `email`, `post`, `paper`, `slides`, or `fiction` (each a small overlay with its own guidance and its expectation of the positive register), a project overlay layered on top with `--config`, and a user `surfaces.json` to add surfaces or point one at approved excerpts; an unknown surface is an error, never a guess. `pherkad.py surfaces` lists them. A correction (`X -> Y`) goes into a ledger with `tools/corrections.py add`, is counted on a corpus with `trial`, and on approval `promote` writes the rule with its fixtures into an overlay and generates the mined-corrections line in the prose rules; nothing becomes a rule uncounted, and a factual correction never becomes one. `pherkad.py review-pack --surface X draft.md` assembles the whole context for a judgment run into one prompt (surface guidance, profile files, approved excerpts, mechanical findings with decisions applied, the rules to read for, the output schema, every input hashed), so the model's check is the same on every run and any model can run it. `pherkad.py manifest --verify` proves a vendored copy is what it says it is, and `pherkad.py check-overlay OVERLAY` says whether a downstream overlay still fits this base. The pieces still run on their own:

The judgment layer needs Claude; the linter does not. Put it in a pre-commit hook or CI step and it flags the mechanical tells in any Markdown, plain-text, or HTML draft:

```sh
python3 skills/pherkad/tools/voicelint.py draft.md          # findings with line numbers
python3 skills/pherkad/tools/voicelint.py --json --strict draft.md   # CI mode
```

The linter masks Markdown code spans and blockquotes before matching (`tools/mdmask.py`, the one reading of Markdown structure that voicelint and structlint share), so a document can name a banned phrase inside backticks without tripping it and a quoted passage is not held to the author's rules. It does not adjudicate inline quotations. It flags configured source domains mechanically and leaves their context to the model. CI lints this repository's README and cheat sheet on every push, and both exit 0 under the default rules.

Rules live in [`tools/voice_config.json`](skills/pherkad/tools/voice_config.json). Every shipped default was built from tells observed across many AI-assisted documents, including the hard no-dash rule. The shipped file beside the script is the only base; one overlay (`--config`, or a `voice_config.json` in the working directory) is deep-merged onto it: unlisted top-level fields and unlisted nested keys inherit, listed arrays replace, and `add_<field>` / `remove_<field>` amend a shipped list without restating it. `--print-config` prints the effective set. `tools/corpusscan.py` counts the rules against a corpus (`scan DIR`, one rule with sampled contexts, or a `--candidate` rule that is not in the config yet) and diffs two releases of the rule set under one overlay (`diff DIR --old A.json --new B.json`); every number it prints is a raw hit, not a confirmed violation. Every rule has a stable id (`banned.game-changer`, `soft.abstract-landscape`, `dash`, `overuse.quietly`): a plain string entry derives one from its pattern, and an entry may instead be an object `{"id", "pattern", "rationale", "since", "fires", "clean"}` whose examples the test suite runs. Findings report the id, `remove_<field>` accepts one in place of the pattern, an inline `ignore-line` can name one, and `--list-rules` prints them all. If a default contradicts your real style (you use dashes deliberately, `robust` is your field's vocabulary), relax it in your own config and record the override in your voice profile so both layers agree: [`tools/examples/relaxed.json`](skills/pherkad/tools/examples/relaxed.json) shows the shape, [`tools/examples/news-brief.json`](skills/pherkad/tools/examples/news-brief.json) shows team-specific additions, and the profile builder can generate a personal config. Exit codes: 0 when no error-level findings are present, 1 when an error-level finding is present or a warning is present under `--strict`, and 2 for usage, IO, or config errors. A crash therefore cannot look like a style finding.

## Why these defaults

The default rule set is the one I run on my own writing. I added each entry after meeting a phrase or construction across many AI-assisted documents, in many contexts, until it read as a signature. That makes it a useful house default, not proof that the phrase is bad or machine-written. A hit flags a pattern; it does not judge how the text was written.

The defaults are still my conclusions, and your register may differ. The rules are a JSON file, so changing them is the easy part: clone the tool and edit `tools/voice_config.json` to your purpose, or keep the defaults and relax specific rules in your own config. The one ask: when you loosen a rule, do it because the evidence of your own writing shows the habit is really yours, and record the override in your voice profile so the linter and the judgment layer agree.

## Why this exists

I use AI in most of what I write and build now, and Pherkad came out of that practice. The tools are good enough that people who never called themselves writers or programmers are finishing essays and shipping working software. I think that is worth defending. The people on the fence, the ones with something to say who stopped before saying it, lose the most if the answer to AI-flattened prose is to abstain.

The answer I believe in is informed use. Know what the tools do to your sentences, check the output against your own voice, and keep what is yours. A REVISE or REWRITE verdict is not evidence of how a draft was produced; it means the review found a weak match to your profile or too many configured style patterns. Inspect the cited sentences and decide whether the diagnosis is right.

So use the assistance. Write the essay you were not going to write, build the tool you were not going to build. Just read what you sign.

## Cheat sheet

One page, every mode, what to say, what you get: [docs/CHEATSHEET.md](docs/CHEATSHEET.md) (also as [HTML](docs/CHEATSHEET.html)).

## What Pherkad is and is not

- It validates against one voice: yours. A passage can be fully human-written and still fail because it does not sound like you, and an assisted passage can pass because it does.
- It never returns a bare score. Every number carries a quoted passage as evidence.
- It flags and fixes specific sentences rather than rewriting your piece.
- It does not police other people's text, and it is not a detector for grading student work.

## Your data

The voice profile is built from your writing and stays in your folder. This repository ships no profiles and no personal data; the only persona in it (Rosa Vantani) is fictional. Corrections you make ("that flag is wrong, that's really me") append to your profile, so a later run applies the recorded correction instead of repeating the flag.

## Install

**Claude (Cowork or claude.ai with skills):** grab `pherkad.skill` from this repo if the prebuilt bundle is present, or build it in one command (below), then add it via Settings > Capabilities.

**Claude Code:** copy `skills/pherkad/` into your skills directory.

First run: ask for a voice check on any draft. Pherkad will notice you have no profile yet and run the profile interview first; bring at least four pieces of writing you consider most you (five or more if you write in several registers), since one is held back to check the profile.

## Build the .skill bundle

```
./build.sh
```

produces `pherkad.skill` (a zip of `skills/pherkad/`).

## Origins

The tell catalog draws on public discussions of recurring AI-writing patterns (notably Julian Harris's 2026 thread), the Wikipedia "Signs of AI writing" page, and patterns observed in assisted drafts. The seven-dimension review and the density rule began as a private workflow for one writer. That history explains the design, but it is not public validation of the generalized skill; see [docs/review-followups.md](docs/review-followups.md) for what a blind validation set would add. The mechanical linter began as a news-brief house rule set and was generalized here.

## License

MIT. See [LICENSE](LICENSE).
