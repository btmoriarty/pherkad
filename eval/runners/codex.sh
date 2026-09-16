#!/bin/bash
# A study.py runner: prompt on stdin, the model's final message on stdout, nothing else.
# Uses the Codex binary bundled with the ChatGPT app; set CODEX_MODEL to pick the model.
CODEX="${CODEX_BIN:-/Applications/ChatGPT.app/Contents/Resources/codex}"
OUT=$(mktemp)
trap 'rm -f "$OUT"' EXIT
ARGS=(exec --skip-git-repo-check --ephemeral -s read-only -o "$OUT" -)
if [ -n "$CODEX_MODEL" ]; then ARGS=(exec --skip-git-repo-check --ephemeral -s read-only -m "$CODEX_MODEL" -o "$OUT" -); fi
"$CODEX" "${ARGS[@]}" >/dev/null 2>"$OUT.err" || { cat "$OUT.err" >&2; rm -f "$OUT.err"; exit 1; }
rm -f "$OUT.err"
cat "$OUT"
