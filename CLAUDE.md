# Pherkad

The voice tools live in `skills/pherkad/tools/`. Run the suites with `python3 <abs path>/test_voicelint.py`, `test_structlint.py`, `test_replycheck.py`, and `eval/test_study.py`; all four are unittest modules and pytest collects them too.

## Reply preflight

Before sending any reply longer than a line or two, preflight it:

1. Write the reply to a file in the scratchpad.
2. Run `python3 /Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/replycheck.py <that file>`.
3. While it says `FIX`, revise and rerun, at most three times.
4. Send the exact text that passed. Keep the check output out of the reply.
5. If the check could not run (exit 2), that is not a pass; fix the cause or say the reply is unchecked.

Quote any banned phrase you need to mention in backticks; plain quotation marks are prose and fire. Full recipe and the Stop hook: `docs/reply-preflight.md`.

## Rule changes

Every change to `voice_config.json` is counted against the saga corpus before it ships (`/Users/moriarty/el_loco_lobo`, the shareable tree, via the saga overlay), and the count goes in the CHANGELOG. The ban list does not grow for migrating habits; those go to the judgment layer or corpus monitoring. Chat-only rules go in `tools/surfaces/assistant-chat.json`, never the shipped defaults.
