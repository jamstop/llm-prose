#!/usr/bin/env bash
# Cut a release. Bumps the version across every manifest, validates, commits,
# tags, and pushes.
#
# Why this matters: Claude Code keys the installed plugin cache by version
# (.../llm-prose/<version>/). Pushing commits WITHOUT bumping the version does
# not reach installed users — `claude plugin update` reports "already latest".
# So every user-facing change ships through here.
#
# Usage:
#   scripts/release.sh            # patch bump (x.y.Z+1)
#   scripts/release.sh minor      # x.Y+1.0
#   scripts/release.sh major      # X+1.0.0
#   scripts/release.sh 1.2.3      # explicit
set -euo pipefail
cd "$(dirname "$0")/.." || exit 2

cur=$(jq -r '.version' .cursor-plugin/plugin.json)
IFS=. read -r MA MI PA <<<"$cur"
case "${1:-patch}" in
  major) new="$((MA+1)).0.0";;
  minor) new="$MA.$((MI+1)).0";;
  patch) new="$MA.$MI.$((PA+1))";;
  *)     new="$1";;
esac
echo "$new" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$' || { echo "bad version: $new"; exit 2; }

git diff --quiet && git diff --cached --quiet || { echo "note: committing pending changes with this release"; }
echo "release: $cur -> $new"

for f in .cursor-plugin/plugin.json .claude-plugin/plugin.json; do
  jq --arg v "$new" '.version=$v' "$f" >"$f.tmp" && mv "$f.tmp" "$f"
done
jq --arg v "$new" '.plugins |= map(.version=$v)' .claude-plugin/marketplace.json >.claude-plugin/marketplace.json.tmp \
  && mv .claude-plugin/marketplace.json.tmp .claude-plugin/marketplace.json

bash scripts/validate.sh >/dev/null || { echo "validation failed — aborting release"; exit 1; }

git add -A
git commit -q -m "release: v$new"
# Prefer Claude's tagger (validates plugin.json vs marketplace entry agreement); fall back to a plain tag.
claude plugin tag . >/dev/null 2>&1 || git tag "llm-prose--v$new"
git push -q origin HEAD --tags

echo "released v$new. To pull it into your install: claude plugin update llm-prose@llm-prose"
