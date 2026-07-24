# Blind evaluation of the judgment layer

This is the plan for the one piece of evidence Pherkad does not yet have: a blind test showing that the seven-dimension validation pass actually tells whether a draft sounds like its writer. The mechanical linter is tested. The judgment layer, which carries the "sounds like you" claim, is not. Until the test below exists and is reported with its failures, the honest claim stays "structured, evidence-citing review," not "reliable voice validation."

This file is the protocol. The dataset needs real writer samples and is built with the maintainer, not shipped in this repo.

## Why it is the highest-value work

Every review round so far has hardened the linter. The linter can only show that configured patterns occur; it cannot show that prose carries a person's voice. A profile is currently built and judged on the same samples, so a good-looking verdict may be circularity rather than recognition. A small blind set closes that gap directly, and it is worth more now than any further rule polish.

## What the set has to contain

For several writers (aim for five to eight, varied registers), collect, per writer:

- Two or three authentic samples used to build the profile.
- One or more authentic held-out samples the profile never saw.
- A flattened rewrite of a held-out sample: same content, voice stripped toward a generic default (balanced sentences, stock connectives, texture removed), clean of obvious banned phrases so it tests the positive-register read rather than the linter.
- A sample by a different writer in the same register.
- One authentic sample that legitimately contains a catalog phrase or a deliberate habit the profile allows, to test that overrides hold.

Label each item with its true class. Keep the labels out of the text the validator sees.

## How to run it

For each writer, load only that writer's profile, then run a normal validation pass on each item blind (the run must not see the label). Record the verdict (PASS / REVISE / REWRITE), the positive-register finding, and the dimension scores. Run each item more than once to measure stability, since the judgment layer is a model and may vary.

## What counts as a pass for Pherkad

- Held-out authentic sample: PASS or light REVISE, positive markers present.
- Flattened rewrite: REVISE or REWRITE, driven by the positive-register read, not only by tells.
- Another writer's sample: not PASS as this writer.
- Override sample: not failed on the allowed habit.
- Stability: the same item does not swing across PASS/REVISE/REWRITE between identical runs.

## Reporting

Report the confusion cases, not only the wins. The useful output is where Pherkad gets it wrong: authentic prose it revises, flattened prose it passes, another writer it accepts, verdicts that move between runs. A short table per writer, plus the aggregate rates and the failures quoted, is enough. Publish it in this repo so the central claim rests on evidence a reader can inspect.

## What the result would change

- If flattened held-out prose regularly passes, or unusual authentic prose is regularly revised, or verdicts swing between identical runs: the "sounds like you" claim is not yet supported, and the README and skill language should stay advisory and say so.
- If the set holds up: the claim can be stated with the evidence behind it, and a team could reasonably consider the verdict as more than advisory.

Either way, the honest move is to run it before making the stronger claim, not after.
