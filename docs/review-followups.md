# Review follow-ups (deferred)

The 0.4.2 pass fixed every confirmed linter bug, added tests and CI, and corrected the doc claims from the external review. Four findings were judgment calls, not bugs, and were held back on purpose. Each needs a design decision before it ships, so they live here rather than in a rushed release.

## 1. Split the generic defaults from house style

The default `voice_config.json` still carries rules that are source-quality policy, not voice tells: the `aggregator_domains` list and the `live` watch word came in from a news-brief linter. `examples/news-brief.json` already exists as a preset, so the move is to strip the news-specific rules out of the generic defaults and into that preset, leaving `voice_config.json` as cross-register patterns only. Held back because it changes default behavior for existing users and deserves a deliberate call on what counts as "generic."

## 2. Ship blind validation evidence for the judgment layer

The linter now has real test coverage, but the seven-dimension judgment pass has none that is public. The claim that a run gives an honest read of whether a draft sounds like its writer rests on a private single-writer predecessor. The fix is a small blind set: for two or three writers, hold out authentic prose, a deliberately flattened rewrite, an unusual-but-authentic piece, and another writer's prose, then record where Pherkad passes, revises, rewrites, and gets it wrong. This is the single strongest thing that would raise the tool from advisory to dependable, and the biggest lift.

## 3. Profile holdout check

The profile is built and assessed on the same samples. A holdout step (build from all but one sample, then test whether the validator flags the held-out piece as characteristic, plus a flattened rewrite and another writer's piece) would show a writer where their profile succeeds and fails before they trust it. A `profile_builder.md` addition, not code.

## 4. Corpus-level drift and standalone packaging

Two smaller product gaps. Drift: store dated validation summaries and periodically surface changes in positive-marker frequency, recurring false positives, and new vocabulary allowances, presented for the writer to accept or reject rather than auto-applied. Packaging: the `.skill` bundle covers Claude install, but the standalone linter is copy-the-file only; a tagged release with `voicelint.py`, the configs, and a one-command or `pipx` install would make "put it in your CI" real.

---

None of these blocks the current use as an advisory self-review tool. They are the path from advisory to a dependable gate.
