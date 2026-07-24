# Pherkad Cheat Sheet

One page. Everything Pherkad does and what to say to trigger it. It validates against one voice, yours; it never polices anyone else's text and never returns a score without quoted evidence. Say things in your own words; the phrases below are examples, not commands.

**First run:** ask for a voice check on any draft. With no profile yet, Pherkad interviews you first; bring at least four pieces of writing you consider most you. The profile lives in your folder and never leaves it.

| Mode | Say something like | What you get |
|---|---|---|
| **Build profile** | "build my voice profile" | A short interview over your samples, then `Voice_Profile.md`: your authority, hedging, texture, mechanics, structure, and tone, every marker backed by a quoted sentence of yours |
| **Voice check** | "does this sound like me," "voice check this draft," "tone check" | A fingerprint (the 3 sentences most and least like you), seven dimensions scored with evidence, the full catalog checked, density per 100 words, and a verdict: PASS / REVISE / REWRITE |
| **Targeted rewrites** | arrives with any REVISE or REWRITE verdict | Only the flagged sentences rewritten, each fix explained. Facts, names, numbers, dates, sources, and emphasis must stay as you had them; a rewrite that changes them is wrong, so check that it did not |
| **Correct a flag** | "that one is actually me" | The correction appends to your profile with the sentence as evidence, so a later run applies it instead of repeating the flag |
| **Personal linter config** | "make me a linter config from my profile" | Your dash stance, crutch-word caps, and extra bans as a `voice_config.json` the CLI linter can run in CI |
| **CLI linter** | `python3 tools/voicelint.py draft.md` | The mechanical tells with exact line numbers, no model needed. Use `--json --strict` for CI. Exit 0 means no error-level findings, exit 1 means an error-level finding or a warning under `--strict`, and exit 2 means a usage, IO, or config error |

**About the defaults:** the shipped rules are the author's own, built from tells observed across many AI-assisted documents, and they ship strict. Your register may differ: edit `tools/voice_config.json` to your purpose, or relax single rules in your own config (`tools/examples/relaxed.json` shows the shape) with the override recorded in your profile.

**Your data:** your voice profile is built from your writing and stays in your folder. The repository ships no personal data; its only persona is fictional.

**The one rule:** every verdict carries quoted evidence. A fully human-written draft can fail, because the test is you, not humanity in general. Density is the tell; a single contrast or one stray phrase never sinks a draft.
