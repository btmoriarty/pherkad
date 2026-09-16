# Pherkad

The voice tools live in `skills/pherkad/tools/`. Run the suites with `python3 <abs path>/test_voicelint.py`, `test_mdmask.py`, `test_structlint.py`, `test_pherkad.py`, `test_replycheck.py`, `test_corpusscan.py`, `test_corrections.py`, and `eval/test_study.py`; all eight are unittest modules and pytest collects them too.

## Reply preflight

Before sending any reply longer than a line or two, preflight it:

1. Write the reply to a file in the scratchpad.
2. Run `python3 /Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/replycheck.py <that file>`.
3. While it says `FIX`, revise and rerun, at most three times.
4. Send the exact text that passed. Keep the check output out of the reply.
5. If the check could not run (exit 2), that is not a pass; fix the cause or say the reply is unchecked.

Quote any banned phrase you need to mention in backticks; plain quotation marks are prose and fire. Full recipe and the Stop hook: `docs/reply-preflight.md`.

## Rule changes

Every change to `voice_config.json` is counted against the saga corpus before it ships, and the count goes in the CHANGELOG. The count is one command:

```
python3 /Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/corpusscan.py diff /Users/moriarty/el_loco_lobo/canon /Users/moriarty/el_loco_lobo/deliverables --config /Users/moriarty/el_loco_lobo/tools/voice_config.json --exclude '[0-9][0-9]-*.md' --ext .md --old <previous voice_config.json> --new skills/pherkad/tools/voice_config.json
```

with `<previous voice_config.json>` from `git show <last release>:skills/pherkad/tools/voice_config.json`. A candidate rule is tried before it is added with `corpusscan.py scan ... --candidate "field:pattern" --contexts 8`. The numbers are raw hits; read the contexts before calling one a violation. To turn them into precision, `corpusscan.py review ... --out labels.jsonl` exports a sample for Brian to label and `score-review` scores it; only he labels. The ban list does not grow for migrating habits; those go to the judgment layer or corpus monitoring. Chat-only rules go in `tools/surfaces/assistant-chat.json`, never the shipped defaults.

## Corrections

When Brian corrects a phrase (`X -> Y`, in an edit, an email, or a review), it goes into the ledger, never by hand into `voice-rules.md`:

```
python3 /Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/corrections.py add --ledger /Users/moriarty/Documents/kochab/pherkad/corrections.jsonl --before "X" --after "Y" --context "<the sentence>" --source "<where>" --surface <email|post|paper|chat> --rationale "<why>"
```

Then `trial` it on the saga (`... trial --ledger <ledger> <id> /Users/moriarty/el_loco_lobo/canon /Users/moriarty/el_loco_lobo/deliverables --config /Users/moriarty/el_loco_lobo/tools/voice_config.json --exclude '[0-9][0-9]-*.md'`), read the contexts, and only on his say-so `promote --overlay skills/pherkad/tools/voice_config.json --prose voice-rules.md`, which writes the rule with its fixtures and generates the mined-corrections line. A promotion into the shipped base is a release: `pherkad.py manifest --write`, the corpus count, the CHANGELOG. A factual correction never becomes a rule; a recast of meaning is judgment-only and gets prose only.
