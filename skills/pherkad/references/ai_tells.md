# AI Tells Catalog

The generic half of Pherkad's diagnostic: constructions and phrases that mark AI-generated or AI-flattened prose regardless of whose voice is being validated. Personal markers live in the user's `Voice_Profile.md`, not here.

Sources: patterns documented in the public "AI Tells" discussion threads (notably Julian Harris's 2026 thread), the Wikipedia "Signs of AI writing" page, and tells observed across many real AI-assisted documents. The category labels 5a-5i correspond to Dimension 5 of the skill protocol.

---

## 5a. Banned intensifiers and filler words

Flag every instance, subject to the caveats at the end of this file:

- significant, crucial, essential, important, key, robust
- leverage (as verb), utilize
- genuinely, honestly, straightforward
- load-bearing (outside literal engineering)
- delve, delves into, delving
- tapestry
- underscores (as verb meaning "emphasizes")
- showcases
- navigating (as metaphor, e.g. "navigating the complexities of")
- in the realm of
- it's worth noting, it is worth noting, it's important to note
- essentially, fundamentally
- ultimately (when hedging, not when sequencing)
- in many ways
- a testament to
- speaks to

## 5b. Flattened stock phrases

Phrases that recur in AI-assisted drafts where a plain clause would serve:

- empirical anchor
- methodological foundation
- rests on
- necessary-but-invisible
- game-changer, paradigm shift
- unlock the potential of

## 5c. Antithesis construction family

A rhetorical family models over-rely on. Detect the structural pattern, not just word matches:

1. "It doesn't just X. It Y."
2. "X isn't just Y; it's Z."
3. "This is not X. It is Y." (and the mirror: "This is not just X. It is Y.")
4. "X to the Y's Z."
5. "Not just X, but Y."
6. "X doesn't merely Y; it Z."

**Single instances can be authentic.** The tell is clustering: two or more antithesis-family constructions in adjacent sentences signals AI flattening. Report density across the document, not just individual hits.

## 5d. Scene-setting and hedge openers

Flag whenever one opens a paragraph:

- "Situated [adverbial phrase], the [noun] [verb]..."
- "In a world where..."
- "In the rapidly evolving landscape of..."
- "As we navigate..."
- "Today, more than ever..."
- "In recent years..."
- "Picture this:"
- "Imagine [scenario]..."

## 5e. Engagement-bait transitions

Social-post-genre tells; flag in any public-facing prose:

- But here's the part no one is talking about
- Here's what they don't tell you
- And that's the thing
- Here's the real question
- The truth is
- Let me tell you why
- And here's why that matters
- Plot twist:

## 5f. Triplet noun piling

Three abstract nouns coordinated where one or two would have served. Pattern: "[adjective]+[noun], [adjective]+[noun], and [adjective]+[noun]" with all three nouns abstract.

Examples: "clarity, transparency, and accountability"; "engagement, calibration, and trust"; "innovation, collaboration, and growth."

Single instances may be authentic; two or more triplets in a paragraph signals AI.

## 5g. Counter-X constructions

"Counter-" prefixed to an abstract noun where a plain word would serve: counter-symbol, counter-narrative (unless the literal subject), counter-intuitive (the hyphenated form specifically), and the shape "a [noun] of [hyphenated abstract]."

## 5h. Authenticity-language paradox

Words meant to signal sincerity that become tells when models use them to sound human:

- genuinely, honestly (already in 5a)
- truthfully, frankly, candidly
- to be honest, in all honesty
- I'll be real with you

## 5i. Structural and stylistic artifacts

- Hedge-stacking (piling "may," "potentially," "somewhat" into one sentence)
- Parallel tricolon structure used more than twice in a piece
- "Furthermore" / "Moreover" / "Additionally" as paragraph openers
- Balanced-nothing sentences ("While X is important, Y is equally critical")
- Generic abstraction where the profile shows the writer using concrete specifics
- Summary paragraphs that restate the introduction
- "In conclusion" / "To summarize"
- "This raises important questions about"
- "The landscape of"
- "at the end of the day" / "the bottom line is"
- Corporate-meeting idioms used non-literally ("didn't land," "needs sharpening," "circle back," "in flight")
- Self-narrating closers ("writes itself," "needs no embellishment," "that's the news") and reader stage-directions ("watch the move," "note the framing"). End on the substantive point instead
- Reach-for-an-analogy connectives ("the mirror image of," "rhymes with," "the flip side of")
- Trailing "quietly" (mechanical): "quietly" ending a clause or sentence ("shut it down quietly," "the numbers moved quietly") is the insinuating position, implying concealed intent. The linter flags it; put the adverb before the verb or cut it
- Pre-modifier "quietly + verb" (judgment): "quietly shelved," "quietly building" can imply hidden agency, but the same shape carries legitimate stance ("quietly skeptical," "quietly noticing"). Not mechanical; flag only when the intent is concealment, not stance
- Crutch-word overuse: any word the profile lists as a personal crutch, past its soft cap
- Harsh rhetorical dismissals ("useless," "dumb," flat "bad" with no specifics). A voice critiques by naming the failure, not labeling the thing
- Compound-hyphen abstractions ("better-serving-the-question"). Expand into a clause instead
- Em dashes. Flag them: heavy em dash use is a documented AI tell. **Profile override:** if `Voice_Profile.md` records deliberate em dash use with evidence, flag only overuse (three or more in a paragraph, or dashes doing work commas would do)

---

## Positive register: calibrate toward, not only against

The catalog above says what to remove. It cannot say what a voice should sound like; that is the profile's job. But validation should carry a positive model, not only a ban list, or it flattens every draft toward a safe generic default. Read whether the draft shows the writer's own positive markers, drawn from the profile's Grounding, Texture, Mechanics, Structure, and Tone. Absence of tells is necessary, not sufficient: prose can be clean of every entry above and still read as competent, generic, and no one's.

The strongest positive markers are the most specific and least imitable. Common shapes, examples of the kind of move to look for, not a checklist to score:

- **Concrete before concept.** The writer leads with the physical thing and lets the reader infer the idea, rather than stating the abstraction.
- **Flat consequence.** An outcome stated without the emotional adjective, so the plainness carries the feeling.
- **The telling specific detail.** The incidental, slightly off detail that fixes a scene and marks it as lived. This is the single strongest signal of human provenance, and the move a model is least likely to make.
- **Owned, not deflected.** When the failure or the stake is the writer's own, the voice names it plainly rather than distributing it to a structure.

Read the profile for this writer's own version of these. When a draft is clean of tells but shows none of the writer's positive markers, that is a REVISE-level signal on its own: the voice has flattened even though nothing is technically wrong.

## Genre calibration

Distinctiveness lives in the frame, the transitions, and the close. The analytical, legal, or technical core of a piece stays plain, precise, and short, and it is correct when it is plain. Do not smooth a writer's positive markers evenly across a passage that must be exact, and do not flag a precise passage for failing to be vivid. A finished piece is often deliberately uneven: a distinctive frame around an exact middle, and the unevenness is the design. Apply the positive-register read to the frame and the transitions; hold the technical core to precision and to the tell catalog, not to the archetype.

---

## The mechanical layer

A subset of this catalog is literal enough for regex: `tools/voicelint.py`, a dependency-free Python linter with the rules in `tools/voice_config.json`. It gives exact line and column numbers, runs in CI or pre-commit (exit 1 on error-level findings, `--strict` to fail warnings, `--json` for machines), and its shipped defaults were built from tells observed across many AI-assisted documents.

When validating and a Python runtime is available, run it first and fold its findings into Step 3 as pre-located hits. What it cannot see (antithesis structure, triplet piling, clustering, tone, profile match, and the positive register) remains this catalog's judgment work. The linter's config is tunable per person or team: `tools/examples/relaxed.json` shows loosening a default the writer's profile contradicts (deliberate dash use), `tools/examples/news-brief.json` shows team-specific additions, and the profile builder can generate a personal config. A relaxation should match an evidence-backed profile override so this layer and the linter agree.

---

## Density meta-rule

A bigger tell than any single phrase is prose heavily peppered with them. The validator produces two outputs:

1. **Individual hits**: every match, listed by sentence.
2. **Density signal**: flagged constructions per 100 words. Above 2.0 triggers a density warning even when no single hit would force a REVISE.

The density signal catches flattened prose built from individually allowed words in characteristic clusters.

---

## Caveats and what NOT to flag

- **Technical-literal uses.** "Key" as API key, JSON key, or primary key; "load-bearing" in structural engineering; "delve" in archaeology; "tapestry" in textiles; "showcases" as literal display cases; "navigating" as actual navigation. Extend to any banned item where domain context makes the word the subject.
- **Direct quotes** from sources where the quoted person uses a flagged phrase. Reporting, not endorsing.
- **Single instances** of antithesis, triplet, or hedge constructions. Real writers use contrast. Density is the tell.
- **Informal registers** (chat messages, casual email) where a relaxed register is appropriate. The validator is for drafts intended as public posts, papers, and finished prose.
- **Documents that teach this pattern list**: this catalog, the profile, validator-internals docs, and any text that discusses the patterns by name. Ignore hits inside lines that quote, name, or define the patterns; flag only the prose proper.
- **Precise cores.** Do not flag a legal, statutory, or technical passage for reading plainly; see Genre calibration above.
- **Profile overrides.** Whatever `Voice_Profile.md` explicitly claims as the writer's real habit, with evidence, wins over a default in this catalog, except the density meta-rule, which always applies.
