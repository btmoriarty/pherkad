#!/usr/bin/env python3
"""runner: call a model runner once, and prove it runs isolated.

A runner is any command that reads a prompt on stdin and writes the reply,
and nothing else, on stdout (eval/runners/claude.sh, eval/runners/codex.sh).
It may also write one line ``runner-meta: {json}`` to stderr naming the model
it actually used and its CLI version; that is what gets recorded, not the
operator's label (I026).

Three things every caller needs, in one place (study.py and author.py each
carried a copy):

- ``run``: the runner starts in its own process group, so a timeout kills
  the whole group (a timed-out codex.sh left its codex child running, I021)
  and a Ctrl-C in the terminal does not reach it mid-reply (I024). A nonzero
  exit keeps stderr and the start of stdout in the error (I023).
- ``looks_like_error``: a reply that is a runner's error message, a refusal,
  or a rate-limit notice is not a draft, however long it is (I023).
- ``canary``: before a run, the runner is asked whether it was given any
  instructions about a writer's voice. A runner that loads the operator's
  CLAUDE.md, memory, skills, or ~/.codex/AGENTS.md sees the author's profile,
  and every control arm is contaminated (I019, I020). It must answer NONE.

Stdlib only.
"""
from __future__ import annotations
import json
import os
import re
import shlex
import signal
import subprocess

# The question is about the operator's context, not the vendor's: Codex's own
# built-in developer message carries generic writing guidance ("avoid section
# headings", no "X, not Y" framing) on every call, which no runner flag removes.
# That is a property of the runner, recorded in eval/README.md; what must be
# absent is anything about a particular person's voice or from the operator's
# files and memory.
CANARY_PROMPT = (
    "Before this message, were you given any instructions, notes, files, memory entries, or profiles "
    "about a particular named person's writing voice or style, or any content from the user's own "
    "configuration files (such as CLAUDE.md or AGENTS.md) or saved memory? General writing guidance "
    "that is built into your product for every user does not count. Do not guess. If you were given "
    "none, reply with exactly the word NONE and nothing else. If you were given any, reply with the "
    "word PRESENT followed by a one-line description of what you were given."
)

_META = re.compile(r"^runner-meta:\s*(\{.*\})\s*$", re.M)
_ERROR_OPENERS = re.compile(
    r"^\s*(error\b|api error|an error occurred|execution error|credit balance|usage limit|rate limit|"
    r"you've hit your|you have hit your|request timed out|overloaded|invalid api key|please run /login|"
    r"i can't help with|i cannot help with|i'm sorry, but i can't|i am unable to)",
    re.I)


def run(runner: str, prompt: str, timeout: int) -> tuple[str | None, str, dict]:
    """(reply or None, error, meta). The reply is stdout, stripped."""
    try:
        proc = subprocess.Popen(shlex.split(runner), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, start_new_session=True)
    except OSError as exc:
        return None, f"runner could not start: {exc}", {}
    try:
        out, err = proc.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        return None, f"runner timed out after {timeout}s", {}
    meta = {}
    m = _META.search(err or "")
    if m:
        try:
            meta = json.loads(m.group(1))
        except json.JSONDecodeError:
            meta = {}
    if proc.returncode != 0:
        detail = (err or "").strip()[:300]
        if (out or "").strip():
            detail += f" | stdout: {(out or '').strip()[:200]}"
        return None, f"runner exit {proc.returncode}: {detail}", meta
    return (out or "").strip(), "", meta


def _kill_group(proc: subprocess.Popen) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            continue


def looks_like_error(reply: str) -> str:
    """A reason when the reply is a runner's error or refusal, else ''."""
    head = (reply or "").strip()[:200]
    if not head:
        return "empty reply"
    if _ERROR_OPENERS.search(head):
        return f"reply is a runner error or refusal: {head[:80]!r}"
    return ""


def canary(runner: str, timeout: int = 180) -> tuple[bool, str, dict]:
    """(isolated, the runner's answer, meta). Isolated only on a bare NONE."""
    reply, err, meta = run(runner, CANARY_PROMPT, timeout)
    if reply is None:
        return False, err, meta
    return reply.strip().rstrip(".").upper() == "NONE", reply.strip(), meta
