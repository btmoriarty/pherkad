#!/usr/bin/env bash
# Run the smoke test and every unittest suite against this checkout, report each,
# and exit nonzero if any failed. The pre-commit hook runs this, so a commit that
# breaks a suite is refused before it reaches CI. PYTHON picks the interpreter
# (PYTHON=/usr/bin/python3 tests/run-all.sh checks the 3.8 floor).
set -u
R="$(cd "$(dirname "$0")/.." && pwd)"; T=$R/skills/pherkad/tools
PY=${PYTHON:-python3}
fail=0
bash "$R/tests/smoke.sh" || fail=1
for s in "$T"/test_*.py "$R/eval/test_study.py"; do
  out=$("$PY" "$s" 2>&1); code=$?
  summary=$(printf '%s\n' "$out" | grep -E '^(OK|FAILED)' | tail -1)
  if [ $code -ne 0 ]; then
    fail=1
    echo "suites: FAIL $(basename "$s"): ${summary:-exit $code}"
    printf '%s\n' "$out" | grep -E '^(FAIL|ERROR):|Error' | head -8 | sed 's/^/    /'
  else
    echo "suites: ok   $(basename "$s")"
  fi
done
[ $fail -eq 0 ] && echo "suites: all green ($("$PY" --version 2>&1))"
exit $fail
