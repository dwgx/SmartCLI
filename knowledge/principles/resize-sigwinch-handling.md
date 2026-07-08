# Resize / SIGWINCH Handling

**Statement:** Never cache terminal size once; on resize the kernel sends SIGWINCH (carrying no dimensions) as a dirty flag — re-query size and full-redraw, or you get wrap/garbage/stale borders.

**Mechanism / real API:**
```
Kernel stores size as  struct winsize { ws_row, ws_col, ws_xpixel, ws_ypixel }.
  TIOCGWINSZ = get, TIOCSWINSZ = set.  On change, kernel sends SIGWINCH to the pty's fg process group.
tmux resize path: client resize -> tmux updates layout/pane geometry -> sets pane pty winsize
  -> kernel delivers SIGWINCH -> app re-queries via ioctl(TIOCGWINSZ) / os.get_terminal_size(fd)
  / shutil.get_terminal_size().
SIGWINCH carries NO dimensions and signals coalesce -> treat as a DIRTY FLAG, not one-signal-per-step.
Triggers: client resize, split-window, resize-pane, zoom toggle (-Z), layout change, another client
  attaching at a different size (see window-size / aggressive-resize options).
```
Correct loop:
```
startup:  smcup (\e[?1049h) if wanted; hide cursor (\e[?25l); query size
SIGWINCH: resized = True
each frame (or when dirty): re-query size; if changed -> \e[2J + \e[H + full redraw
exit:     show cursor (\e[?25h); rmcup (\e[?1049l)
```
```python
import os, signal, sys, shutil
resized = True
def on_winch(signum, frame):
    global resized; resized = True
if hasattr(signal, "SIGWINCH"):          # Unix only
    signal.signal(signal.SIGWINCH, on_winch)
# Windows (ConPTY): signal.SIGWINCH does not exist; resize is host-driven via
# ResizePseudoConsole(HPCON, COORD). Fall back to polling shutil.get_terminal_size() each frame.
```
What breaks if you cache size: draw past new right edge -> wrap+garbage; shrink -> stale chars/borders; cursor addressing hits wrong cells; boxes/progress/double-width misalign; alt-screen apps look corrupted.

**Source:** https://man7.org/linux/man-pages/man1/tmux.1.html (resize/window-size options; SIGWINCH Unix-only https://docs.python.org/3/library/signal.html ; ResizePseudoConsole https://learn.microsoft.com/en-us/windows/console/resizepseudoconsole — project research R6 §3)

**See also:** [[cursor-and-screen-control]], [[flicker-free-rendering]], [[tmux-alternate-screen]], [[cell-grid-model]], [[tmux-launch-and-sizing]]
