# Alternate Screen Buffer (VT + per-pane in tmux)

**Statement:** The alternate screen gives an app a clean full-screen canvas that is discarded on exit, restoring the prior scrollback; in tmux each pane keeps its OWN alt-screen buffer.

**Exact sequences / config:**
```
enter (smcup): \e[?1049h   leave (rmcup): \e[?1049l   (1049 = save cursor + switch + clear)
older:         \e[?47h                    \e[?47l
```
```tmux
set -g alternate-screen on    # default; with `off` tmux blocks pane smcup/rmcup and art scrolls into scrollback
```
Behavior:
- Each tmux pane is a separate pty with its own virtual terminal state, INCLUDING its own alt-screen buffer. App emits smcup/rmcup; tmux switches THAT pane's alt screen if `alternate-screen on`.
- While in alt screen, lines are NOT added to normal pane history (the "can't scroll back after vim/less" FAQ — expected).
- Nesting terminal -> tmux -> app works when each layer has the right TERM + terminfo. AVOID configs that delete smcup/rmcup, e.g. `set -g terminal-overrides '*:smcup@:rmcup@'`.
- App responsibility: smcup on start, rmcup on EVERY exit path. You cannot trap SIGKILL — after a hard kill the pane may stay in alt screen until `printf '\033[?1049l'` / `reset` / `tput rmcup`.
- capture-pane grabs whatever is currently displayed (alt or normal); `-a` forces the alternate screen (history unavailable there; errors if no alt screen unless `-q`).

**Source:** https://man7.org/linux/man-pages/man1/tmux.1.html (alternate-screen, capture-pane -a; sequences from xterm ctlseqs https://invisible-island.net/xterm/ctlseqs/ctlseqs.html — project research R6 §2, R5 §B.7)

**See also:** [[cursor-and-screen-control]], [[flicker-free-rendering]], [[truecolor-passthrough-tmux]], [[tmux-capture-pane]], [[resize-sigwinch-handling]], [[alternate-screen-buffer]] (agent capture gotcha), [[alternate-screen-detection]] (detecting the switch in the byte stream)
