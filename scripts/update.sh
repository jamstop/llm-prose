#!/usr/bin/env bash
# Fast-forward this checkout to the latest remote. Safe: never clobbers local
# work (ff-only no-ops if the branch has diverged or the tree is dirty).
# The local Cursor plugin symlinks here, so a successful pull = up-to-date plugin.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2
git fetch --quiet origin && git merge --ff-only --quiet @{u} 2>/dev/null \
  && echo "llm-prose: up to date ($(git rev-parse --short HEAD))" \
  || echo "llm-prose: skipped pull (dirty tree or diverged branch)"
