#!/usr/bin/env python3
"""Claude Code Stop hook: run replycheck over the reply that was just finished.

The cooperative recipe (draft, check, send the checked buffer) depends on the
assistant remembering to run it. This hook does not: Claude Code fires it when
a reply ends, hands it the transcript path on stdin, and an exit 2 with the
findings on stderr makes the assistant continue and revise. The reply has
already been displayed by then, so this is enforcement after the fact, not
interception; the recipe is the pre-send half and this is the backstop.

Bounded repair: Claude Code sets ``stop_hook_active`` when the assistant is
already continuing because of a stop hook. That run is allowed through, so a
reply gets exactly one enforced revision and can never loop.

Errors block. Warnings are printed with the block when there is one and are
otherwise silent, unless REPLYCHECK_STRICT=1, in which case they block too.
Structural findings never block from here. A hook that cannot read the
transcript exits 0 with a note on stderr: a broken hook must not wedge the
session, and the recipe still says a check that did not run is not a pass.

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

import replycheck  # noqa: E402


def last_reply_text(transcript_path: str) -> str:
    """The text blocks of the assistant turn that just ended: every assistant
    text block after the last real user message (a user entry whose content is
    not only tool results), in order."""
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
    for d in reversed(rows):
        t = d.get("type")
        if t not in ("user", "assistant") or d.get("isSidechain"):
            continue
        content = (d.get("message") or {}).get("content")
        if t == "user":
            if isinstance(content, list) and content and all(
                    isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                continue  # a tool result, not the human
            break
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                    texts.append(b["text"])
    texts.reverse()
    return "\n\n".join(texts)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        sys.stderr.write("replycheck-hook: no hook payload on stdin; not checked\n")
        return 0
    if payload.get("stop_hook_active"):
        return 0  # the one enforced revision has happened; do not loop
    path = payload.get("transcript_path")
    if not path or not os.path.exists(path):
        sys.stderr.write("replycheck-hook: no transcript; not checked\n")
        return 0
    try:
        text = last_reply_text(path)
    except OSError as exc:
        sys.stderr.write(f"replycheck-hook: cannot read transcript ({exc}); not checked\n")
        return 0
    if not text.strip():
        return 0

    surface = os.environ.get("REPLYCHECK_SURFACE", replycheck.DEFAULT_SURFACE)
    strict = os.environ.get("REPLYCHECK_STRICT") == "1"
    try:
        result = replycheck.check_reply(text, surface, structure=False)
    except SystemExit:
        sys.stderr.write("replycheck-hook: surface or config error; not checked\n")
        return 0
    if replycheck.verdict(result, strict) == "PASS":
        return 0
    sys.stderr.write("replycheck: the reply you just sent breaks the voice rules. "
                     "Revise it once, in a short follow-up, and send only the corrected text:\n")
    for f in result["findings"]:
        if f["severity"] == "error" or strict:
            sys.stderr.write(f"  {f['line']}:{f['col']} {f['rule_id']}: {f['message']}  ->  {f['match']!r}\n")
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never wedge the session on a hook bug
        sys.stderr.write(f"replycheck-hook: unexpected error ({exc}); not checked\n")
        sys.exit(0)
