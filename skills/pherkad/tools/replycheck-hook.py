#!/usr/bin/env python3
"""Claude Code Stop hook: run replycheck over the reply that was just finished.

The cooperative recipe (draft, check, send the checked buffer) depends on the
assistant remembering to run it. This hook does not: Claude Code fires it when
a reply ends, hands it the transcript path on stdin, and an exit 2 with the
findings on stderr makes the assistant continue and revise. The reply has
already been displayed by then, so this is enforcement after the fact, not
interception; the recipe is the pre-send half and this is the backstop.

Bounded repair: Claude Code sets ``stop_hook_active`` when the assistant is
already continuing because of a stop hook. That run never blocks, so a reply
gets exactly one enforced revision and can never loop; but the revision is
still checked, and a revision that still fails is reported to the person as a
``systemMessage`` rather than passed in silence.

Headless runs are skipped. A `claude -p` call from a script inherits the user
settings and so this hook; blocking it makes the model rewrite output a program
will parse (2026-09-17 to 09-20 it rewrote verbatim evidence quotes in 90
course-kg extractions). Such a turn is opened by a user row whose
``turnOrigin`` is ``sdk``; a person's turn in the desktop app or terminal is
``human``, and task notifications and peer messages are still checked.

Never a silent pass. A check that cannot run (a sibling module that will not
import, a broken overlay, an unknown surface, an unreadable transcript, a
crash) blocks once with ``voice check did not run: <reason>``, so the
assistant tells the person the reply is unchecked; ``stop_hook_active`` keeps
that to once per turn. A ``surfaces.json`` in the session's working folder is
not read, so no project folder can redirect or disable the check.

Errors block. Warnings block too under REPLYCHECK_STRICT=1. Structural
findings never block from here.

Install (user settings, ~/.claude/settings.json):

    "Stop": [{"matcher": "", "hooks": [{"type": "command",
      "command": "/Users/moriarty/Documents/kochab/pherkad/skills/pherkad/tools/replycheck-hook.py"}]}]

REPLYCHECK_SURFACE selects the surface (default assistant-chat).
"""
from __future__ import annotations
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def last_reply_text(transcript_path: str) -> str:
    """The text blocks of the assistant turn that just ended: every assistant
    text block after the last real user message (a user entry whose content is
    not only tool results), in order."""
    return last_turn(transcript_path)[0]


def last_turn(transcript_path: str) -> tuple[str, str | None]:
    """The reply text of the turn that just ended, and the ``turnOrigin`` of
    the user message that opened it (``human``, ``sdk``, ... or None when the
    transcript does not record one). Meta rows (a skill body, an image note)
    sit inside a turn and are not its boundary."""
    rows = []
    with open(transcript_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    texts: list[str] = []
    origin = None
    for d in reversed(rows):
        t = d.get("type")
        if t not in ("user", "assistant") or d.get("isSidechain"):
            continue
        content = (d.get("message") or {}).get("content")
        if t == "user":
            if d.get("isMeta"):
                continue  # injected context inside the turn, not the human
            if isinstance(content, list) and content and all(
                    isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                continue  # a tool result, not the human
            origin = d.get("turnOrigin")
            break
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                    texts.append(b["text"])
    texts.reverse()
    return "\n\n".join(texts), origin


def _did_not_run(reason: str, revising: bool) -> int:
    msg = f"voice check did not run: {reason}"
    if revising:
        print(json.dumps({"systemMessage": "replycheck: " + msg}))
        return 0
    sys.stderr.write("replycheck: " + msg + ". Tell the person this reply is unchecked, "
                     "in one short line, and do not repeat the reply.\n")
    return 2


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        sys.stderr.write("replycheck-hook: no hook payload on stdin; not checked\n")
        return 0
    revising = bool(payload.get("stop_hook_active")) if isinstance(payload, dict) else False
    try:
        return check(payload, revising)
    except Exception as exc:  # a hook bug is reported once, never a silent pass
        return _did_not_run(f"unexpected error ({type(exc).__name__}: {exc})", revising)


def check(payload: dict, revising: bool) -> int:
    try:
        import replycheck
    except Exception as exc:  # a missing or broken sibling must not pass silently
        return _did_not_run(f"cannot load replycheck ({exc})", revising)

    path = payload.get("transcript_path")
    tail = (payload.get("last_assistant_message") or "").strip()
    text, origin = "", None
    if path and os.path.exists(path):
        try:
            text, origin = last_turn(path)
        except OSError as exc:
            if not tail:
                return _did_not_run(f"cannot read the transcript ({exc})", revising)
    elif not tail:
        return _did_not_run("no transcript and no last message in the hook payload", revising)
    if origin == "sdk":
        return 0  # a headless `claude -p` run: its output feeds a program, not a reader
    if tail and tail not in text:
        text = (text + "\n\n" + tail) if text.strip() else tail  # not yet written to the transcript
    if not text.strip():
        return 0

    surface = os.environ.get("REPLYCHECK_SURFACE", replycheck.DEFAULT_SURFACE)
    strict = os.environ.get("REPLYCHECK_STRICT") == "1"
    try:
        result = replycheck.check_reply(text, surface, structure=False, cwd=False)
    except SystemExit:
        return _did_not_run(f"surface or config error on '{surface}'", revising)
    if replycheck.verdict(result, strict) == "PASS":
        return 0
    lines = [f"  {f['line']}:{f['col']} {f['rule_id']}: {f['message']}  ->  {f['match']!r}"
             for f in result["findings"] if f["severity"] == "error" or strict]
    if revising:
        # the one enforced revision has happened; report, never loop
        print(json.dumps({"systemMessage": "replycheck: the revised reply still breaks the voice rules:\n"
                                           + "\n".join(lines)}))
        return 0
    sys.stderr.write("replycheck: the reply you just sent breaks the voice rules. "
                     "Revise it once, in a short follow-up, and send only the corrected text:\n")
    sys.stderr.write("\n".join(lines) + "\n")
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # only reachable before the payload is read; cannot know the turn, so never block
        sys.stderr.write(f"replycheck: voice check did not run: unexpected error ({exc})\n")
        sys.exit(1)
