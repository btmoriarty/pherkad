# Pherkad Cheat Sheet

One page. Everything Pherkad does and what to say to trigger it. It validates against one voice, yours; it never polices anyone else's text and never returns a score without quoted evidence. Say things in your own words; the phrases below are examples, not commands.

**First run:** ask for a voice check on any draft. With no profile yet, Pherkad interviews you first; bring at least four pieces of writing you consider most you. The profile lives in your folder and never leaves it.

| Mode | Say something like | What you get |
|---|---|---|
| **Build profile** | "build my voice profile" | A short interview over your samples, then `Voice_Profile.md`: your authority, hedging, texture, mechanics, structure, and tone, every marker backed by a quoted sentence of yours |
| **Quick check** (the default) | "does this read as me," "check this," "give it a look" | One command over both mechanical engines, then the judgment rules for the draft's surface, returned as one table: rule, quote, decision (fix / intentional / literal / not applicable / quoted), rationale, proposed edit; then one verdict line. Positive markers are expected only where the surface wants them |
| **Full audit** | "audit this," "validation report," "score it," or any paper, essay, or chapter | A fingerprint (the 3 sentences most and least like you), seven dimensions scored with evidence, the full catalog checked, density per 100 words, and a verdict: PASS / REVISE / REWRITE |
| **Targeted rewrites** | arrives with any REVISE or REWRITE verdict | Only the flagged sentences rewritten, each fix explained. Facts, names, numbers, dates, sources, and emphasis must stay as you had them; a rewrite that changes them is wrong, so check that it did not |
| **Correct a flag** | "that one is actually me" | The correction appends to your profile with the sentence as evidence, so a later run applies it instead of repeating the flag |
| **Personal linter config** | "make me a linter config from my profile" | Your dash stance, crutch-word caps, and extra bans as a `voice_config.json` the CLI linter can run in CI |
| **CLI check** | `python3 tools/pherkad.py check draft.md` | Both mechanical engines, one list, every finding with a stable rule id, no model needed. `--format json` or `--format sarif` for CI, `--advisory structure.` to keep the shape checks visible but non-blocking, `--decisions FILE` to hide what you have already ruled on. Exit 0 means no error-level findings, exit 1 means an error-level finding or a warning under `--strict`, and exit 2 means a usage, IO, or config error |
| **Reply preflight** | `python3 tools/replycheck.py -` | The same check on an assistant's chat reply before it is sent, under the `assistant-chat` surface; PASS or FIX. A Stop hook enforces it after the fact |
| **Judgment packet and rulings** | `python3 tools/pherkad.py review-pack --surface X draft.md`, then `review-import table.md --file draft.md --decisions FILE` | The packet is one prompt with everything a judgment run needs, inputs hashed. The import records the rows you ruled on (`intentional`, `literal`, `not applicable`, `quoted`); the next packet lists them so they are not raised again, and `pherkad.py decisions` marks a ruling stale once its sentence is gone |
| **Measured profile** | `python3 tools/samples.py add piece.md --dir SAMPLES --provenance hand --surface email`, then `python3 tools/fingerprint.py build --samples SAMPLES --out fp.json`, then `pherkad.py check --fingerprint fp.json draft.md` | Numbers from your own hand-written samples (sentence shape, openers, punctuation, constructions, function words), each with quoted evidence; the check reports what in a draft sits past two of your own standard deviations, quoting your sentence beside the draft's. Advisory, never counted |

**About the defaults:** the shipped rules are the author's own, built from tells observed across many AI-assisted documents, and they ship strict. Your register may differ: edit `tools/voice_config.json` to your purpose, or relax single rules in your own config (`tools/examples/relaxed.json` shows the shape) with the override recorded in your profile.

**Your data:** your voice profile is built from your writing and stays in your folder. The repository ships no personal data; its only persona is fictional.

**The one rule:** every verdict carries quoted evidence. A fully human-written draft can fail, because the test is you, not humanity in general. Density is what gives it away; a single contrast or one stray phrase never sinks a draft.
