# Voice Profile Builder

How to build `Voice_Profile.md`, the personal half of Pherkad. Run this once on first use, then update it as corrections accumulate. The profile lives in the user's working folder and never enters this repository.

## Ground rules

- The profile describes how the user actually writes, evidenced by their real samples. If the user wants to record an aspiration ("I want to stop hedging so much"), store it in a clearly labeled Aspirations section; score against the evidence, mention aspirations only in rewrites.
- Every marker in the profile must be backed by at least one quoted sentence from the user's samples. No marker without evidence, same rule as validation itself.
- The profile is the user's data. Do not summarize it into chat beyond what is needed to confirm accuracy, and never suggest committing or publishing it.

## Step 1: Collect samples

Ask for at least four pieces the user considers most "them" (five or more if they write in several registers): blog posts, essays, papers, long emails. One of these is reserved as the holdout below before any is read for markers, so four is the floor, not three. Aim for 1,500+ words total. For each, note the register (public post, paper, informal). If the user has both formal and informal registers, say the profile will carry both and validation will use whichever fits the draft.

Prefer pre-AI or lightly assisted samples. If the user suspects a sample is already flattened, exclude it or mark it low-confidence.

**Set the holdout aside first.** Before reading any sample for markers, choose one sample as the holdout for Step 4b and record its file name or a hash. Do not load its text during marker extraction, profile drafting, user correction, or config generation. Reveal it only after the profile is frozen for the check. A sample the model has already read cannot be made unseen, so the holdout has to be reserved before Step 2, not relabeled after. This means Step 1 should collect enough that one can be spared (aim for at least four).

## Step 2: Extract markers

Read the non-holdout samples, then draft the six personal dimensions. For each, write 2 to 4 markers plus quoted reference sentences:

1. **Grounding and authority.** Where does authority come from: lived observation, argument, data, craft, reporting? Who is the narrator relative to the subject (inside the work, above it, beside the reader)?
2. **Epistemic calibration.** Preferred hedging verbs and confidence ceiling. Does the writer make predictions? Prescriptions? How do endings behave (resolve, open, trail off)?
3. **Texture.** What concrete specifics recur: times, places, tools, named roles, sensory detail, numbers? What density of specifics per section is normal?
4. **Sentence mechanics.** Length variation, rhythm, fragments, punctuation habits (em dash stance, semicolons, parentheticals), humor style, favorite constructions. Capture explicit bans and explicit allowances; an allowance that loosens a default in `ai_tells.md` needs evidence in the samples (except the density meta-rule, which always applies).
5. *(Dimension 5 is the shared catalog; nothing personal to extract, but record any evidence-backed override here, e.g. "uses em dashes deliberately" or "the word 'robust' is domain vocabulary in my field.")*
6. **Structural habits.** How pieces open and close, what stays implicit, paragraph length, use of headers and lists.
7. **Tonal identity.** Three to five adjectives with evidence, plus an equally specific list of what the writer never sounds like.

## Step 2b: Capture the positive register (the archetype)

The six dimensions above capture what the writer avoids and prefers. Also capture what the voice actively does, its most specific and least imitable moves, so validation can calibrate toward the writer and not only against tells (see "Positive register" in `ai_tells.md`). From the samples, name two to four positive moves, each with a quoted example. Shapes to look for, examples and not a checklist: leading with a concrete object before the concept; stating a consequence flatly without the emotional adjective; the telling incidental detail that marks a scene as lived; owning a failure plainly rather than deflecting it to a structure. Record these as an Archetype section in the profile. These are strong profile-match signals because they are specific to the writer's samples. Treat them as evidence of voice fit, not evidence of how the passage was produced. Note which markers belong to the frame and the close rather than the precise analytical core, so validation does not flatten a technical passage toward the archetype (see Genre calibration in `ai_tells.md`).

## Step 3: Confirm with the user

Show the draft profile. Ask the user to correct anything that reads wrong and to add bans or allowances the samples did not surface. Their corrections win over inference.

## Step 4: Write the profile

Save as `Voice_Profile.md` in the user's working folder, following the shape of `example_profile.md`. Include a "One paragraph" summary at the end: the whole voice compressed, ending with a test like "if a passage could have been written by anyone, it is not this writer."

## Step 4b: Hold a sample back and check the profile generalizes

A profile built and judged on the same samples can look sharper than it is: the markers were read off those exact pieces, so of course they match. Before treating the profile as ready, run one holdout check against the sample set aside in Step 1, which the profile never saw.

Assemble three kinds of text (below), then run the check blind: shuffle them, strip the labels, and do not tell the validating pass which item is which or what verdict you expect. Record its verdicts, then reveal the labels and compare. If the pass knows an item is "the authentic one" or "the flattened one," it can return the expected answer from the cue rather than from the writing, and the check proves nothing. Run the validation in a fresh context from the profile building where you can.

The three kinds, and what a blind pass should produce if the profile is good:

1. The held-out sample. It should read as the writer: the positive markers should be present and the verdict should land at PASS or a light REVISE (a REVISE driven by minor surface hits, not by a missing-markers finding). If the profile does not recognize the writer's own unseen writing, the markers are overfit to the extraction set; widen them.
2. A flattened rewrite of the held-out sample. Have a separate editor or a model that cannot see the profile produce it: preserve the facts, the concrete examples, and the paragraph order; neutralize only framing, unusual syntax, characteristic hedges, recurring transitions, and sentence-length variation; and keep it within 10 percent of the source word count. Before using it, confirm the rewrite carries the same facts and specific detail as the source, so the check measures voice and not lost content; personal examples are often evidence, not decoration, and stripping them would confound a thinner text with a flatter voice. Do not build the rewrite by deleting the profile's listed markers one by one; that tests obedience to the profile, not recognition of naturally flattened prose. It should draw a REVISE or REWRITE on the positive-register read, even if it trips no banned phrase. If it passes, the profile is only catching tells, not carrying voice.
3. Two or three short pieces by different writers in the same register, matched as closely as you can on topic, length, and level of expertise. None should read as this writer. If any passes, the profile is too generic to distinguish nearby writers, not just an obviously different one.

Record the results in the profile as a dated "Holdout check." **A failed holdout is spent.** If a result is wrong and you change the profile to fix it, that sample has joined the development set: rechecking it only shows the fix fitted the known failure. Retire it and confirm the revised profile on a new untouched sample. This is a sanity check on one writer, not a validation of the method; the method-level evidence is the multi-writer blind set in `docs/blind-eval.md`.

## Step 5: Offer a personal linter config

Offer to generate a personal `voice_config.json` for the mechanical layer (`tools/voicelint.py`) from the profile: the dash stance from Dimension 4 (keep the default hard ban, or relax to the density cap if the profile shows deliberate dash use), personal crutch words as `watch_words` soft caps, and any extra banned phrases the user names. Save it next to their profile. The shipped defaults reflect tells observed across many documents; relaxations and additions live in the user's copy, and any relaxation should match an evidence-backed override in the profile so both layers agree.

## Step 6: Maintain

When a validation flag is wrong and the user says "that one is actually me," append the correction to the profile with the quoted sentence as evidence. When the user's writing context changes (new field, new format), offer a profile refresh from fresh samples rather than patching indefinitely.
