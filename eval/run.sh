#!/usr/bin/env bash
# Tiny behavioral eval: drives the real comment-bloat-review skill through the
# Cursor CLI against a fixture with planted comments, then checks the verdict.
#
# Each comment in the fixture carries a sentinel token:
#   CMT_B* = bloat to DELETE (narration, notes-to-self, dead code, trivial doc)
#   CMT_T* = kernel worth keeping, oversized as written -> TIGHTEN, not delete
#            (over-documented public API, or a dense design-doc comment)
#   CMT_M* = worth keeping but misplaced -> MOVE (inline at the lines it
#            describes, or out to the PR description)
#   CMT_K* = comments that earn their place and should be KEPT
#
# The fixture also plants one missing-annotation case: evict_uploads has an
# unexplained magic constant and should draw an ADD suggestion; every other
# function must draw none (precision).
#
# Pass = every B*/T*/M* flagged (recall) with the right action, no K* flagged,
# and the ADD suggestion lands on evict_uploads only.
#
# Usage:  bash eval/run.sh            # pinned default model (see MODEL below)
#         MODEL=claude-sonnet-5-thinking-high bash eval/run.sh
#         RUNS=3 bash eval/run.sh     # repeat to gauge flakiness
set -uo pipefail
cd "$(dirname "$0")" || exit 2

PLUGIN="${PLUGIN_DIR:-$(cd .. && pwd)}"
SAMPLE="$(cat fixtures/sample.py)"
DELETE=(CMT_B1 CMT_B2 CMT_B3 CMT_B4 CMT_B5 CMT_B6 CMT_B7 CMT_B8 CMT_B9)
TIGHTEN=(CMT_T1 CMT_T2)
MOVE=(CMT_M1)
KEEP=(CMT_K1 CMT_K2 CMT_K3 CMT_K4)
ADD_EXPECT=evict_uploads
RUNS="${RUNS:-1}"
# Pinned so a shifting CLI default can't silently move the eval baseline;
# override with MODEL=… (MODEL=auto for the CLI default).
MODEL="${MODEL:-claude-sonnet-5-thinking-high}"
MODEL_ARG=(--model "$MODEL"); [ "$MODEL" = auto ] && MODEL_ARG=()

command -v cursor-agent >/dev/null || { echo "cursor-agent not found on PATH"; exit 2; }

PROMPT="Use the comment-bloat-review skill from the loaded plugin to review the comments in this file.
Each comment contains a token like CMT_XX. For every comment you would flag, print exactly one line:
FLAG: <token> <delete|tighten|move>
Use 'tighten' when the comment has a kernel worth keeping but is oversized as written -- keep 1-2 direct lines here, cut the rest; use 'move' when the content is worth keeping but belongs somewhere else (split inline to the exact lines it describes, or out to the PR description); use 'delete' when the whole comment should go. Do NOT flag comments that earn their place.
Also apply the skill's missing-annotation check: if a function needs a gotcha-class annotation it doesn't have (unexplained magic constant, unlinked workaround, breakable invariant), print exactly one line per function:
ADD: <function_name>
Suggest additions sparingly, exactly as the skill says -- zero ADD lines for code that reads fine. Print only FLAG: and ADD: lines, nothing else.

\`\`\`python
$SAMPLE
\`\`\`"

pass_runs=0
for i in $(seq 1 "$RUNS"); do
  echo "=== run $i/$RUNS ==="
  OUT=$(cursor-agent --plugin-dir "$PLUGIN" ${MODEL_ARG[@]+"${MODEL_ARG[@]}"} --trust --force -p "$PROMPT" --output-format text 2>/dev/null)
  FLAG_LINES=$(printf '%s\n' "$OUT" | grep -iE '^[[:space:]]*FLAG:')
  ADD_LINES=$(printf '%s\n' "$OUT" | grep -iE '^[[:space:]]*ADD:')
  flagged()   { printf '%s\n' "$FLAG_LINES" | grep -q "$1"; }
  tightened() { printf '%s\n' "$FLAG_LINES" | grep "$1" | grep -qi 'tighten'; }
  moved()     { printf '%s\n' "$FLAG_LINES" | grep "$1" | grep -qi 'move'; }

  miss=0; fp=0; wrongact=0
  for d in "${DELETE[@]}"; do
    if flagged "$d"; then echo "  caught   $d"; else echo "  MISSED   $d"; miss=$((miss+1)); fi
  done
  for t in "${TIGHTEN[@]}"; do
    if flagged "$t"; then
      if tightened "$t"; then echo "  tighten  $t"; else echo "  WRONGACT $t (flagged, not as tighten)"; wrongact=$((wrongact+1)); fi
    else echo "  MISSED   $t"; miss=$((miss+1)); fi
  done
  for m in "${MOVE[@]}"; do
    if flagged "$m"; then
      if moved "$m"; then echo "  move     $m"; else echo "  WRONGACT $m (flagged, not as move)"; wrongact=$((wrongact+1)); fi
    else echo "  MISSED   $m"; miss=$((miss+1)); fi
  done
  for k in "${KEEP[@]}"; do
    if flagged "$k"; then echo "  FALSE+   $k"; fp=$((fp+1)); else echo "  kept     $k"; fi
  done

  # Missing-annotation: exactly one ADD, on the planted function.
  if printf '%s\n' "$ADD_LINES" | grep -q "$ADD_EXPECT"; then
    echo "  add      $ADD_EXPECT"
  else echo "  MISSED   ADD:$ADD_EXPECT"; miss=$((miss+1)); fi
  add_extra=$(printf '%s\n' "$ADD_LINES" | grep -cv -e "$ADD_EXPECT" -e '^$')
  if [ "${add_extra:-0}" -gt 0 ]; then
    echo "  FALSE+   $add_extra stray ADD line(s):"; printf '%s\n' "$ADD_LINES" | grep -v "$ADD_EXPECT" | sed 's/^/           /'
    fp=$((fp+add_extra))
  fi

  total=$(( ${#DELETE[@]} + ${#TIGHTEN[@]} + ${#MOVE[@]} + 1 ))
  recall=$(( total - miss ))
  echo "  recall ${recall}/${total} findings, ${wrongact} wrong-action, ${fp} false positive(s)"
  if [ "$miss" -eq 0 ] && [ "$fp" -eq 0 ] && [ "$wrongact" -eq 0 ]; then echo "  -> PASS"; pass_runs=$((pass_runs+1)); else echo "  -> FAIL"; fi
done

echo "------------------------------------------------------------"
echo "passed $pass_runs/$RUNS run(s)"
[ "$pass_runs" -eq "$RUNS" ] && exit 0 || exit 1
