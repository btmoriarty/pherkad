# Pherkad

A Claude skill that checks whether a draft still sounds like you.

AI-assisted writing drifts toward a house style that belongs to no one: balanced sentences, stock openers, three abstract nouns where one would do. The drift is gradual and invisible from inside a draft. Pherkad makes it visible, names the flattened sentences, and proposes rewrites that keep your meaning in your voice.

Pherkad is the sibling of [Kochab](https://github.com/btmoriarty/kochab), a job-search assistant built on the same ethos. Kochab and Pherkad are the Guardians of the Pole, the two bright stars at the front of the Little Dipper's bowl. Around 1100 BC, before Polaris drifted into position, they served together as the twin pole stars navigators steered by. Kochab keeps a job search pointed true north; Pherkad does the same for a writer's voice.

## How it works

Pherkad splits the problem in three:

- **A generic tell catalog** ([`references/ai_tells.md`](skills/pherkad/references/ai_tells.md)): banned filler, antithesis constructions, scene-setting openers, engagement-bait transitions, triplet noun piles, and a density rule that catches prose built from individually allowed words in characteristic clusters.
- **A personal voice profile**: built once from 3 to 5 samples of your real writing through a short interview ([`references/profile_builder.md`](skills/pherkad/references/profile_builder.md)). It records where your authority comes from, how you hedge, what concrete texture you use, your sentence mechanics, your structural habits, and your tone, each marker backed by a quoted sentence of yours. A fictional example profile shows the shape ([`references/example_profile.md`](skills/pherkad/references/example_profile.md)).
- **A mechanical linter** ([`skills/pherkad/tools/voicelint.py`](skills/pherkad/tools/voicelint.py)): the regex-able subset of the catalog as a dependency-free, stdlib-only Python script (3.8+). Exact line numbers, JSON output, CI-friendly exit codes. Runs standalone, no model needed.

A validation run fingerprints the draft (the three sentences most and least like you), runs the linter when Python is available, scores seven dimensions with quoted evidence, flags every tell, computes tell density per 100 words, and returns a verdict: PASS, REVISE, or REWRITE, with targeted rewrites of only the flagged sentences.

## The linter alone

The judgment layer needs Claude; the linter does not. Put it in a pre-commit hook or CI step and it flags the mechanical tells in any Markdown, plain-text, or HTML draft:

```sh
python3 skills/pherkad/tools/voicelint.py draft.md          # findings with line numbers
python3 skills/pherkad/tools/voicelint.py --json --strict draft.md   # CI mode
```

Rules live in [`tools/voice_config.json`](skills/pherkad/tools/voice_config.json). Every shipped default was built from tells observed across many AI-assisted documents, including the hard no-dash rule. If a default contradicts your real style (you use dashes deliberately, "robust" is your field's vocabulary), relax it in your own config and record the override in your voice profile so both layers agree: [`tools/examples/relaxed.json`](skills/pherkad/tools/examples/relaxed.json) shows the shape, [`tools/examples/news-brief.json`](skills/pherkad/tools/examples/news-brief.json) shows team-specific additions, and the profile builder can generate a personal config. Exit codes: 0 clean, 1 findings, 2 usage or IO error, so a crash never reads as "findings found."

## What Pherkad is and is not

- It validates against one voice: yours. A passage can be fully human-written and still fail because it does not sound like you, and an assisted passage can pass because it does.
- It never returns a bare score. Every number carries a quoted passage as evidence.
- It flags and fixes specific sentences rather than rewriting your piece.
- It does not police other people's text, and it is not a detector for grading student work.

## Your data

The voice profile is built from your writing and stays in your folder. This repository ships no profiles and no personal data; the only persona in it (Rosa Vantani) is fictional. Corrections you make ("that flag is wrong, that's really me") append to your profile, so the validator gets more accurate with use.

## Install

**Claude (Cowork or claude.ai with skills):** grab `pherkad.skill` from this repo if the prebuilt bundle is present, or build it in one command (below), then add it via Settings > Capabilities.

**Claude Code:** copy `skills/pherkad/` into your skills directory.

First run: ask for a voice check on any draft. Pherkad will notice you have no profile yet and run the profile interview first; bring 3 to 5 pieces of writing you consider most you.

## Build the .skill bundle

```
./build.sh
```

produces `pherkad.skill` (a zip of `skills/pherkad/`).

## Provenance

The tells catalog draws on the public "AI Tells" discussions (notably Julian Harris's 2026 thread), the Wikipedia "Signs of AI writing" page, and tells observed across many real AI-assisted documents. The seven-dimension structure and the density rule come from a private predecessor validated against one writer's published work before this generalization. The voicelint mechanical layer began as a house linter for a news-brief project and was generalized here.

## License

MIT. See [LICENSE](LICENSE).
