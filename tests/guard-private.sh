#!/usr/bin/env bash
# Refuse a commit that stages the author's private material, whatever .gitignore
# says. This repository is public; .gitignore is one line of defence and a branch
# without it (pherkad-v0.3-positive-register has none) or a `git add -f` walks
# straight past it. The pre-commit hook runs this before the suites.
#
# Private: the voice profile and rule files (links into session-hygiene), the
# correction ledger, measured profiles and references, held-out ids, review
# packets, authoring records, a root voice_config.json, the eval data, the local
# junk folder, and any backup.
set -u
patterns=(
  '^Voice_Profile[^/]*\.md$'
  '^voice-(rules|authoring|intake)\.md$'
  '^voice_config\.json$'
  '(^|/)corrections\.jsonl$'
  '(^|/)fingerprint[^/]*\.json$'
  '(^|/)reference[^/]*\.json$'
  '(^|/)holdout[^/]*\.json$'
  '(^|/)pack\.json$'
  '(^|/)prompt\.md$'
  '\.author\.json$'
  '^eval/data/'
  '^_to_delete/'
  '\.bak'
)
staged=$(git diff --cached --name-only --diff-filter=ACMR)
bad=""
for p in "${patterns[@]}"; do
  hits=$(printf '%s\n' "$staged" | grep -E "$p" || true)
  [ -n "$hits" ] && bad="$bad$hits"$'\n'
done
if [ -n "$bad" ]; then
  echo "guard-private: refusing to commit private material to a public repository:"
  printf '%s' "$bad" | sort -u | sed '/^$/d; s/^/  /'
  echo "guard-private: unstage it (git restore --staged <path>); nothing here may be forced past this check"
  exit 1
fi
exit 0
