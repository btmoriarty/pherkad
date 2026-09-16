#!/bin/bash
# A study.py runner: prompt on stdin, the reply on stdout, nothing else.
# Isolated from the operator's own Claude Code setup: no settings (so no hooks),
# no CLAUDE.md voice rules, no tools, no saved session. Set CLAUDE_MODEL to pick the model.
exec claude -p --model "${CLAUDE_MODEL:-claude-sonnet-5}" --setting-sources "" --tools "" --no-session-persistence \
  --system-prompt "You are a careful editor. Follow the instructions in the message exactly and reply with the requested output only." \
  2>/dev/null
