#!/usr/bin/env bash
# Tiny behavioral eval: drives the real comment-bloat-review skill through the
# Cursor CLI against a fixture with planted comments, then checks the verdict.
#
# Each comment in the fixture carries a sentinel token:
#   CMT_B* = bloat that SHOULD be flagged (narration, notes-to-self, dead code, doc dump)
#   CMT_K* = comments that earn their place and should be KEPT
#
# Pass = every B* flagged (recall) and no K* flagged (precision).
#
# Usage:  bash eval/run.sh            # default model
#         MODEL=sonnet-4-thinking bash eval/run.sh
#         RUNS=3 bash eval/run.sh     # repeat to gauge flakiness
set -uo pipefail
cd "$(dirname "$0")" || exit 2

PLUGIN="${PLUGIN_DIR:-$(cd .. && pwd)}"
SAMPLE="$(cat fixtures/sample.py)"
BLOAT=(CMT_B1 CMT_B2 CMT_B3 CMT_B4)
KEEP=(CMT_K1 CMT_K2)
RUNS="${RUNS:-1}"
MODEL_ARG=(); [ -n "${MODEL:-}" ] && MODEL_ARG=(--model "$MODEL")

command -v cursor-agent >/dev/null || { echo "cursor-agent not found on PATH"; exit 2; }

PROMPT="Use the comment-bloat-review skill from the loaded plugin to review ONLY the comments in this file.
Each comment contains a token like CMT_XX. For every comment you would DELETE or TIGHTEN (flag as bloat), print exactly one line: FLAG: <that token>. Do NOT flag comments that earn their place. Print only FLAG: lines, nothing else.

\`\`\`python
$SAMPLE
\`\`\`"

pass_runs=0
for i in $(seq 1 "$RUNS"); do
  echo "=== run $i/$RUNS ==="
  OUT=$(cursor-agent --plugin-dir "$PLUGIN" ${MODEL_ARG[@]+"${MODEL_ARG[@]}"} --trust --force -p "$PROMPT" --output-format text 2>/dev/null)
  FLAGGED=$(printf '%s\n' "$OUT" | grep -iE '^[[:space:]]*FLAG:' | grep -oE 'CMT_[A-Z0-9]+' | sort -u)

  miss=0; fp=0
  for b in "${BLOAT[@]}"; do
    if printf '%s\n' "$FLAGGED" | grep -qx "$b"; then echo "  caught  $b"; else echo "  MISSED  $b"; miss=$((miss+1)); fi
  done
  for k in "${KEEP[@]}"; do
    if printf '%s\n' "$FLAGGED" | grep -qx "$k"; then echo "  FALSE+  $k"; fp=$((fp+1)); else echo "  kept    $k"; fi
  done

  recall=$(( (${#BLOAT[@]} - miss) ))
  echo "  recall ${recall}/${#BLOAT[@]} bloat, ${fp} false positive(s)"
  if [ "$miss" -eq 0 ] && [ "$fp" -eq 0 ]; then echo "  -> PASS"; pass_runs=$((pass_runs+1)); else echo "  -> FAIL"; fi
done

echo "------------------------------------------------------------"
echo "passed $pass_runs/$RUNS run(s)"
[ "$pass_runs" -eq "$RUNS" ] && exit 0 || exit 1
