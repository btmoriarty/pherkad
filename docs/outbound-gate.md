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
| 2. Edit capture | `skills/pherkad/tools/capture.py` plus a launchd job; four sources: chat transcripts, slides, files, Gmail | 03:30 nightly, no model call |
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

`capture.py` runs at 03:30 from a launchd job, with no model call. It reads four sources, in this
order, because the first two are where Brian's edits actually arrive (revised 2026-11-12 after he
said his inline chat edits and slide changes were not being used at all).

### Source 1: inline edits in chat

`capture.py` reads the Claude Code transcripts of both seats,
`/Users/moriarty/.claude/projects/*/*.jsonl` and `/Users/moriarty/.claude-edu/projects/*/*.jsonl`,
for sessions changed since its last run. Only interactive sessions count (entrypoint
`claude-desktop` or `cli`); headless runs and rows whose turn origin is `sdk` (scheduled tasks,
messages from other sessions) are skipped, and so are compaction summaries.

**How Brian marks his edits.** A survey of the last 60 days (17,487 of his messages in 8,686
interactive sessions, run 2026-11-12) settled the matcher. He does not use brackets,
strikethrough or tracked-change marks. He pastes the draft back with his changes made in place,
under a short lead-in line: "I revised:", "edit:", "small rev:", "minor and partial revisions",
"I want to go back to more like this:", "For slide 2 this is closer but still a little clunky",
"this is the email I sent so voice can learn my small changes". Slide edits come the same way,
often with the deck's own markers kept (`[SLIDE 3: the mirror]`). Instructions of the form
`change "X" to "Y"` or `replace "X" with "Y"` did not appear in his own typed words in the 60
days; the matches were reviews from other tools that he pasted in, which are not his
corrections.

**The matcher.**

1. For each of Brian's messages, split it into sentences and find, for each, the closest
   sentence in the assistant's earlier text in the same session (word overlap, the measure
   `mine_pairs` uses).
2. The message is a paste-back with edits when at least two sentences match at 0.6 or above and
   at least one of them is changed (below 1.0). Its draft is the assistant block most of them
   came from, cut to the span he pasted; its edited side is his matching span, without the
   lead-in.
3. Before the diff, both sides are normalised: curly quotes folded to straight ones, email
   quote marks (`>`) and Markdown bold stripped. Without this, one candidate in eight was a
   quote-style change.
4. The lead-in decides whether it counts. A lead-in naming an edit (revised, rev, edit, version,
   changes, closer, like this, I sent) counts. A lead-in naming someone else's text (feedback,
   comments, review, recommend, "came back with", "what is this") does not. A message with no
   lead-in counts only when the pasted span is not a web page or terminal output, and its
   candidates are marked "no lead-in" on the daily page so Brian can retire a wrong one in one
   step.
5. A `change "X" to "Y"`, `replace "X" with "Y"` or `"X" -> "Y"` line counts when it is in
   Brian's own typed text, outside any pasted block, and X occurs in the assistant's earlier
   text.
6. A message that names a slide is mined with surface `slides`; others with the surface of the
   draft (email when it opens with a greeting, post otherwise). Saga sessions and "Yours: /
   Mine:" exchanges are fiction and go to no personal ledger. Heron sessions and messages naming
   Heron or FAccT go to the private ledger.

**What the last 60 days would have yielded.** 123 messages were paste-backs with edits. With the
normalisation, 80 of them produce candidates, 408 phrase candidates in all. By lead-in:

| Lead-in | Messages with candidates | Candidates | Personal ledger | Private ledger |
|---|---|---|---|---|
| names an edit | 23 | 155 | 131 | 23 (one fiction pair dropped) |
| none | 49 | 236 | 120 | 116 |
| names someone else's text (excluded) | 8 | 17 | 0 | 0 |

A sample of the no-lead-in group was about half real edits (a revised email, his edited talk
abstract) and half pasted pages, terminal output or requests ("simplify and update this"),
which is why those are labelled rather than trusted. So the chat source would have produced
roughly 25 to 50 edited drafts and 150 to 270 candidates over 60 days, against the 20 records
the ledger holds from three months of hand entry. That is two to four candidates a day for the
daily page, so section 1 groups them by message with one retire-all line per message.

### Source 2: slides

Decks are built from source, so Brian's slide changes arrive by one of two routes: he edits a
built .pptx and saves it, or he tells a session in chat and the session ports the change into the
builder. Both are covered.

**(a) Hand-saved decks.** Every builder already calls `deckcheck.py` as its last step (part 5).
That call also writes a snapshot of each slide's text and speaker notes, with the deck's
`cp:revision`, to the gate folder. Nightly, `capture.py` looks at every .pptx under the two trees,
`/Users/moriarty/Downloads` and `/Users/moriarty/Desktop` changed since its last run. A deck is
hand-saved when its revision is above the snapshot's (PowerPoint raises `cp:revision` on every
save; pptxgenjs and python-pptx always write 1). A deck saved under a new name, such as
`Week 6 tonight - 7 Oct.pptx` in Downloads, has no snapshot of its own, so it is matched to the
snapshot whose slide titles it shares at 0.6 or more. Each changed slide is diffed against the
snapshot, text and notes separately, and the pairs go to `corrections.py mine` with surface
`slides`.

**(b) Changes ported from chat.** When Brian pastes a slide back with his edits ("For slide 2
this is closer", "[SLIDE 3: the mirror]"), source 1 catches it, and a message that names a slide
is mined with surface `slides`. The builder commit that follows adds nothing new.

What the last 60 days show (survey of 2026-11-12): 72 .pptx files changed, and every one has
`cp:revision` 1, so none was saved by hand in PowerPoint. Brian's older hand-made decks show the
counter working (`SysCon2026_Moriarty_v3.pptx` is at 3, the HOSL poster at 10). The Downloads
copies that differ from the repository builds (week 5 differs on 18 slides, the SRECon deck on 17)
are builder output from an earlier or different build: both are at revision 1, the SRECon copy
still carries python-pptx's default author, and the week 5 repository copy is four days newer. So route (a) would
have caught no deck in the last 60 days; his edited slide text all came through chat, which is why
source 1 comes first. Route (a) stays because it costs one snapshot per build and it is the only
route that sees an edit made in PowerPoint. The revision check missed one thing: comments, below.

### Source 2, continued: slide comments

Brian said on 2026-11-12 that his slide "edits" are sometimes comments, and that the main ones
are on decks a session built and sent him: he opens the .pptx in Keynote or PowerPoint, comments
on it, and uploads it back into a chat. A comment is not a before-and-after pair, so it cannot
become a lint rule directly. Each one is captured with the slide text it sits on, which is the
deck as the session sent it, and with the same slide in the next version the session built.

**What exists** (surveys of 2026-11-12, every .key and .pptx under the two trees, Downloads,
Desktop and the Cowork session folders).

| Where | Files with comments | Comments | Distinct | Wording | Fact | Design | Content |
|---|---|---|---|---|---|---|---|
| Decks a session sent, commented in Keynote and uploaded back | 10 | 120 | 91 | 29 | 6 | 2 | 54 |
| Google Slides exports in Downloads | 40 | 137 | 43 | 5 | 2 | 2 | 34 |
| Chat messages naming a slide, last 60 days | 69 messages | 69 | 69 | 23 to 32 | | | |

The uploaded decks are the FA550 lectures for weeks 2, 3, 4, 5, 6 and 11 (August 2026 and
2026-11-11), all saved as Keynote files in `/Users/moriarty/Downloads` with names such as
`week-04-critique-redesign-stevens-comments.key`. Week 11's two review rounds were also copied by
a session into `lectures/week-11-capstone-launch/edits/` in the course repository. Every comment
is by Brian. Distinct counts drop the repeats in copied files. The wording comments read like
this: "Don't like word choice", "AI speak", "Cheesy", "Obtuse wording", "No way I would say or do
this", "This sounds like an instruction for me on a slide students are seeing", "The forward
look? I guess you stopped doing voice passes before showing me a draft". Nine of the content
comments are one recurring complaint, a term used before students have been told what it means
("Students will not remember what the five questions are"); that is a candidate for a structural
check later, not a voice rule. The Google Slides exports (2024-01 to 2026-04) are mostly to-do
notes he left himself ("Update"), which is why so few are wording.

**Where the uploads went.** Week 11's decks were attached in a Code-tab chat by path
(`@"/Users/moriarty/Downloads/week-11-capstone-launch-stevens.key"`). The August decks appear in
no Code-tab or Cowork transcript on either seat and in no Cowork `uploads/` folder, so they were
uploaded in claude.ai chats, where the attachment lives on the server only. The Cowork folders
hold one Keynote upload (`AITC_Slides.key`, no comments) and no .pptx, and none of their 1,433
Markdown uploads is a converted deck. Capture therefore does not depend on the upload at all: in
every case Brian saved the commented file on the Mac before uploading it, and capture reads that
file. A deck commented on another device and uploaded straight to claude.ai would be missed;
reaching it would need the claude.ai data export, done by hand, and that export carries a
conversation's text, not reliably the original file.

**Four routes.**

1. *Decks sent for review and uploaded back with comments* (the main route). `capture.py` reads
   commented .key and .pptx files wherever they are saved: Downloads, Desktop, the two trees and
   the Cowork folders. Keynote files are read with a small stdlib reader (Keynote's IWA format is
   snappy-compressed protobuf inside a zip); a comment is message type 3056, its author is
   resolved through a reference, and its slide text comes from the same slide part. The survey
   read all 33 Keynote files with no failure. PowerPoint files are read as in route 2. The before
   text is the commented file's own slide text, since that file is the deck as sent. The after
   text is the same slide, matched by word overlap, in the session's next build: the builder
   snapshot after the comment's date, or the builder's committed output at the next commit. On
   week 11 that pairing works: of 23 commented slides, the rebuild in commit `ace9add` ("deck
   rebuilt from Brian's two review rounds") changed 19 and removed 3.
2. *Comments in .pptx files*, mainly Google Slides exports. `capture.py` reads
   `ppt/comments/comment*.xml` with `ppt/commentAuthors.xml`, and the modern
   `ppt/comments/modernComment_*.xml` with `ppt/authors.xml`, maps each comment to its slide
   through the slide relationships, and keeps only Brian's. The response is the same slide in the
   latest deck of the same family, not merely the next numbered copy, because unresolved
   comments ride forward unchanged: in the SysCon copies only 5 of 40 comment texts sit on a
   slide whose text later changed. The presented deck, `SysCon2026_Moriarty_v3.pptx`, holds the
   answers: "desired end state" is gone, "artifact" is in, "time pressure" stayed.
3. *Comments left live in Google Slides.* The Drive connector's `read_file_content` with
   `includeComments` returns a deck's text with its comment threads inline, but only inside a
   session. Retyping is avoidable here: Claude Code writes every tool result verbatim into the
   session's transcript, so a scheduled desktop session that only calls `list_recent_files` and
   then `read_file_content` on each presentation changed that day leaves the comments verbatim
   in its transcript, and `capture.py` parses them from there without any model output in the
   path. The costs are one small model run a night, a text format the tool's own description says
   will change (so a parse failure shows as "failed" in section 5, never as zero), and one
   dispatch that must finish the whole job. `download_file_content` with a .pptx export would
   reuse route 2's parser, but it returns the deck as base64 into the model's context, which
   does not fit for a full deck. The alternative with no model run is a read-only Google OAuth
   token used by `capture.py` directly (Drive `comments.list` gives author, text, quoted text,
   resolved state and replies); the same token would cover Gmail (question 3).
4. *Comments in chat that name a slide.* A message that names a slide and does not paste text
   back is a comment, no longer dropped. Its before text is that slide in the deck the session
   was working on, taken from the snapshot `deckcheck.py` wrote at the last build before the
   message; its after text is the same slide at the session's next build. The deck is found from
   the session's own Bash calls to a known builder. For messages before snapshots exist, the
   builder's source in git, at the commits either side of the message, gives the slide's string
   literals before and after.

**Sorting.** Each comment is sorted by keywords into wording (term, word, wording, phrase,
language, wordy, obtuse, cheesy, confusing, "sounds like AI", "AI speak", "reads as", "would I
say", a quoted replacement), fact (accuracy, wrong, check, source, data, correct, number, "is
this actually"), design (table, matrix, callout, layout, box, visual, colour, font) or content
(everything else). The hand sort of the 91 uploaded-deck comments above is the test set for the
keyword sort. Only wording comments feed the voice ledger, as judgment records: the comment as
the rationale, the slide text before and after as the example, surface `slides`, kind
`judgment`, so promote writes prose and never a rule. Fact, design and content comments are
counted, not mined. A mis-sorted comment costs one retire on the daily page.

**Where they live.** Every captured comment, of every kind, is copied with its deck path, the
deck's sha256, slide, slide text and response text into `comments.jsonl` in the private gate
folder at capture time, so nothing depends on a file in Downloads staying put after
`mac-cleanup` clears it. Wording records also go to the ledger (private ledger when the deck or
session is private). The first run backfills the 257 comments already found; until then both
surveys' records are kept in the voice-profile repository.

### Sources 3 and 4: files and Gmail

For each gate-log entry not yet paired and newer than 14 days:

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

The Gmail connector exists only inside a Claude session, so a launchd job cannot use it. A
scheduled desktop task that wrote sent messages to a file would have its model retype them, and
a model retyping text is exactly what corrupts a word-level diff. Three routes avoid that:

- **A scheduled session read through its transcript.** The session only calls `search_threads`
  and `get_thread` for the threads in the draft log; the messages land verbatim in its
  transcript as tool results, and `capture.py` parses them from there, the same way as the live
  Slides comments in source 2. No credential is created, at the cost of a small model run a
  night and a result format that can change without notice.

- **IMAP with a Gmail app password (recommended).** Python's `imaplib` reads `[Gmail]/Sent Mail`;
  Gmail's `X-GM-THRID` extension gives the same thread id the connector returns, so the pairing
  is exact. Brian creates an app password in his Google account and stores it in the Keychain
  with one `security add-generic-password` command; the job reads it from there and no session
  ever sees it. It needs 2-step verification on the account, and Google Workspace accounts can
  have app passwords disabled by the admin.
- **The Gmail API with a read-only OAuth token.** Brian creates an OAuth client in Google Cloud
  and authorises `gmail.readonly` once in a browser. It is more setup, and it is the route if app
  passwords are off for the account.

Which account the connector drafts from, and whether Brian would rather create a credential or
run a nightly session, decides the route (question 3). The OAuth token is the one choice that
also covers live Google Slides comments with no model run.

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
distance between draft and sent text per surface. Captured edits are counted by source in four
fixed columns, chat, slides, files and Gmail, each printed as 0 when it yielded nothing, so a
source that has gone quiet or broken shows as a zero rather than a missing row. A source whose
reader failed that night (an unreadable transcript store, an IMAP login refused) shows "failed"
in its cell instead of a number. Slide comments get their own small table, by route (decks uploaded
back, .pptx files, live Google Slides, chat) and by kind (wording, fact, design, content), with the same zero and
"failed" rule; only the wording column feeds the ledger. The edit distance is the number that says
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
budgets. `test_capture.py`: the chat matcher on fixture transcripts built from the survey's shapes (a
paste-back with a lead-in, a paste-back of a slide, a pasted review from another tool that must
not count, a verbatim quote with a question, a curly-quote-only change, an email with quote
marks, a compaction summary); the slide snapshot diff on a deck whose revision went up and on a
renamed copy; Gmail pairing from a fixture log and a fixture mbox; the three labels; the
private-ledger split; and the zero-not-missing source counts. For comments: a Keynote file with
comments (a two-slide deck with two comments, made once in Keynote with neutral text and checked in as
a fixture) read by the IWA reader
with its author and slide text, the after text found in a later build; a legacy and a modern
.pptx comment part built in the test, authors other than Brian dropped, the response taken from
the latest deck of the family, the keyword sort on the survey's real comment texts, a recorded
`read_file_content` result parsed from a fixture transcript, and a chat slide comment paired with
two snapshots. `test_deckcheck.py`: a two-slide pptx and an HTML deck built in the test.
All join `tests/run-all.sh`.

## Decisions for Brian

1. Fail mode when the gate itself breaks: fail open with a visible warning and a logged count
   (recommended), or fail closed.
2. Where the draft log lives. Recommended: `/Users/moriarty/Documents/voice-profile/gate/`,
   ignored by git so it never reaches the voice-profile remote, with the private ledger beside it.
   The cost is that it sits on one disk; the durable output is the ledger, and an entry only
   matters until its pair is mined.
3. Which Gmail account the connector drafts from, and how capture reads Google: an app password
   for IMAP (Gmail only), a read-only OAuth token (Gmail and live Slides comments, no model run),
   or a nightly scheduled session read through its transcript (both, no credential, one small
   model run a night).
4. The path rule for Write and Edit as written above, or a narrower opt-in list of folders.
