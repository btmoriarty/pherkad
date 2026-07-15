#!/usr/bin/env bash
# Package the pherkad skill as an installable .skill bundle.
# Usage: ./build.sh
# On Windows, use: Compress-Archive -Path skills/pherkad -DestinationPath pherkad.zip
#   then rename pherkad.zip to pherkad.skill
set -euo pipefail
cd "$(dirname "$0")"
rm -f pherkad.skill
(cd skills && zip -r ../pherkad.skill pherkad -x '*.DS_Store')
echo "Built pherkad.skill"
