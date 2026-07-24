# Review follow-ups (deferred)

The 0.4.2 through 0.4.4 passes fixed the confirmed linter bugs then known, added tests and CI, and corrected the documentation claims from the external reviews. The remaining items below are design or validation work that was held back on purpose. Each needs a decision before it ships, so it lives here rather than in a rushed release.

## 1. Split the generic defaults from house style (done)

The source-quality rules left the generic defaults in 0.4.3: `aggregator_domains` is empty and the `live` watch word is gone from `voice_config.json` and the built-in fallback. The news-brief closers moved to `examples/news-brief.json` in 0.4.4. No source policy or news register rule remains in the generic defaults. The open question is whether any other default reflects the maintainer's register more than a pattern that travels across registers. Test that question against the blind set below.

## 2. Ship blind validation evidence for the judgment layer (protocol written; dataset open)

The linter now has real test coverage, but the seven-dimension judgment pass has none that is public. The claim that a run gives an honest read of whether a draft sounds like its writer rests on a private single-writer predecessor. The protocol for closing this is written in `docs/blind-eval.md`: for several writers, hold out authentic prose, a deliberately flattened rewrite, an unusual-but-authentic piece, another writer's prose, and an override sample, then report where Pherkad passes, revises, rewrites, and gets it wrong, with the failures quoted. What remains is building the dataset from real samples and running it. This is the single strongest thing that would raise the tool from advisory to dependable, and the biggest lift.

## 3. Profile holdout check (done)

Added to `profile_builder.md` as Step 4b: reserve one sample the profile never saw, then check that the profile recognizes the held-out sample, revises a flattened rewrite of it, and does not accept another writer's piece, before the profile is trusted. It is a per-writer sanity check, not method-level evidence; that is item 2.

## 4. Corpus-level drift and standalone packaging

Two smaller product gaps. Drift: store dated validation summaries and periodically surface changes in positive-marker frequency, recurring false positives, and new vocabulary allowances, presented for the writer to accept or reject rather than auto-applied. Packaging: the `.skill` bundle covers Claude install, but the standalone linter is copy-the-file only; a tagged release with `voicelint.py`, the configs, and a one-command or `pipx` install would make "put it in your CI" real.

---

None of these blocks the current use as an advisory self-review tool. They are the path from advisory to a dependable gate.
