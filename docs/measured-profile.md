# The measured profile (design, 2026-09-16)

## Why

The first detect pilot (`oversight-research/papers/authorship_oversight/pherkad_pilot_2026_09_16.md`) found that a judge given the prose profile separates the author's text from flattened text no better than a judge given nothing. The prose profile is a model's description of the writing; nothing in it is counted, so nothing in it can be tested, and the judge reads polish instead. The fix is to make the profile out of the author's own hand-written text, as numbers first, and to let the prose, the checks, the revision, and the authoring all derive from those numbers, so that every claim about the voice points at counted evidence and the harness can score it.

## Inputs: samples with provenance

A samples folder in the author's private repository (`/Users/moriarty/Documents/voice-profile/samples/`), never in Pherkad. Every sample has a manifest line: id, path, provenance, surface, date, words, sha256. Provenance is one of `hand` (typed by the author, no model in the loop), `captured` (the author's words recorded by an assistant with minimal shaping; the saga captures), `approved` (AI-assisted, author-edited; what the pilot had). Nothing enters without a provenance and a surface, and the tool never guesses either. `hand` builds the profile; `captured` is admitted with a lower weight and its own register; `approved` is excluded from building and kept for testing only, since a profile built from text the tool already shaped would be circular.

Importers: a mailbox export the author runs himself (sent messages, quoted replies and signatures stripped, one sample per message over a length floor, surface `email`); the saga's `CAPTURED.md` split into one sample per capture (surface `narrative`, provenance `captured`); loose files dropped in the folder (surface and provenance asked once, recorded in the manifest).

## The fingerprint (`fingerprint.py build`)

Stdlib, deterministic, from the samples alone. Per surface and pooled:

- Sentence length: mean, standard deviation, quartiles, share under 8 words and over 35; run structure (how often a long sentence follows a short one).
- Paragraph shape: sentences per paragraph, share of one-sentence paragraphs, share of paragraphs that end on a short sentence.
- Openers: sentence-initial word classes (first person, conjunction, article, subordinator, number), and the twenty most frequent first words.
- Closers: paragraph-final sentence length relative to the paragraph; document-final sentence patterns.
- Function words: relative frequency of the 150 most common English function words, the standard stylometric signature, with the author's per-sample variance so a deviation is measured in his own units.
- Punctuation: commas, colons, semicolons, parentheses, quotation marks, dashes per sentence; contraction rate; question rate.
- Constructions: the rates of the shipped tells (candour announcements, contrast frames, pointers, staccato, mystery tails), hedges, intensifiers, passive-shaped verb phrases, sentence-initial And, But, So.
- Distinctive vocabulary: words and bigrams over-represented against a plain reference (the flattenings and the impostor texts already in the eval corpus serve as the first reference; a public general-English frequency list later).
- Evidence: every feature stores up to five quoted sentences with the sample id, so the prose profile and the checks can cite them.

Output: `fingerprint.json` with the sample ids it was built from, their hashes, the tool version, and the date, so a profile can be rebuilt and a change explained.

## Recognition (`fingerprint.py compare`)

A text is compared to the fingerprint feature by feature: each feature's deviation in the author's own standard-deviation units, the features that deviate most, and a quoted example for each. `pherkad.py check --fingerprint F` adds these as `voice.<feature>` findings (advisory by default), and the detect harness gets a `fingerprint` condition: a verdict from distance alone, no model. That gives a number nobody can argue with: does the measured profile tell the author from flattened text and from impostors better than the model judge did (+0.26 and +0.83 lift over the pilot's controls)?

## What the first mail test taught (2026-09-17)

Distance to the author's mean cannot recognise the author: a flattening is generic, generic sits near everyone's mean, and on eight held-out emails the flattening was nearer than the original on 15 of 16 pairs. Recognition needs a second profile of what the author is not. `build-reference` makes one from flattenings or from other writers, and the discriminant over the features where the two profiles part company put the held-out email above its flattening 16 of 16 times, with the reference built from other emails' flattenings each time. The same score does not tell the author from six cohort notes, because the reference was flattenings, so what it learned is hand-typed mail against machine prose. Each reference answers one question; the next is a reference of other writers' mail.

## Prose from numbers (`fingerprint.py prose`)

The prose profile is rendered from the fingerprint, each claim carrying its count and one quoted sentence with its sample id. A model may polish the rendering under review, but it may not add a claim the numbers do not make. `Voice_Profile.md` stops being the source of truth and becomes a view.

## Learning

Two channels, both already partly built. New samples: `samples.py add` records them and `build` reruns; the fingerprint's sample list says what changed. The author's edits: `corrections.py add --from-diff draft.md edited.md` mines phrase-level changes between an AI draft and the author's edit into the ledger as candidates; nothing becomes a rule without the corpus count and his approval, as now. A factual correction still never becomes a style rule.

## Authoring on demand (`pherkad.py author`)

Builds a packet: the surface, the measured constraints written as instructions (a sentence-length band, the opener and closer habits, the contraction rate, what never appears), the nearest exemplars from the samples for that surface, the notes to write from, and the output schema. A runner writes; `compare` and `check` score the result; the loop repeats within a bound until the draft sits inside the author's own band. Model-agnostic through the runners; nothing here rewrites his prose without the harness having said the packet produces text closer to him than a bare prompt does (the authoring experiment, `study.py plan --task author`).

## Order

1. Samples folder, manifest, provenance rules, the CAPTURED.md importer, the mailbox importer.
2. `fingerprint.py build` and `compare`, with tests, run on whatever `hand` samples exist plus the pilot corpus as the test set.
3. The `fingerprint` condition in the detect harness; rerun detect on the pilot corpus with the fingerprint alongside the model judge.
4. `prose` rendering; `Voice_Profile.md` regenerated from it and diffed against the hand-written one.
5. `corrections.py --from-diff`.
6. `pherkad.py author` and the authoring experiment.

Each step is a release with its own count, and steps 2 and 3 are the ones that decide whether the rest is worth building.
