#!/usr/bin/env bash
# Claude Code statusLine script
# Reads statusline JSON from stdin and prints a single colored status line.
#
# Segments (in order):
#   1. Model name                        - cyan
#   2. Context window usage % (+ tokens) - traffic-light (green/yellow/red)
#   3. Rate-limit usage (5h/7d)          - magenta, traffic-light per window if possible
#   4. Output style name                 - blue
#
# Segments are separated with a dim " | ". Any segment whose data is not
# present in the input JSON is silently omitted so the line never breaks.
#
# No jq dependency: jq is not guaranteed to be on PATH (e.g. plain git-bash
# on Windows), so JSON fields are pulled with grep/sed instead. Each field is
# matched by scoping to its enclosing "name": {...} block first, so sibling
# blocks that reuse a field name (e.g. used_percentage in both
# context_window and rate_limits.*) don't collide.

input=$(cat | tr -d '\n')

# Allows one level of nested {..} (e.g. context_window.current_usage) so the
# scan doesn't stop at the nested object's closing brace and truncate the
# outer block before fields like used_percentage are reached.
get_block() {
  printf '%s' "$input" | grep -oE "\"$1\"[[:space:]]*:[[:space:]]*\{[^{}]*(\{[^{}]*\}[^{}]*)*\}" | head -1
}

get_num() {
  printf '%s' "$1" | grep -oE "\"$2\"[[:space:]]*:[[:space:]]*[0-9]+(\.[0-9]+)?" | head -1 | sed -E 's/.*:[[:space:]]*//'
}

get_str() {
  printf '%s' "$1" | grep -oE "\"$2\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" | head -1 | sed -E 's/^"'"$2"'"[[:space:]]*:[[:space:]]*"//; s/"$//'
}

# --- ANSI color helpers -----------------------------------------------------
RESET=$'\033[0m'
DIM=$'\033[2m'
CYAN=$'\033[36m'
BLUE=$'\033[34m'
GREEN=$'\033[32m'
YELLOW=$'\033[33m'
RED=$'\033[31m'
MAGENTA=$'\033[35m'

SEP="${DIM} | ${RESET}"

segments=()

# --- 1. Model name -----------------------------------------------------------
model_block=$(get_block "model")
model_name=$(get_str "$model_block" "display_name")
if [ -n "$model_name" ]; then
  segments+=("${CYAN}${model_name}${RESET}")
fi

# --- 2. Context window usage % (+ token count) -------------------------------
ctx_block=$(get_block "context_window")
ctx_used=$(get_num "$ctx_block" "used_percentage")
ctx_tokens=$(get_num "$ctx_block" "total_input_tokens")
ctx_size=$(get_num "$ctx_block" "context_window_size")
if [ -n "$ctx_used" ]; then
  ctx_color="$GREEN"
  ctx_int=${ctx_used%%.*}
  if [ "$ctx_int" -ge 80 ] 2>/dev/null; then
    ctx_color="$RED"
  elif [ "$ctx_int" -ge 50 ] 2>/dev/null; then
    ctx_color="$YELLOW"
  fi
  ctx_fmt=$(printf '%.0f' "$ctx_used" 2>/dev/null)
  ctx_seg="Ctx ${ctx_fmt}%"
  if [ -n "$ctx_tokens" ] && [ -n "$ctx_size" ]; then
    ctx_seg="${ctx_seg} ($((${ctx_tokens%%.*} / 1000))k/$((${ctx_size%%.*} / 1000))k)"
  fi
  segments+=("${ctx_color}${ctx_seg}${RESET}")
fi

# --- 3. Rate-limit usage (5h / 7d) ------------------------------------------
five_block=$(get_block "five_hour")
week_block=$(get_block "seven_day")
five_pct=$(get_num "$five_block" "used_percentage")
week_pct=$(get_num "$week_block" "used_percentage")

rl_color() {
  local pct_int=${1%%.*}
  if [ "$pct_int" -ge 80 ] 2>/dev/null; then
    printf '%s' "$RED"
  elif [ "$pct_int" -ge 50 ] 2>/dev/null; then
    printf '%s' "$YELLOW"
  else
    printf '%s' "$MAGENTA"
  fi
}

rl_parts=()
if [ -n "$five_pct" ]; then
  five_fmt=$(printf '%.0f' "$five_pct" 2>/dev/null)
  rl_parts+=("$(rl_color "$five_pct")5h ${five_fmt}%${RESET}")
fi
if [ -n "$week_pct" ]; then
  week_fmt=$(printf '%.0f' "$week_pct" 2>/dev/null)
  rl_parts+=("$(rl_color "$week_pct")7d ${week_fmt}%${RESET}")
fi
if [ "${#rl_parts[@]}" -gt 0 ]; then
  rl_joined=""
  for i in "${!rl_parts[@]}"; do
    if [ "$i" -eq 0 ]; then
      rl_joined="${rl_parts[$i]}"
    else
      rl_joined="${rl_joined}${DIM}/${RESET}${rl_parts[$i]}"
    fi
  done
  segments+=("$rl_joined")
fi

# --- 4. Output style ----------------------------------------------------------
style_block=$(get_block "output_style")
output_style=$(get_str "$style_block" "name")
if [ -n "$output_style" ]; then
  segments+=("${BLUE}${output_style}${RESET}")
fi

# --- Join segments with dim separator ----------------------------------------
line=""
for i in "${!segments[@]}"; do
  if [ "$i" -eq 0 ]; then
    line="${segments[$i]}"
  else
    line="${line}${SEP}${segments[$i]}"
  fi
done

printf '%s' "$line"
