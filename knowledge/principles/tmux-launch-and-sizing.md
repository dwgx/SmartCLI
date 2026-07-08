# tmux Launch & Sizing (popup / split / resize)

**Statement:** Run a terminal-art or TUI app in tmux via a fixed-size overlay popup (not scrapeable) or a layout-participating split (scrapeable, resizable); either way the app reads its OWN real size and full-redraws on resize.

**Exact syntax (display-popup requires tmux >= 3.2):**
```sh
# popup: per-client rectangular OVERLAY, NOT a pane, does not join the layout, can't be captured.
display-popup [-BCEkN] [-b border-lines] [-h height] [-s style] [-S border-style]
  [-T title] [-w width] [-x pos] [-y pos] [shell-command]
  # -w/-h: cols/rows OR percent (80%); default = HALF terminal if omitted.
  # -x/-y: C=center, R=right, P=pane bottom-left, M=mouse, S=status-relative, or numeric.
  # -E close when cmd exits; -EE close only on success; -k any key dismisses; -B no border.
tmux display-popup -E -w 80 -h 24 -x C -y C 'python3 ./anim.py'      # fixed 80x24 centered
tmux display-popup -E -w 80% -h 70% -x C -y C 'python3 ./anim.py'

# split-window: participates in layout, scrapeable, resizable.
split-window [-bdefhIkPvZ] [-l size] [-p percentage] [-t target] [shell-command]
  # -h L/R split (-l = cols); -v top/bottom (-l = rows, default -v); -l may be NN%.
tmux split-window -v -l 24  'python3 ./anim.py'     # 24 rows
tmux split-window -h -l 80  'python3 ./anim.py'     # 80 cols

# resize-pane
resize-pane [-DLMRTUZ] [-t target] [-x width] [-y height] [adjustment]
tmux resize-pane -t %3 -x 80 -y 24
tmux resize-pane -Z                                 # toggle zoom
```
The popup app cannot resize itself (tmux owns popup geometry — effectively fixed for its lifetime); do NOT derive size from the `-w`/`-h` args (borders/defaults make that brittle) — read your own size from inside.

POSIX guard (dev box has no tmux): `tmux_popup_available() { command -v tmux >/dev/null && [ -n "${TMUX-}" ] && tmux_version_ge 3 2; }` then fall back to running inline.

**Source:** https://man7.org/linux/man-pages/man1/tmux.1.html (popup/split/resize syntax; popup intro https://github.com/tmux/tmux/issues/2592 — project research R6 §4, R5 §B.1-B.3, B.8-B.9)

**See also:** [[resize-sigwinch-handling]], [[tmux-capture-pane]], [[tmux-alternate-screen]], [[truecolor-passthrough-tmux]]
