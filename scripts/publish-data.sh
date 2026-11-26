#!/usr/bin/env bash
set -euo pipefail

bash scripts/release-data.sh publish

git add sp500_mapping.json
if [[ "$PAGES_BUILD_TYPE" == legacy ]]; then
  # Keep branch-based Pages publishing until the Actions publishing source is selected.
  git add data.json historical_data.json official_history.json history_status.json official_scan_state.json
fi

if ! git diff --cached --quiet; then
  git config user.name 'github-actions[bot]'
  git config user.email 'github-actions[bot]@users.noreply.github.com'
  git commit -m 'Update quarterly earnings publication [skip ci]'
  git pull --rebase origin main
  git push origin HEAD:main
fi
