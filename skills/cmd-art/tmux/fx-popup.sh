#!/usr/bin/env sh
# fx-popup.sh -- run an fx effect inside a tmux popup (display-popup -E).
#
#   fx-popup.sh donut --theme fire
#   fx-popup.sh gallery --seconds-per 2
#   fx-popup.sh --seconds 8 plasma --set palette=rgb
#   fx-popup.sh -w 100 -h 30 sphere --theme ocean
#
# The first non-flag token is the fx EFFECT name (or a bare subcommand:
# gallery / random / show). Everything after it is passed straight through to
# `python -m fx`. A leading `-w/-h` sizes the popup; `--` ends popup-flag
# parsing.
#
# No tmux? This prints how to get it and exits 0 (clean, non-fatal) so callers
# and CI never break just because tmux is absent (this dev box has none).
set -eu

# --------------------------------------------------------------------------
# Locate the skill dir (parent of this script's dir) and a python interpreter.
# Robust to symlinks, spaces in the path, and any cwd.
# --------------------------------------------------------------------------
script_path=$0
# resolve symlinks without readlink -f (not on every platform)
while [ -h "$script_path" ]; do
    link=$(ls -ld -- "$script_path" | sed -e 's/^.*-> //')
    case $link in
        /*) script_path=$link ;;
        *)  script_path=$(dirname -- "$script_path")/$link ;;
    esac
done
TMUX_DIR=$(cd -- "$(dirname -- "$script_path")" && pwd)
SKILL_DIR=$(cd -- "$TMUX_DIR/.." && pwd)   # skills/cmd-art

find_python() {
    for c in "${FX_PYTHON:-}" python3 python py; do
        [ -n "$c" ] || continue
        if command -v "$c" >/dev/null 2>&1; then
            # `py` is the Windows launcher; make it run python
            if [ "$c" = py ]; then printf '%s -3' "$c"; else printf '%s' "$c"; fi
            return 0
        fi
    done
    return 1
}

# --------------------------------------------------------------------------
# tmux guard: degrade cleanly when tmux is unavailable.
# --------------------------------------------------------------------------
if ! command -v tmux >/dev/null 2>&1; then
    cat >&2 <<EOF
fx-popup: tmux is not installed -- cannot open a popup here.

  The fx play loop already owns a single alt-screen session, so you can run
  the effect directly, without tmux:

      cd "$SKILL_DIR"
      python -m fx play $*

  To get tmux popups (needs tmux >= 3.2 for display-popup):
      Debian/Ubuntu : sudo apt install tmux
      macOS (brew)  : brew install tmux
      Windows       : use WSL, or run the effect directly (no tmux needed).
EOF
    exit 0
fi

# --------------------------------------------------------------------------
# Parse optional popup sizing flags, then the effect + its args.
# --------------------------------------------------------------------------
POP_W="80%"
POP_H="80%"
while [ $# -gt 0 ]; do
    case $1 in
        -w|--popup-width)  POP_W=$2; shift 2 ;;
        -h|--popup-height) POP_H=$2; shift 2 ;;
        --) shift; break ;;
        -*) break ;;   # an fx flag (e.g. --seconds) -- stop popup parsing
        *)  break ;;   # the effect name
    esac
done

if [ $# -eq 0 ]; then
    echo "fx-popup: no effect given. Usage: fx-popup.sh <effect|gallery|random> [fx args]" >&2
    exit 2
fi

PY=$(find_python) || { echo "fx-popup: no python interpreter found (set FX_PYTHON)" >&2; exit 3; }

# If the first token is a bare subcommand, use it as-is; otherwise it's an
# effect name that needs the `play` subcommand. Only `play`/`random` accept
# --seconds (gallery uses --seconds-per; list/show ignore bounds), and only
# those two can run unbounded -- so only they get the default bound. (Avoids
# argparse prefix-matching --seconds onto gallery's --seconds-per.)
case $1 in
    list|show|gallery)       SUB="$*"; bound=no ;;
    play|random)             SUB="$*"; bound=yes ;;
    *)                       SUB="play $*"; bound=yes ;;
esac

# Bounded by default so a popup never runs forever if the caller forgets.
if [ "$bound" = yes ]; then
    case " $SUB " in
        *" --seconds "*|*" --frames "*|*" --forever "*|*" --once "*) ;;
        *) SUB="$SUB --seconds 10" ;;
    esac
fi

# display-popup -E runs the command and closes the popup on exit.
# We cd into the skill dir so `python -m fx` resolves the package.
# shellcheck disable=SC2086
exec tmux display-popup -E -w "$POP_W" -h "$POP_H" \
    "cd \"$SKILL_DIR\" && $PY -m fx $SUB"
