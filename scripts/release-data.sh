#!/usr/bin/env bash
set -euo pipefail

scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT

snapshot_prefix=earnings-data-
latest_snapshot() {
  gh release list --repo "$GITHUB_REPOSITORY" --limit 50 --json tagName,isDraft,isPrerelease \
    --jq '[.[] | select(.isPrerelease and (.isDraft | not) and
      (.tagName | test("^earnings-data-[0-9]{14}-[0-9a-f]{12}$"))) | .tagName] | sort | last // ""'
}

download_snapshot() {
  local tag=$1 expected
  gh release download "$tag" --repo "$GITHUB_REPOSITORY" \
    --pattern earnings-data.zip --dir "$scratch"
  expected=${tag##*-}
  [[ $(sha256sum "$scratch/earnings-data.zip" | cut -c1-12) == "$expected" ]]
}

case "$1" in
  restore)
    if [[ -n ${SNAPSHOT_TAG:-} ]]; then
      [[ "$SNAPSHOT_TAG" =~ ^earnings-data-[0-9]{14}-[0-9a-f]{12}$ ]]
      tag=$SNAPSHOT_TAG
    else
      tag=$(latest_snapshot)
    fi
    if [[ -n "$tag" ]]; then
      download_snapshot "$tag"
      python scripts/data_snapshot.py restore "$scratch/earnings-data.zip"
      echo "Restored $tag"
    else
      echo "Using checked-in data to seed the first snapshot."
    fi
    ;;
  publish)
    python scripts/data_snapshot.py pack "$scratch/earnings-data.zip"
    digest=$(sha256sum "$scratch/earnings-data.zip" | cut -c1-12)
    previous=$(latest_snapshot)
    if [[ ${previous##*-} == "$digest" ]]; then
      echo "Snapshot is unchanged."
      exit 0
    fi
    tag="$snapshot_prefix$(date -u +%Y%m%d%H%M%S)-$digest"
    gh release create "$tag" "$scratch/earnings-data.zip" --repo "$GITHUB_REPOSITORY" \
      --target "$GITHUB_SHA" --prerelease --latest=false --title "Earnings data $tag" \
      --notes "Validated S&P 500 earnings snapshot used by GitHub Pages."
    ;;
  *) echo "Usage: $0 restore|publish" >&2; exit 2 ;;
esac
