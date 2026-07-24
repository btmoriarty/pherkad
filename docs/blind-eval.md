# Blind evaluation of the judgment layer

This is the plan for the one piece of evidence Pherkad does not yet have: a blind test showing that the seven-dimension validation pass actually tells whether a draft sounds like its writer, and that it does so because of the writer's profile rather than a generic model judgment about polish. The mechanical linter is tested. The judgment layer, which carries the "sounds like you" claim, is not. Until the study below is run and reported with its failures, the honest claim stays "structured, evidence-citing review," not "reliable voice validation."

This file is the protocol. The dataset needs real writer samples and is built with the maintainer, not shipped in this repo.

## Why it is the highest-value work

Every review round so far has hardened the linter. The linter can only show that configured patterns occur; it cannot show that prose carries a person's voice. A profile is currently built and judged on overlapping samples, so a good-looking verdict may be circularity rather than recognition. A blind study with the right controls closes that gap directly, and it is worth more now than any further rule polish.

## The one comparison that matters: correct-profile lift

A run that passes an authentic sample and revises a flattened one has shown nothing on its own if it would do the same with the wrong profile, a shuffled profile, or no profile at all. The model may be reacting to polish, specificity, or register, not to the writer. So the primary result is a comparison, not a pass rate:

Run every item under four conditions and compare the verdicts:

- the writer's correct profile,
- a different writer's profile, matched on register,
- a shuffled profile (the correct markers scrambled or paired to the wrong dimensions),
- no profile (a profile-less scan), and as a floor, the linter alone.

**Correct-profile lift** is how much better the right profile separates authentic from flattened, and this writer from an impostor, than the wrong, shuffled, absent, and linter-only conditions. If lift is near zero, Pherkad is scoring generic writing quality, not voice, whatever its reports say. This is the single most important measurement and the protocol is built around it.

## Case types

For each writer, assemble labeled items. Keep the labels out of the text the validator sees.

- Authentic samples used to build the profile.
- Authentic held-out samples the profile never saw, including at least one deliberately atypical piece (an unusual but real register or subject), since penalizing a writer's own unusual prose is a named failure mode.
- Flattened rewrites of a held-out sample, at least two per sample, each produced by a different editor or model family that cannot see the profile. Preserve facts, concrete examples, argument, and paragraph function; neutralize framing, syntax, hedging, transitions, and rhythm only; keep within 10 percent of the source length. Before using a flattening, confirm it carries the same facts and specific detail as its source, so the contrast measures voice and not lost content; a thinner text is a confound, not a flatter voice. Do not build a flattening by deleting the profile's listed markers; that tests obedience, not recognition.
- Hard impostors: several different writers per subject, matched as closely as possible on register, topic, length, and expertise. One easy impostor proves little.
- An override sample: an authentic piece that legitimately uses a catalog phrase or a habit the profile allows, to check overrides hold.

## Registers, within and across

Coverage has to be within a writer, not only across the set. A profile that carries an essay, a technical analysis, and an informal email is the multi-register claim the profile builder makes. So for at least some writers, build the profile in one register and test held-out samples in another, and include a mixed-register profile. "Varied registers across the writers" does not establish that one profile handles one writer moving between registers.

## Roles and blinding

Separate the roles across people or model families wherever possible: whoever builds the profile should not be whoever writes the flattenings, and neither should be the judge. If one model family builds, flattens, authors, and judges, shared style and preferences can manufacture apparent success that is not recognition. Blind the validation run to each item's true class, and keep the profile builder, flattening author, and operator from seeing the labels they could act on.

## External reference judgment

The labels assume authentic equals voice-consistent and flattened equals voice-inconsistent. Check that assumption: have the writer and one or two independent readers judge, blind and pairwise, which of a paired authentic-and-flattened passage sounds more like the writer. If human readers cannot tell the pair apart, Pherkad should not be scored for getting it "wrong," and if they can, their judgment is the reference Pherkad is measured against.

## Definitions to freeze before the run

Vague terms make the result unfalsifiable. Before running, write down:

- **Light REVISE:** a REVISE driven by minor surface hits, not by a missing-positive-markers finding. An authentic held-out sample may draw a light REVISE and still count as recognized; a missing-markers REVISE does not.
- **Run count:** how many times each item is run (at least three, not "more than once").
- **Model and sampling:** the exact model version, temperature, and sampling settings, frozen for the study and recorded.
- **Stability:** report exact-verdict agreement, adjacent movement (PASS to light REVISE), and severe movement (PASS to REWRITE) separately. A single adjacent step is not the same failure as a PASS/REWRITE reversal.
- **Thresholds:** the pass bar and the lift threshold that would count as success, set before the run so the go/no-go is not decided after seeing the numbers.

## Pass bar (per condition, under the correct profile)

- Held-out authentic sample: PASS or light REVISE, positive markers present.
- Flattened rewrite: REVISE or REWRITE, driven by the positive-register read, not only by tells.
- Impostor: not PASS as this writer, and the reason cites voice mismatch, not an unrelated stray hit.
- Override sample: not failed on the allowed habit.
- Correct-profile lift: authentic-versus-flattened and writer-versus-impostor separation is meaningfully larger under the correct profile than under wrong, shuffled, absent, and linter-only.

## What to measure

Report, per writer, not only pooled:

1. Correct-profile lift over wrong, shuffled, absent, and linter-only.
2. Authentic acceptance rate, by writer and register.
3. Flattened rejection rate, across the independent flattenings.
4. Impostor rejection rate, across the matched impostors.
5. Paired discrimination margin: the verdict and score separation between each authentic passage and its flattened counterpart.
6. Cross-register generalization: train in one register, test in another; and mixed-register profiles.
7. Run stability: exact agreement, adjacent movement, severe movement.
8. Explanation stability: whether the same markers and evidence are cited across runs.
9. Rewrite fidelity: facts, qualifications, emphasis, and terms of art preserved.
10. False-edit burden: authentic sentences rewritten unnecessarily.
11. Writer-rated usefulness: whether the named failures and proposed rewrites are actually right.
12. Authoring performance (below).

## Preregistration

Write these down before collecting a single verdict, and do not change them after seeing results. This is what separates a study from a story.

- **Estimand.** The average correct-profile lift: the difference in the "sounds like the writer" outcome between the correct-profile condition and the pooled controls (wrong, shuffled, none), across writers.
- **Analysis unit.** The writer, not the passage. Passages within a writer are correlated, so the writer is the independent unit and the count that drives the result.
- **Primary outcome (one formula, frozen).** The rating is the 1-to-5 "sounds like the writer" score. Per writer, lift = the mean rating under the correct profile minus the mean rating under the pooled controls (wrong, shuffled, none), the three controls weighted equally. Aggregate as the across-writer mean lift with a confidence interval. The paired authentic-versus-flattened discrimination margin, and any verdict-based score, are named secondary outcomes, not the primary. If a verdict is scored at all, encode it once and in advance (for example PASS 4, light REVISE 3, REVISE 2, REWRITE 1) and keep it secondary; the primary is the rating.
- **Interval method.** A cluster bootstrap over writers, or a mixed-effects model with a random intercept per writer. Report the interval, not just the point estimate.
- **Multiplicity.** Name the one primary outcome (lift) in advance. Everything else (per-register rates, stability, fidelity) is secondary and reported as secondary, not promoted to the headline after the fact.
- **Power.** State the smallest lift worth detecting and the writer count needed to detect it at the chosen interval width. Five to eight writers is a pilot that cannot power a confirmatory claim; size the confirmatory run to the effect, not the reverse.
- **Failure criteria.** Fixed before the run: the lift below which the profile is judged to add no writer-specific value, the flattened-pass rate above which the positive-register read is judged unreliable, and the run-to-run verdict swing above which the judgment is judged unstable. If any triggers, the claim stays advisory and says so.

## Authoring arm

Authoring mode claims to write in the user's voice, and nothing demonstrates it. Add an arm:

- Give the model factual briefs or notes, not source prose it can imitate, so it composes rather than paraphrases.
- Generate under the correct profile, a wrong profile, and no profile.
- Have a different model family, and the writer, rank the drafts blind.
- Measure factual preservation, excess certainty, marker stuffing, and caricature.
- Run rewriting-existing-prose and drafting-from-notes as separate tasks; they are different claims.

Self-validation by the same model is a useful drafting discipline. It is not independent validation.

## Sizing: pilot, then confirmatory

Five to eight writers is a pilot. The writer is the unit that matters, and many passages from a few writers do not substitute for writer diversity. Use the pilot to freeze the process, surface failure modes, and check that the controls run. Then run a larger preregistered evaluation, roughly 20 to 30 writers, with writer-level reporting and uncertainty intervals, before making any claim beyond advisory.

## Reporting

Report the confusion cases, not only the wins: authentic prose Pherkad revised, flattened prose it passed, an impostor it accepted, verdicts that moved between identical runs, rewrites that removed a real marker. A short table per writer, the per-condition lift, and the failures quoted. Publish it in this repo so the central claim rests on evidence a reader can inspect.

## What the result would change

- If lift is near zero, or flattened held-out prose regularly passes, or unusual authentic prose is regularly revised, or verdicts swing between identical runs: the "sounds like you" claim is not supported, and the README and skill stay advisory and say so.
- If the correct profile shows real lift and the pass bar holds across writers and registers: the claim can be stated with the evidence behind it, and a team could reasonably consider the verdict as more than advisory.

Either way, the honest move is to run it before making the stronger claim, not after.
