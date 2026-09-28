#!/bin/bash
# A study.py runner: prompt on stdin, the reply on stdout, nothing else; one
# "runner-meta: {json}" line on stderr naming the model actually used.
#
# Isolated from the operator's own Claude Code setup (I019). Until 2026-09-27
# this ran with --setting-sources "" alone, and the canary showed it still
# loaded the operator's memory index, which describes the author's voice rules:
# every control arm saw the profile it was meant to lack. Now:
#   --safe-mode           no CLAUDE.md, memory, skills, plugins, hooks, MCP, agents
#   --strict-mcp-config   no MCP servers at all
#   --setting-sources ""  no user or project settings
#   --tools ""            no tools
#   an empty working folder, so no project CLAUDE.md can be discovered
# study.py run asks the canary question first and refuses to run unless the
# answer is NONE. Set CLAUDE_MODEL to pick the model.
set -u
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT INT TERM
cd "$WORK" || exit 1
OUT=$(claude -p --model "${CLAUDE_MODEL:-claude-sonnet-5}" --safe-mode --strict-mcp-config \
  --setting-sources "" --tools "" --no-session-persistence --output-format json \
  --system-prompt "You are a careful editor. Follow the instructions in the message exactly and reply with the requested output only.")
code=$?
[ $code -ne 0 ] && { printf '%s\n' "$OUT" >&2; exit $code; }
printf '%s' "$OUT" | python3 -c '
import json, subprocess, sys
d = json.load(sys.stdin)
if d.get("is_error"):
    sys.stderr.write("claude: " + str(d.get("result", ""))[:300] + "\n")
    sys.exit(1)
sys.stdout.write(d.get("result", ""))
ver = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()
sys.stderr.write("runner-meta: " + json.dumps({"runner": "claude.sh", "models": sorted((d.get("modelUsage") or {}).keys()),
                                               "cli": ver, "session": d.get("session_id", "")}) + "\n")
'
