#!/usr/bin/env bash
# Smoke test for pherkad: the tools compile, and replycheck passes clean prose and fails prose with tells.
set -u; R=/Users/moriarty/Documents/kochab/pherkad; T=$R/skills/pherkad/tools; fail=0
say(){ echo "smoke: $*"; fail=1; }
python3 -m py_compile "$T"/*.py || say "a tool does not compile"
python3 "$T/replycheck.py" "$R/tests/fixtures/clean.md" >/dev/null 2>&1 || say "replycheck rejected the clean fixture"
python3 "$T/replycheck.py" "$R/tests/fixtures/tells.md" >/dev/null 2>&1 && say "replycheck passed the fixture with tells"
[ $fail -eq 0 ] && echo "smoke: pherkad ok"; exit $fail
