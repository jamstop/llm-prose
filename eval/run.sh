#!/usr/bin/env bash
# Tiny behavioral eval: drives the real comment-bloat-review skill through the
# Cursor CLI against a fixture with planted comments, then checks the verdict.
#
# Each comment in the fixture carries a sentinel token:
#   CMT_B* = bloat to DELETE (narration, notes-to-self, dead code, trivial doc)
#   CMT_T* = kernel worth keeping, oversized as written -> TIGHTEN, not delete
#            (over-documented public API, or a dense design-doc comment)
#   CMT_K* = comments that earn their place and should be KEPT
#
# Pass = every B*/T* flagged (recall), each T* flagged as "tighten" (action), and
# no K* flagged (precision).
#
# Usage:  bash eval/run.sh            # pinned default model (see MODEL below)
#         MODEL=claude-sonnet-5-thinking-high bash eval/run.sh
#         RUNS=3 bash eval/run.sh     # repeat to gauge flakiness
set -uo pipefail
cd "$(dirname "$0")" || exit 2

PLUGIN="${PLUGIN_DIR:-$(cd .. && pwd)}"
SAMPLE="$(cat fixtures/sample.py)"
DELETE=(CMT_B1 CMT_B2 CMT_B3 CMT_B4 CMT_B5 CMT_B6 CMT_B7 CMT_B8)
TIGHTEN=(CMT_T1 CMT_T2)
KEEP=(CMT_K1 CMT_K2 CMT_K3 CMT_K4)
RUNS="${RUNS:-1}"
# Pinned so a shifting CLI default can't silently move the eval baseline;
# override with MODEL=… (MODEL=auto for the CLI default).
MODEL="${MODEL:-claude-sonnet-5-thinking-high}"
MODEL_ARG=(--model "$MODEL"); [ "$MODEL" = auto ] && MODEL_ARG=()

command -v cursor-agent >/dev/null || { echo "cursor-agent not found on PATH"; exit 2; }

PROMPT="Use the comment-bloat-review skill from the loaded plugin to review ONLY the comments in this file.
Each comment contains a token like CMT_XX. For every comment you would flag, print exactly one line:
FLAG: <token> <delete|tighten>
Use 'tighten' when the comment has a kernel worth keeping but is oversized as written -- an over-documented public-API doc, or a dense multi-line comment whose rationale outgrows the code under it (keep 1-2 direct lines, cut the rest); use 'delete' when the whole comment should go. Do NOT flag comments that earn their place. Print only FLAG: lines, nothing else.

\`\`\`python
$SAMPLE
\`\`\`"

pass_runs=0
for i in $(seq 1 "$RUNS"); do
  echo "=== run $i/$RUNS ==="
  OUT=$(cursor-agent --plugin-dir "$PLUGIN" ${MODEL_ARG[@]+"${MODEL_ARG[@]}"} --trust --force -p "$PROMPT" --output-format text 2>/dev/null)
  FLAG_LINES=$(printf '%s\n' "$OUT" | grep -iE '^[[:space:]]*FLAG:')
  flagged()   { printf '%s\n' "$FLAG_LINES" | grep -q "$1"; }
  tightened() { printf '%s\n' "$FLAG_LINES" | grep "$1" | grep -qi 'tighten'; }

  miss=0; fp=0; wrongact=0
  for d in "${DELETE[@]}"; do
    if flagged "$d"; then echo "  caught   $d"; else echo "  MISSED   $d"; miss=$((miss+1)); fi
  done
  for t in "${TIGHTEN[@]}"; do
    if flagged "$t"; then
      if tightened "$t"; then echo "  tighten  $t"; else echo "  WRONGACT $t (flagged, not as tighten)"; wrongact=$((wrongact+1)); fi
    else echo "  MISSED   $t"; miss=$((miss+1)); fi
  done
  for k in "${KEEP[@]}"; do
    if flagged "$k"; then echo "  FALSE+   $k"; fp=$((fp+1)); else echo "  kept     $k"; fi
  done

  total=$(( ${#DELETE[@]} + ${#TIGHTEN[@]} ))
  recall=$(( total - miss ))
  echo "  recall ${recall}/${total} bloat, ${wrongact} wrong-action, ${fp} false positive(s)"
  if [ "$miss" -eq 0 ] && [ "$fp" -eq 0 ] && [ "$wrongact" -eq 0 ]; then echo "  -> PASS"; pass_runs=$((pass_runs+1)); else echo "  -> FAIL"; fi
done

echo "------------------------------------------------------------"
echo "passed $pass_runs/$RUNS run(s)"
[ "$pass_runs" -eq "$RUNS" ] && exit 0 || exit 1
