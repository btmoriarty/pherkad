# Outbound gate and edit capture: design

Drafted 2026-11-12 after the scan in `/Users/moriarty/code/pherkad/LANDSCAPE.md` (decision:
extend pherkad, per component). Nothing below is built until Brian approves it. The open
decisions are at the end.

## The problem

Only chat replies are checked today, by the Stop hook `replycheck-hook.py`. Email drafts, Slack
messages, Google Docs, published artifacts, prose files and decks leave a session with no check,
because the instruction to run a voice pass lives in CLAUDE.md and sessions skip it. The
corrections pipeline (`corrections.py add`, `mine`, `trial`, `promote`) works but runs only by
hand: 20 corrections since 2026-09-27, 19 pending, 1 promoted, and nothing asks Brian to approve.

## What gets built

| Part | New code | Where it runs |
|---|---|---|
| 1. Outbound gate | `skills/pherkad/tools/gate.py` (PreToolUse and PostToolUse hook) | Every session, on the tools listed below |
| 2. Edit capture | `skills/pherkad/tools/capture.py` plus a launchd job | 03:30 nightly, no model call |
| 3. Approvals | a gatherer in `/Users/moriarty/code/overnight/bin/daily` | Section 1 of the 04:30 build |
| 4. Counts | the same gatherer | Section 5 of the 04:30 build |
| 5. Deck check | `skills/pherkad/tools/deckcheck.py`, called by each builder | At the end of every deck build, and in the daily sweep |

Everything new in pherkad stays stdlib-only and carries no personal path. Brian's paths, server
ids and private-recipient lists live in one config file outside the public repo,
`/Users/moriarty/Documents/voice-profile/gate.json`, beside the existing `surfaces.json`, and the
hook command in `settings.json` passes it with `--config`.

## 1. The outbound gate

### Tools gated, and the text each one carries

| Tool | Text checked | Surface |
|---|---|---|
| Gmail `create_draft`, `update_draft`, `send_message`, `reply`, `forward` | `subject`, then `body`, or the text of `htmlBody` when there is no `body` | `email` |
| Slack `slack_send_message`, `slack_send_message_draft`, `slack_schedule_message` | `message` | `email` (a message to a person) |
| Slack `slack_create_canvas`, `slack_update_canvas` | `title`, `content`, each `sections[].content` | `post` |
| Drive `create_file`, `update_file` | `textContent`, or the decoded `base64Content` when the MIME type is text, Markdown or HTML | `post` |
| Google Docs `update_doc` | each `insertText.text` and `replaceAllText.replaceText` | `post` |
| Claude docs connector `create`, `update`, `batch` | every string under the payload keys that hold body text | `post` |
| `Artifact` with action publish | the published file, read from `file_path`; HTML reduced to its text | `post` |
| `Write`, `Edit`, `MultiEdit` on a gated path (rule below) | the lines this call adds, never the whole file | by path, default `post` |

Matching is by tool-name suffix, so a reconnected connector with a new server id is still
caught. Generic names (`create`, `update`, `batch`) are gated only for the server ids listed in
`gate.json`; on any other server they pass untouched. One matcher covers all of it:

```
^(Write|Edit|MultiEdit|Artifact|mcp__.+__(create_draft|update_draft|send_message|reply|forward|slack_send_message|slack_send_message_draft|slack_schedule_message|slack_create_canvas|slack_update_canvas|create_file|update_file|update_doc|create|update|batch))$
```

### The path rule for Write and Edit

A file is gated when all three hold:

1. Its extension is `.md`, `.txt`, `.html`, `.htm` or `.eml`.
2. It is under `/Users/moriarty/Documents/`, or it is a `README.md` anywhere, or its path inside
   a repository under `/Users/moriarty/code/` has a folder named `deliverables`, `drafts`,
   `outbox`, `submissions`, `proposals`, `talk-materials`, `lectures`, `outreach-materials` or
   `docs`.
3. It is not on the exclude list: anything under a `.claude` folder, the scratchpad and `/tmp`,
   `CLAUDE.md`, `CLAUDE.local.md`, `MEMORY.md`, `HANDOFF.md`, `CHANGELOG.md`, test fixtures,
   pherkad's own rule files (they quote the banned phrases), and files that hold Brian's own
   words verbatim: `/Users/moriarty/Documents/voice-profile/samples/`, the saga's
   `generated/CAPTURED.md`, and any `captures/` or `transcripts/` folder.

Saga canon (`/Users/moriarty/el_loco_lobo/canon/` and `deliverables/`) is routed to the saga's
own overlay, `/Users/moriarty/el_loco_lobo/tools/voice_config.json`, so the fiction is checked by
its own rules and never by Brian's personal profile. Folder lists live in `gate.json`, so adding
a folder is a config change. A project folder cannot remove itself from the gate.

Only added lines are checked. For Edit that is `new_string` minus the lines already in
`old_string`; for Write over an existing file it is the lines not in the file on disk. A session
is never blocked for text Brian wrote earlier.

### What a block looks like

On an error-level finding the hook prints a PreToolUse deny:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
  "permissionDecisionReason": "voice gate (email): 2 errors. Revise and call again:\n  3:14 banned.honest_framing: 'the honest answer'\n  ..."}}
```

The assistant sees the findings, revises, and calls the tool again. Warnings never block; they
are logged. Structural findings and length never block, as in replycheck.

The loop is bounded. If the same target (thread, channel, document, file) is denied twice within
fifteen minutes, the third call returns `permissionDecision: "ask"` with the findings, so Brian
decides in the permission dialog instead of the assistant rewriting a false positive forever. An
occurrence Brian accepts can be recorded with the existing `pherkad.py decide`.

Headless runs (`claude -p`, whose turn origin is `sdk`) are not gated on Write and Edit, for the
reason replycheck skips them: their files feed programs. Sends are gated in every run.

### Speed

One Python start, one config load, one voicelint pass over a short text. The target is under
300 ms per gated call, and under 20 ms for an ungated Write (extension and path are checked
before anything is imported). The test suite measures both.

### When the gate itself fails

A hook that cannot read its config, crashes, or times out has two possible behaviours, and this
is Brian's decision (question 1 below):

- **Fail open, loudly (recommended).** The call goes through. The hook prints a `systemMessage`
  that Brian sees ("voice gate did not run on this email: <reason>; the text is unchecked"),
  writes the failure to the log, and the daily page counts it in section 5. Work never stops for
  a broken hook, and a broken hook never hides.
- **Fail closed.** The call is denied with the reason. Nothing unchecked leaves, but one bad
  config edit stops every email, Slack message and prose write in every session until it is
  fixed.

### The draft log

Every gated call appends one JSON line: time, session id, tool, surface, target (thread id,
channel, document id, path), recipients, the checked text, verdict, findings, and the hook's run
time. A matching PostToolUse hook adds what the tool returned (the draft id and thread id for
Gmail, the message timestamp for Slack) to the same entry, keyed by `tool_use_id`, so the nightly
job can find what was eventually sent.

The log holds draft text, including mail to Heron fellows and any FAccT review text, so it must
never leave the Mac (question 2 below).

## 2. Edit capture, nightly

`capture.py` runs at 03:30 from a launchd job, with no model call. For each logged entry not yet
paired and newer than 14 days:

- **Gmail drafts.** It reads Brian's sent mail in the draft's thread and pairs the logged draft
  with the message he sent (quoted history stripped by the code `samples.py` already uses).
- **Files.** If the file's current text differs from the last logged write and no later logged
  write explains it, the difference is Brian's edit (or a script's), and the last logged text is
  paired with the current one.
- **Sent directly by the agent** (`send_message`, `reply`, `forward`, `slack_send_message`).
  Nothing was edited, so nothing is mined; the entry is counted as sent as-is.
- **Slack drafts, canvases and Google Docs** are not paired in this version. Reading them
  headlessly needs a Slack or Google token of its own; that is a follow-up.

Each pair gets one of three labels, borrowed from the email assistants in the scan: sent as-is,
edited, or rewritten (sentence overlap below 0.6, which yields nothing to learn). Edited pairs go
through `corrections.py mine` into the ledger, then `corrections.py trial` on the saga corpus,
so every record reaches the daily page with its count. The first run also trials the 18 pending
records that have never been trialled. The character edit distance per pair, the measure PRELUDE
uses, is stored for section 5.

Records drawn from a private source (a recipient or path matching the private list in
`gate.json`: Heron recipients, FAccT review folders) go to a local ledger,
`corrections.private.jsonl`, never to the session-hygiene ledger, which is pushed to GitHub.

### Reading sent Gmail headlessly

The Gmail connector exists only inside a Claude session, so a launchd job cannot use it.
A scheduled desktop task could, but its model would retype each sent message into a file, and a
model retyping text is exactly what corrupts a word-level diff. Two headless routes work:

- **IMAP with a Gmail app password (recommended).** Python's `imaplib` reads `[Gmail]/Sent Mail`;
  Gmail's `X-GM-THRID` extension gives the same thread id the connector returns, so the pairing
  is exact. Brian creates an app password in his Google account and stores it in the Keychain
  with one `security add-generic-password` command; the job reads it from there and no session
  ever sees it. It needs 2-step verification on the account, and Google Workspace accounts can
  have app passwords disabled by the admin.
- **The Gmail API with a read-only OAuth token.** Brian creates an OAuth client in Google Cloud
  and authorises `gmail.readonly` once in a browser. It is more setup, and it is the route if app
  passwords are off for the account.

Which account the connector drafts from decides which route (question 3).

## 3. Approvals in section 1

A new gatherer reads both ledgers and lists each pending record under "Voice rules to approve":
the before and after, the source, the kind, the trial count (hits per 1,000 words on the saga
corpus, and whether its fires and clean examples hold), and the exact command:

```
python3 /Users/moriarty/code/pherkad/skills/pherkad/tools/corrections.py promote --ledger /Users/moriarty/code/pherkad/corrections.jsonl c-20261111-003 --overlay /Users/moriarty/code/pherkad/skills/pherkad/tools/voice_config.json --prose /Users/moriarty/code/pherkad/voice-rules.md
```

beside the retire command for the same id. Judgment-kind records get no promote command, because
promote writes prose only for them; they are listed as "prose only or retire". A promotion into
the shipped base is a pherkad release (`pherkad.py manifest --write`, the corpus count, the
CHANGELOG), so when anything was promoted the day before, section 1 also lists the release
commands once.

The gate reads `voice_config.json` on every call, so a promoted rule is enforced from the next
gated call with no restart.

Private-ledger records appear on the local page only. The 05:00 email carries section 1, so it
drops them, along with the before and after text of any record whose source matches the private
list.

## 4. Counts in section 5

One table per day for the last seven days: texts gated, passed, blocked, escalated to Brian,
gate failures, then corrections captured, trialled, promoted and retired, and the mean edit
distance between draft and sent text per surface. The edit distance is the number that says
whether the gate is working: if it does not fall over a month, the gate is catching the wrong
things.

## 5. The deck check

`deckcheck.py <deck>` reads a `.pptx` as the zip it is (slide text from `ppt/slides/*.xml`,
speaker notes from `ppt/notesSlides/*.xml`) or an HTML deck (text per slide section), and runs
pherkad with `surfaces/slides.json`. It exits 1 on an error, prints findings by slide number, and
logs to the draft log so decks count in section 5. The daily build sweeps every `.pptx` and deck
HTML under the two trees changed in the last 24 hours and lists errors in section 1.

The builders to wire, after Brian's go:

| Builder | Format | Repository |
|---|---|---|
| `/Users/moriarty/code/hosl-research/data-analysis-visualization-course/lectures/week-NN-*/build-deck.js`, 15 builders from one skeleton | pptx (pptxgenjs) | FA550 course |
| `.../data-analysis-visualization-course/lectures/week-04-critique-redesign/a1-debrief/build-deck.js` | pptx | FA550 course |
| `.../data-analysis-visualization-course/design/build-deck-template.js`, so new weeks inherit the call | pptx | FA550 course |
| `.../data-analysis-visualization-course/tools/make-recording-pptx.py` (replaces notes) | pptx | FA550 course |
| `/Users/moriarty/code/hosl-research/hosl-submissions/srecon-emea-2026/talk-materials/build_deck.py` and `build_hcb_deck.py` | html | hosl-submissions |
| `.../srecon-emea-2026/talk-materials/build_pptx.py` (slides are images; the notes from `script.md` are the text) | pptx | hosl-submissions |
| `.../srecon-emea-2026/talk-materials/build_presenter_view.py` | html | hosl-submissions |
| `/Users/moriarty/code/aisafety_pipeline/outreach-materials/builder/deck.js` and `deck_deepdive.js` | pptx | aisafety_pipeline |

The JavaScript builders call it with `execFileSync` after writing the file and exit non-zero on
failure; the Python builders call it with `subprocess.run(check=True)`. The FA550 builders write
one deck per theme with the same text, so each checks one. The SRECon study aids (cards, drills,
schedules) are study material, not decks, and are not wired. No reveal.js deck exists.

## Later, not now

Eight of the twenty corrections are judgment kind (abstract-subject AI speak, register recasts)
and no linter can catch them. The follow-up is a model-based check on outbound sends only, run
by the gate on the `email` and `post` surfaces after the mechanical pass, with the pending
judgment corrections as its few-shot examples, the way CIPHER retrieves past edits. It needs its
own scan and its own cost limit, since it puts a model call on every send.

## Tests

`test_gate.py`: each tool's text extraction from a recorded payload; the path rule (gated,
excluded, saga-routed); added-lines-only for Edit and Write; deny, pass and escalate-on-third;
fail-open and fail-closed on a broken config; the sdk skip for Write; the 300 ms and 20 ms
budgets. `test_capture.py`: pairing from a fixture log and a fixture mbox, the three labels, the
private-ledger split. `test_deckcheck.py`: a two-slide pptx and an HTML deck built in the test.
All join `tests/run-all.sh`.

## Decisions for Brian

1. Fail mode when the gate itself breaks: fail open with a visible warning and a logged count
   (recommended), or fail closed.
2. Where the draft log lives. Recommended: `/Users/moriarty/Documents/voice-profile/gate/`,
   ignored by git so it never reaches the voice-profile remote, with the private ledger beside it.
   The cost is that it sits on one disk; the durable output is the ledger, and an entry only
   matters until its pair is mined.
3. Which Gmail account the connector drafts from, and whether you will create an app password
   for it (IMAP) or prefer the OAuth route.
4. The path rule for Write and Edit as written above, or a narrower opt-in list of folders.
