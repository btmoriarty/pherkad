#!/bin/bash
# A study.py runner: prompt on stdin, the model's final message on stdout,
# nothing else; one "runner-meta: {json}" line on stderr.
#
# Isolated from the operator's own Codex setup (I020). Until 2026-09-27 this
# ran with the operator's CODEX_HOME, whose AGENTS.md carries the author's
# voice rules, so the flattener saw the profile it was meant to be blind to
# (the canary answered PRESENT). Now each call gets a throwaway CODEX_HOME that
# holds only a link to the existing login (auth.json): no AGENTS.md, no
# config.toml, no memories, no rules, and an empty working folder. study.py run
# asks the canary question first and refuses to run unless the answer is NONE.
#
# Uses the Codex binary bundled with the ChatGPT app; set CODEX_MODEL to pick
# the model and CODEX_BIN to use another binary.
set -u
CODEX="${CODEX_BIN:-/Applications/ChatGPT.app/Contents/Resources/codex}"
SRC_HOME="${CODEX_HOME:-$HOME/.codex}"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT INT TERM
mkdir -p "$WORK/home" "$WORK/cwd"
[ -f "$SRC_HOME/auth.json" ] || { echo "codex.sh: no login at $SRC_HOME/auth.json" >&2; exit 1; }
ln -s "$SRC_HOME/auth.json" "$WORK/home/auth.json"
ARGS=(exec --skip-git-repo-check --ephemeral --ignore-user-config --ignore-rules -s read-only -C "$WORK/cwd" -o "$WORK/out.txt")
[ -n "${CODEX_MODEL:-}" ] && ARGS+=(-m "$CODEX_MODEL")
CODEX_HOME="$WORK/home" "$CODEX" "${ARGS[@]}" - >/dev/null 2>"$WORK/err.txt" || { cat "$WORK/err.txt" >&2; exit 1; }
cat "$WORK/out.txt"
printf 'runner-meta: {"runner": "codex.sh", "models": ["%s"], "cli": "%s"}\n' \
  "${CODEX_MODEL:-codex-default}" "$("$CODEX" --version 2>/dev/null | head -1)" >&2
