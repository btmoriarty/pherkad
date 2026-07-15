# Voice Profile Builder

How to build `Voice_Profile.md`, the personal half of Pherkad. Run this once on first use, then update it as corrections accumulate. The profile lives in the user's working folder and never enters this repository.

## Ground rules

- The profile describes how the user actually writes, evidenced by their real samples. If the user wants to record an aspiration ("I want to stop hedging so much"), store it in a clearly labeled Aspirations section; score against the evidence, mention aspirations only in rewrites.
- Every marker in the profile must be backed by at least one quoted sentence from the user's samples. No marker without evidence, same rule as validation itself.
- The profile is the user's data. Do not summarize it into chat beyond what is needed to confirm accuracy, and never suggest committing or publishing it.

## Step 1: Collect samples

Ask for 3 to 5 pieces the user considers most "them": blog posts, essays, papers, long emails. Aim for 1,500+ words total. For each, note the register (public post, paper, informal). If the user has both formal and informal registers, say the profile will carry both and validation will use whichever fits the draft.

Prefer pre-AI or lightly assisted samples. If the user suspects a sample is already AI-flattened, exclude it or mark it low-confidence.

## Step 2: Extract markers

Read all samples, then draft the six personal dimensions. For each, write 2 to 4 markers plus quoted reference sentences:

1. **Grounding and authority.** Where does authority come from: lived observation, argument, data, craft, reporting? Who is the narrator relative to the subject (inside the work, above it, beside the reader)?
2. **Epistemic calibration.** Preferred hedging verbs and confidence ceiling. Does the writer make predictions? Prescriptions? How do endings behave (resolve, open, trail off)?
3. **Texture.** What concrete specifics recur: times, places, tools, named roles, sensory detail, numbers? What density of specifics per section is normal?
4. **Sentence mechanics.** Length variation, rhythm, fragments, punctuation habits (em dash stance, semicolons, parentheticals), humor style, favorite constructions. Capture explicit bans and explicit allowances; these override the defaults in `ai_tells.md` (except the density meta-rule).
5. *(Dimension 5 is the shared catalog; nothing personal to extract, but record any override here, e.g. "uses em dashes deliberately" or "the word 'robust' is domain vocabulary in my field.")*
6. **Structural habits.** How pieces open and close, what stays implicit, paragraph length, use of headers and lists.
7. **Tonal identity.** Three to five adjectives with evidence, plus an equally specific list of what the writer never sounds like.

## Step 3: Confirm with the user

Show the draft profile. Ask the user to correct anything that reads wrong and to add bans or allowances the samples did not surface. Their corrections win over inference.

## Step 4: Write the profile

Save as `Voice_Profile.md` in the user's working folder, following the shape of `example_profile.md`. Include a "One paragraph" summary at the end: the whole voice compressed, ending with a test like "if a passage could have been written by anyone, it is not this writer."

## Step 5: Offer a personal linter config

Offer to generate a personal `voice_config.json` for the mechanical layer (`tools/voicelint.py`) from the profile: the dash stance from Dimension 4 (hard ban, or the default density cap), personal crutch words as `watch_words` soft caps, and any extra banned phrases the user names. Save it next to their profile. The shipped defaults stay generic; personalization lives in their copy.

## Step 6: Maintain

When a validation flag is wrong and the user says "that one is actually me," append the correction to the profile with the quoted sentence as evidence. When the user's writing context changes (new field, new format), offer a profile refresh from fresh samples rather than patching indefinitely.
