#!/usr/bin/env sh
# fx-split.sh -- split the current tmux window and run fx effect(s) in panes.
#
#   fx-split.sh donut --theme fire            # split, run donut in the new pane
#   fx-split.sh donut fire                     # 2-up: donut | fire (side by side)
#   fx-split.sh -v donut                       # vertical split (stacked) instead
#   fx-split.sh donut fire --theme synthwave   # theme applies to BOTH effects
#
# One effect  -> split off a new pane and run it there (current pane untouched).
# Two effects -> a clean 2-up: current pane becomes the FIRST effect, a new
#                pane runs the SECOND, side by side (or stacked with -v).
#
# Trailing fx flags (anything starting with `--`, plus their values) apply to
# every effect. For finer control (per-effect themes/params, one alt-screen,
# no pane seams) use the built-in compositor instead:
#     python -m fx show --seq "donut:fire:6,plasma::4"
#     python -m fx show --seq "donut|fire:synthwave:6"   # split INSIDE one pane
#
# No tmux? Prints the direct/compositor alternatives and exits 0 (clean).
set -eu

# --------------------------------------------------------------------------
# Locate skill dir + python (same robust resolution as fx-popup.sh).
# --------------------------------------------------------------------------
script_path=$0
while [ -h "$script_path" ]; do
    link=$(ls -ld -- "$script_path" | sed -e 's/^.*-> //')
    case $link in
        /*) script_path=$link ;;
        *)  script_path=$(dirname -- "$script_path")/$link ;;
    esac
done
TMUX_DIR=$(cd -- "$(dirname -- "$script_path")" && pwd)
SKILL_DIR=$(cd -- "$TMUX_DIR/.." && pwd)

find_python() {
    for c in "${FX_PYTHON:-}" python3 python py; do
        [ -n "$c" ] || continue
        if command -v "$c" >/dev/null 2>&1; then
            if [ "$c" = py ]; then printf '%s -3' "$c"; else printf '%s' "$c"; fi
            return 0
        fi
    done
    return 1
}

# --------------------------------------------------------------------------
# tmux guard: degrade cleanly.
# --------------------------------------------------------------------------
if ! command -v tmux >/dev/null 2>&1; then
    cat >&2 <<EOF
fx-split: tmux is not installed -- cannot split a window here.

  Run one effect directly (the fx play loop owns its own alt-screen):
      cd "$SKILL_DIR"
      python -m fx play <effect> --seconds 8

  For a side-by-side of TWO effects WITHOUT tmux, use the built-in
  split-screen compositor (both in one alt-screen, no pane seams):
      python -m fx show --seq "donut|fire:synthwave:6"

  To get real tmux panes:
      Debian/Ubuntu : sudo apt install tmux
      macOS (brew)  : brew install tmux
      Windows       : use WSL, or use the compositor form above.
EOF
    exit 0
fi

# Must be inside a tmux client for split-window to target a real window.
if [ -z "${TMUX:-}" ]; then
    echo "fx-split: not inside a tmux session. Start one first:  tmux new -s fx" >&2
    echo "          (or run:  python -m fx show --seq \"donut|fire:6\"  -- no tmux needed)" >&2
    exit 4
fi

# --------------------------------------------------------------------------
# Parse: [-v|-h] EFFECT1 [EFFECT2] [-- ...fx flags...]
# --------------------------------------------------------------------------
SPLIT_DIR="-h"   # tmux -h = split into LEFT|RIGHT (side by side)
while [ $# -gt 0 ]; do
    case $1 in
        -v|--vertical)   SPLIT_DIR="-v"; shift ;;
        -h|--horizontal) SPLIT_DIR="-h"; shift ;;
        --) shift; break ;;
        -*) break ;;
        *)  break ;;
    esac
done

EFF1=""
EFF2=""
if [ $# -gt 0 ] && [ "${1#-}" = "$1" ]; then EFF1=$1; shift; fi
if [ $# -gt 0 ] && [ "${1#-}" = "$1" ]; then EFF2=$1; shift; fi

if [ -z "$EFF1" ]; then
    echo "fx-split: need at least one effect. Usage: fx-split.sh [-v] EFFECT [EFFECT2] [fx flags]" >&2
    exit 2
fi

# Remaining args ($@) are shared fx flags for both panes.
EXTRA=$*
PY=$(find_python) || { echo "fx-split: no python interpreter found (set FX_PYTHON)" >&2; exit 3; }

run_cmd() {   # $1 = effect name -> full shell command string for a pane
    case $1 in
        list|show|gallery) _sub="$1 $EXTRA" ;;          # own/ no bound flag
        play|random)       _sub="$1 $EXTRA"; _sub=$(_bound "$_sub") ;;
        *)                 _sub="play $1 $EXTRA"; _sub=$(_bound "$_sub") ;;
    esac
    printf 'cd "%s" && %s -m fx %s' "$SKILL_DIR" "$PY" "$_sub"
}

_bound() {    # add a default --seconds 10 unless a bound is already present
    case " $1 " in
        *" --seconds "*|*" --frames "*|*" --forever "*|*" --once "*) printf '%s' "$1" ;;
        *) printf '%s --seconds 10' "$1" ;;
    esac
}

if [ -n "$EFF2" ]; then
    # 2-up: current pane runs EFF1, new pane runs EFF2.
    tmux split-window "$SPLIT_DIR" "$(run_cmd "$EFF2")"
    tmux select-layout even-horizontal >/dev/null 2>&1 || true
    # respawn-pane replaces the current pane's shell with EFF1
    tmux respawn-pane -k -t "$TMUX_PANE" "$(run_cmd "$EFF1")"
else
    # single effect: run it in a fresh split pane, leave current pane alone.
    exec tmux split-window "$SPLIT_DIR" "$(run_cmd "$EFF1")"
fi
