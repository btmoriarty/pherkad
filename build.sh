#!/usr/bin/env bash
# Package the pherkad skill as an installable .skill bundle.
# Usage: ./build.sh
# Needs git; the same command works in Git Bash on Windows.
set -euo pipefail
cd "$(dirname "$0")"
rm -f pherkad.skill
# From git, not the working tree: only tracked files ship, never caches, backups or
# anything untracked beside them (I014). Uncommitted edits are left out, and said so.
if ! git diff --quiet HEAD -- skills/pherkad; then
  echo "build.sh: uncommitted changes under skills/pherkad are not in the bundle; commit them first" >&2
fi
git archive --format=zip --prefix=pherkad/ -o pherkad.skill HEAD:skills/pherkad
echo "Built pherkad.skill"
