# pherkad: handoff / start here

Read this before doing anything in this repo. Every path is absolute. Every section is dated.

## Where things stand (2026-11-12)

- pherkad is the voice checker (voicelint, structlint, replycheck, the corrections ledger, the
  measured profile). The chat Stop hook `replycheck-hook.py` has been live since September.
- New on 2026-11-12, approved by Brian the same day: the outbound gate and the edit capture,
  built to `/Users/moriarty/code/pherkad/docs/outbound-gate.md` after the late landscape scan in
  `/Users/moriarty/code/pherkad/LANDSCAPE.md` (decision: extend pherkad).
- `skills/pherkad/tools/gate.py` (commit 4afda77) checks prose before Gmail, Slack, Drive,
  Docs, docs-connector, Artifact and prose-file writes leave a session; it fails open. It is
  **not live until Brian runs the hook installer** (open item 1).
- `skills/pherkad/tools/capture.py` (9b6204b, 7e9e7a1) learns from Brian's edits and comments:
  chat paste-backs, comments on decks he hands back (Keynote via `iwa.py`), chat comments on
  named slides, hand-saved decks, edited files, Gmail via a nightly session. The first backfill
  ran 2026-11-12: 196 candidates in 74 groups (chat 142, comments 54, slides 0, files 0,
  Gmail 0) from 225 captured comments and 70 chat paste-backs, all pending Brian's accept.
- `skills/pherkad/tools/deckcheck.py` runs at the end of 22 deck builders (FA550 9a77219,
  hosl-submissions 54f5a87, aisafety_pipeline c9993eb) and snapshots each build.
- The daily report shows the candidates and ledger records in section 1 and the counts in
  section 5 (`/Users/moriarty/code/overnight` a95f5b7). The 11 pending literal ledger records
  were trialled on the saga corpus (session-hygiene bed07a3).
- Suites: sixteen, all green on Python 3.14 and the 3.8 floor (`tests/run-all.sh`).

## References

- `/Users/moriarty/code/pherkad/docs/outbound-gate.md`: the design, with Brian's decisions at the end.
- `/Users/moriarty/code/pherkad/LANDSCAPE.md`: comparables and the extend decision.
- `/Users/moriarty/Documents/voice-profile/gate.json`: the live config (paths, server ids, private markers).
- `/Users/moriarty/Documents/voice-profile/gate/`: log, candidates, comments, snapshots, private ledger; ignored by git.
- `/Users/moriarty/Documents/voice-profile/install/`: the launchd plist, the hook installer, the nightly Google task prompt.
- `/Users/moriarty/Documents/voice-profile/survey-2026-11-12/`: the surveys behind the matcher (scripts, counts, copied comments).
- `/Users/moriarty/code/overnight/bin/daily`: the daily page; sections 1 and 5 read `capture.py report --json`.

## Decisions already made (do not relitigate without Brian)

- 2026-11-12: the gate fails open, with a visible message, a log line and a section 5 count.
- 2026-11-12: the gate folder lives in voice-profile and is ignored by git; Heron and FAccT text never leaves the Mac.
- 2026-11-12: Google (sent Gmail, live Slides comments) is read by a nightly scheduled session through its transcript; no credential.
- 2026-11-12: the Write/Edit path rule as written in the design.
- 2026-11-12: Brian's own edits and comments are the main input; Gmail is a minor source (most mail goes through stevens.edu, outside every connector).
- Candidates stage in the gate folder until Brian accepts a group; nothing is promoted without his say-so.

## Open, to pick up here

1. Done 2026-11-13: hooks, the 03:30 launchd job and the 03:12 Google task are installed. Real calls are in the gate log: two Edit passes at 13:36 and a Write blocked at 16:40 for `honest-framing` (100 ms, no file written). The Google task's prompt lost its marker line when created; capture now matches its opening sentence too (7eedc81). Install commands, for a reinstall:
   - `/usr/bin/python3 /Users/moriarty/Documents/voice-profile/install/install-gate-hooks.py`
   - `cp /Users/moriarty/Documents/voice-profile/install/com.moriarty.pherkad.capture.plist /Users/moriarty/Library/LaunchAgents/` then `launchctl bootstrap gui/501 /Users/moriarty/Library/LaunchAgents/com.moriarty.pherkad.capture.plist`
   - Create the 03:00 scheduled desktop task from `/Users/moriarty/Documents/voice-profile/install/google-capture-task.md`.
2. After the first night: check section 5 for "failed" (macOS privacy can block a launchd job from Downloads, Desktop and Documents; the comments source then shows failed, and `/usr/bin/python3` needs Full Disk Access).
3. Brian reviews the 74 candidate groups on the daily page and accepts or rejects them; accepted phrases are trialled automatically.
4. The Google session's result format is parsed by guesswork until it first runs; read its transcript and adjust `_sent_bodies` and `google_comments` in capture.py.
5. Follow-up, not built: a model-based check on outbound sends for the judgment-kind corrections (design, "Later, not now").

## Working mirror

None. pherkad has a GitHub remote; Brian pushes.
