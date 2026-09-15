# Reply preflight

Roadmap item 2. Most of the AI-speak the author objects to arrives in chat replies from a coding assistant, and until now nothing ran the linter there. This is the check for that gap, in two halves: a cooperative pre-send recipe, and a Claude Code Stop hook that enforces it after the fact.

## The tool

```
python3 /Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/replycheck.py -
```

reads a drafted reply on stdin (or a file path), runs voicelint under the `assistant-chat` surface and structlint as an advisory, and prints one line per finding plus a verdict:

```
3:1 [error] honest-framing: 'the honest X' performs candour instead of exercising it; cut it and say the thing  ->  'The honest answer'
3:51 [error] banned.markdown-link: canned phrase: 'no markdown links in chat; print the full absolute path'  ->  '[the diff](docs/x.md)'
1 [advisory] structure.staccato: 3 short sentences in a row; merge them  ->  'Done. Tests pass. Committed.'
replycheck: FIX (2 error(s), 0 warning(s), 1 structural advisory; surface assistant-chat)
```

`PASS` exits 0, `FIX` exits 1, a check that could not run exits 2. `--strict` makes warnings fail; `--json` gives the same as a document; `--no-structure` skips structlint.

## The surface

`tools/surfaces/assistant-chat.json` is an overlay on the shipped rule set, so everything voicelint already bans still applies (the honest-X error, dashes, the phrase bans, filler, the watch words). On top, the families the author has flagged in chat specifically:

| Rule id | What it catches |
|---|---|
| `banned.pointer-*` | the demonstrative pointer: `that is the part that`, `that's the thing that`, `that is the detail that` |
| `banned.worth-noting`, `banned.worth-saying` | announcing instead of delivering |
| `banned.question-praise-*` | `great question`, `good question`, `fair question` |
| `banned.markdown-link` | any `[text](target)`; chat prints full absolute paths |
| `banned.tilde-path` | `~/...`; full absolute paths, never a tilde |
| `banned.section-sign` | the symbol; write `section 5` |
| `soft.plainly-tag` | `to put it plainly`, `state it plainly` |
| `soft.the-one-that-matters` | the coy withhold |

A rule that only matters in chat goes here, never into the shipped defaults, so downstream corpora do not inherit it. Code spans and fenced blocks are masked, so a command, a path in backticks, or a quoted rule stays out of the check.

## The recipe (pre-send, cooperative)

For any reply longer than a line or two:

1. Write the reply to a file in the scratchpad.
2. Run `replycheck.py` on it.
3. While it says `FIX`, revise the file and run it again, at most three times.
4. Send the exact text of the buffer that passed.
5. A check that failed to run (exit 2) is not a pass. Say so, or fix the cause, rather than sending unchecked.
6. Keep the check output out of the reply.

The one habit the check will keep catching: quoting a banned phrase as an example. Put it in backticks, which the linter masks; plain quotation marks are prose and fire. Two of eight long replies from the session that built this tool failed on that alone.

## The Stop hook (post-send, enforced)

`tools/replycheck-hook.py` is a Claude Code `Stop` hook. When a reply ends, Claude Code hands the hook the transcript path; the hook takes the assistant text since the last human message, runs the same check, and on an error-level finding exits 2 with the findings on stderr, which makes the assistant continue and send a corrected follow-up. The reply has already been displayed by then, so this is enforcement rather than interception; the recipe above is the pre-send half.

Repair is bounded: Claude Code marks the continuation with `stop_hook_active`, and the hook lets that run through, so a reply gets exactly one enforced revision and cannot loop. Warnings never block unless `REPLYCHECK_STRICT=1`; structural findings never block from the hook. A hook that cannot read its input exits 0 with a note, because a broken hook must not wedge a session.

Install in the user settings (`/Users/moriarty/.claude/settings.json`), beside the existing hooks:

```json
"Stop": [
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/replycheck-hook.py"
      }
    ]
  }
]
```

`REPLYCHECK_SURFACE` selects another surface.

## What this does not do

It does not run the judgment layer. The seven-dimension review is too slow and too variable to run before every short answer; it stays for drafts the author asks to have checked. It does not rewrite anything. And it cannot catch what has no string to match: an answer that is shaped like a listicle, a paragraph that announces its structure, a hedge stack. Those stay with the assistant's own reading of `voice-rules.md`.
