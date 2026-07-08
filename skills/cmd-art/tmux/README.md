# fx + tmux

Optional tmux launchers for the `fx` effect engine. These are a convenience
layer: they let you throw an effect into a **popup** or a **split pane** without
leaving your current tmux window. They are *not* required -- the fx play loop
already owns its own single alt-screen session, so `python -m fx play <effect>`
works standalone in any VT terminal.

> This dev box has **no tmux**. Both scripts detect that, print how to install
> tmux (and the no-tmux alternative), and exit `0` cleanly -- they never fail a
> pipeline just because tmux is missing.

## Scripts

### `fx-popup.sh` -- effect in a floating popup
Opens `tmux display-popup -E` (needs **tmux >= 3.2**) running one effect, then
closes the popup when it ends.

```sh
fx-popup.sh donut --theme fire          # play donut in an 80%x80% popup
fx-popup.sh gallery --seconds-per 2     # tour every effect in a popup
fx-popup.sh random                      # surprise me
fx-popup.sh -w 100 -h 30 sphere         # size the popup (cols x rows or NN%)
```
The first non-flag token is the effect name (bare subcommands `gallery`,
`random`, `show`, `list`, `play` are passed through as-is); everything after it
goes straight to `python -m fx`. `play`/`random`/effect runs get a default
`--seconds 10` bound unless you pass `--seconds`/`--frames`/`--forever`/`--once`,
so a popup never runs forever by accident.

### `fx-split.sh` -- effect(s) in split panes
Must be run **inside** a tmux session (`$TMUX` set).

```sh
fx-split.sh donut --theme fire          # split, run donut in the NEW pane
fx-split.sh donut fire                   # 2-up: donut | fire, side by side
fx-split.sh -v donut                     # vertical (stacked) split instead
fx-split.sh donut fire --theme synthwave # trailing fx flags apply to BOTH
```
- One effect -> a new pane runs it, current pane untouched.
- Two effects -> current pane is respawned with the first effect, a new pane
  runs the second (a clean 2-up). Same default-bound rule as the popup.

For per-effect themes/params, a single seamless alt-screen, and no pane
borders, prefer the **built-in compositor** instead of tmux panes:
```sh
python -m fx show --seq "donut|fire:synthwave:6"   # split INSIDE one screen
python -m fx show --seq "donut:fire:6,plasma::4"    # timed multi-segment show
```

## Truecolor passthrough (important)

tmux collapses 24-bit color to 256 unless you tell it the outer terminal is
truecolor-capable. Add to `~/.tmux.conf`:

```tmux
set -g  default-terminal "tmux-256color"
set -ga terminal-overrides ",*:Tc"
```

- `default-terminal "tmux-256color"` advertises a modern terminfo to programs
  inside tmux.
- `terminal-overrides ",*:Tc"` sets the `Tc` (truecolor) capability for every
  outer `$TERM`, so tmux forwards `\x1b[38;2;R;G;Bm` / `\x1b[48;2;R;G;Bm`
  sequences verbatim instead of quantizing them.

Reload after editing: `tmux source-file ~/.tmux.conf` (or start a fresh
server). Verify with `tmux info | grep Tc` (should show `Tc: (flag) true`), and
your outer terminal (Windows Terminal, iTerm2, kitty, etc.) must itself support
truecolor. Newer tmux also honors `set -as terminal-features ",*:RGB"` as an
alternative to the `Tc` override.

## Configuration

- `FX_PYTHON` -- interpreter to use (default: first of `python3`, `python`, or
  the Windows `py -3` launcher found on `PATH`).
- Popup size: `-w/--popup-width`, `-h/--popup-height` accept tmux size syntax
  (`80%`, `100`, etc.). Split direction: `-h` (side by side, default) or `-v`
  (stacked).

Both scripts resolve their own location (following symlinks) to find the skill
dir, so they work from any cwd and regardless of where they're symlinked.

## No-tmux degradation

When `tmux` is not on `PATH`, each script prints:
1. the direct standalone command (`python -m fx play <effect>`),
2. for `fx-split`, the compositor `--seq "a|b"` equivalent,
3. install hints (apt / brew / WSL),

then exits `0`. `fx-split.sh` also exits non-zero only for real usage errors
(no effect name, `exit 2`; not inside tmux while tmux *is* installed, `exit 4`).
