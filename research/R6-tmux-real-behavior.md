# R6 — Real tmux Behavior for Terminal Art + TUI Driving (Raw Findings)

> **Archived first-pass research** — superseded by [`../knowledge/sources/`](../knowledge/sources/); folded into [`../knowledge/principles/`](../knowledge/principles/README.md). See [`README.md`](README.md). Kept for provenance.


Scope: what actually changes for cmd-art (emitting effects) and drive-tui (scraping panes)
when they run INSIDE tmux vs a bare terminal. Windows dev box has NO tmux; target is
tmux on Linux. This file is the raw evidence; the build-ready digest is at the bottom.

Method: 3 parallel codex live-web-search runs (medium effort) cross-checked against the
tmux man page. capture-pane flag semantics independently verified via WebFetch of
man7.org/linux/man-pages/man1/tmux.1.html on 2026-07-07.

Complements R5 PART B (which already has: version guards, popup/split/capture examples,
POSIX detection helpers, the recommended .tmux.conf skeleton). R6 goes deeper on the
MECHANICS and the exact failure-mode escape pairs, and adds corrections.

Codex source files (transient /tmp):
- Run1 truecolor+altscreen: /tmp/codex-tmux1-565-8497.md
- Run2 resize+popup/split : /tmp/codex-tmux2-17259-30080.md
- Run3 capture+failuremodes: /tmp/codex-tmux3-1736-29467.md

---

## 1. TRUECOLOR PASSTHROUGH

### default-terminal
- `set -g default-terminal "tmux-256color"` is the modern correct value. It is the `$TERM`
  handed to programs INSIDE panes. Man: default-terminal "must be set to screen, tmux or a
  derivative." `tmux-256color` describes tmux's virtual terminal better than
  `screen-256color` (which can miss italics/extended caps on some hosts).
- `screen-256color` is the older compatibility fallback (use only if `tmux-256color`
  terminfo is missing on the host).
- NOTE: `$TERM` inside tmux is tmux-256color/screen*, NOT the outer terminal's TERM.

### terminal-features (tmux >= 3.2) vs terminal-overrides (any version)
- `terminal-features` describes the OUTER terminal tmux is attached to. tmux 3.2 introduced
  named feature sets. `RGB` = outer terminal supports 24-bit SGR.
  - Modern:   `set -as terminal-features ",*:RGB"`   (or a real pattern, see below)
  - FAQ form: `set -as terminal-features ",gnome*:RGB"`
- `terminal-overrides ",*:Tc"` is the OLDER tmux extension; `Tc` is tmux's private flag
  equivalent to the official terminfo `RGB` flag. Works on any tmux version.
  - Older:    `set -as terminal-overrides ",*:Tc"`
- `RGB` is the official terminfo capability flag; `Tc` is tmux's pre-3.2 equivalent.
- Prefer real patterns over `*` if you don't want global matching:
  ```
  set -as terminal-features ",xterm-256color:RGB"
  set -as terminal-features ",alacritty*:RGB"
  set -as terminal-features ",xterm-kitty:RGB"
  set -as terminal-features ",wezterm:RGB"
  set -as terminal-features ",foot*:RGB"
  ```

### Precedence / detection flow (from tty-term.c)
tmux: reads terminfo -> applies terminal-features -> checks COLORTERM -> applies
terminal-overrides -> applies detected features/overrides. So terminal-overrides can still
force individual caps after features. Do NOT configure contradictory entries.
Source: https://raw.githubusercontent.com/tmux/tmux/master/tty-term.c

### Outer terminal + COLORTERM
- Outside tmux, `$TERM` must name the real terminal, its terminfo must support >=256 colors,
  and the emulator must actually implement `38;2`/`48;2`.
- `COLORTERM=truecolor` (or `24bit`) is a hint apps read; current tmux ALSO treats it as
  evidence to add RGB. But it is NOT a substitute for an emulator that renders RGB.
- tmux source checks COLORTERM=truecolor/24bit: same tty-term.c.

### Exact SGR sequences (ESC = 0x1b = \033 = \e)
```
24-bit fg:   \e[38;2;R;G;Bm     octal \033[38;2;R;G;Bm     hex 1b 5b 33 38 3b 32 3b ...
24-bit bg:   \e[48;2;R;G;Bm     octal \033[48;2;R;G;Bm
256 fg:      \e[38;5;Nm
256 bg:      \e[48;5;Nm
reset:       \e[0m
```

### DEGRADATION (what the user actually sees)
If the APP writes RGB but the outer terminal is NOT marked RGB, tmux quantizes: RGB ->
nearest xterm 256-color palette entry (colour_find_rgb maps to closest 6x6x6 cube / grayscale
ramp); if the outer terminal has <256 colors, further down to 16. The app still wrote RGB;
the user sees an approximation. tmux source literally: "Not a 24-bit terminal? Translate to
256-colour palette." So cmd-art's `\e[38;2;...m` output is never wrong on the wire — it just
gets flattened by tmux when RGB isn't advertised. Fix is config, not code.
Sources: tty.c, colour.c, https://github.com/tmux/tmux/issues/299

### Verify
```sh
# outside tmux
echo "$TERM"
printf '\033[48;2;255;0;0m  \033[48;2;0;255;0m  \033[48;2;0;0;255m  \033[0m\n'
# inside tmux
echo "$TERM $COLORTERM"
tmux display -p '#{client_termname} #{client_termfeatures}'   # look for RGB in features
tmux info | grep -E 'RGB|Tc|setrgb|colors'
tmux showenv -g COLORTERM
printf '\033[48;2;255;0;0m  \033[48;2;0;255;0m  \033[48;2;0;0;255m  \033[0m\n'
```
Three distinct color blocks = truecolor working. Banding/identical blocks = degraded.
Sources: FAQ https://github.com/tmux/tmux/wiki/FAQ#how-do-i-use-rgb-colour ,
man https://man7.org/linux/man-pages/man1/tmux.1.html , ArchWiki https://wiki.archlinux.org/title/Tmux

---

## 2. ALTERNATE SCREEN INSIDE A PANE

- Each tmux pane is a separate pseudo-terminal with its OWN virtual terminal state,
  INCLUDING its own alternate-screen buffer. tmux maintains alt-screen state per pane.
- App emits smcup/rmcup; tmux switches THAT pane's virtual terminal to/from its alt screen
  IF the `alternate-screen` window option is on (default on).
  - Modern smcup/rmcup: `\e[?1049h` / `\e[?1049l`  (1049 = save cursor + switch + clear)
  - Older:              `\e[?47h`  / `\e[?47l`
  - hex: 1049h = 1b 5b 3f 31 30 34 39 68 ; 1049l = ...6c
- `set -g alternate-screen on` (default). With `off`, tmux does NOT let pane programs use
  smcup/rmcup — the app's alt-screen output stays on the normal buffer (art would scroll into
  scrollback instead of getting a clean canvas).
- Scrollback interaction: while an app is in alt screen, lines are NOT added to normal pane
  history. This is the FAQ "why can't I scroll back after vim/less" — expected, not a bug.
- Nesting terminal -> tmux -> app (or -> nested tmux -> app) works when each layer has the
  right TERM + terminfo. tmux puts the OUTER terminal in smcup on client start, rmcup on stop,
  and manages pane alt screens internally. Breakage: wrong TERM, missing terminfo, or configs
  that delete smcup/rmcup, e.g. AVOID `set -g terminal-overrides '*:smcup@:rmcup@'`.
- capture-pane and alt screen: plain capture-pane captures whatever is CURRENTLY displayed
  (alt or normal). `-a` explicitly targets the alternate screen (history unavailable there);
  `-a` errors if no alt screen exists unless `-q`.

App responsibility (cmd-art already does most of this in core.py play()):
- smcup on start, rmcup on exit, restore on ANY exit path.
- You cannot trap SIGKILL — after a hard kill the pane may stay in alt screen until reset
  (`printf '\033[?1049l'` or `reset` / `tput rmcup`).
Sources: man (alternate-screen, capture-pane -a), nevis mirror,
xterm ctlseqs https://invisible-island.net/xterm/ctlseqs/ctlseqs.html

---

## 3. RESIZE / SIGWINCH

### Mechanism
- Pane = separate pty. Kernel stores size as `struct winsize {ws_row,ws_col,ws_xpixel,ws_ypixel}`.
  `TIOCGWINSZ` gets, `TIOCSWINSZ` sets. On size change, kernel sends SIGWINCH to the
  foreground process group of that pty.
- tmux resize path: outer client resizes -> tmux updates window/layout/pane geometry ->
  tmux sets the pane pty winsize -> kernel delivers SIGWINCH to pane's fg process group ->
  app must re-query via ioctl(TIOCGWINSZ) / os.get_terminal_size(fd) / shutil.get_terminal_size().
- SIGWINCH carries NO dimensions — it's just "size changed, re-query now." Signals coalesce,
  so treat as a dirty flag, not one-signal-per-step.
- Triggers: client resize, split-window, resize-pane, zoom toggle (-Z), layout change,
  another client attaching at a different size (see window-size below).

### Options that change effective pane size
- `aggressive-resize on` (window opt): resize window to smallest/largest session for which it
  is current window, not just attached session. Man: good for full-screen SIGWINCH-aware apps,
  poor for shells.
- `window-size largest|smallest|manual|latest` (window opt): which client size wins when
  multiple clients attach. `manual` uses `default-size`; `resize-window` forces manual.
  `latest` = most-recently-active client.
- `default-size XxY`; `resize-window -x -y`; `refresh-client -C WxH` (control mode).
- tmux 3.3+ added a `window-resized` hook (fires when window actually resized; "may be later
  than the client resize"). Source: tmux CHANGES.

### What breaks if you CACHE width/height once (THIS IS OUR BUG)
- draw past new right edge -> wrap + garbage
- shrink -> stale chars/borders left outside redrawn region
- cursor addressing hits wrong cells
- boxes / progress bars / double-width / border joins misalign
- alt-screen apps look partially reflowed / corrupted

### Correct loop
```
startup:  smcup (\e[?1049h) if wanted; hide cursor (\e[?25l); query size
SIGWINCH: resize_dirty = True
each frame (or when dirty): re-query size; if changed -> full clear (\e[2J) + home (\e[H) + redraw
exit:     show cursor (\e[?25h); rmcup (\e[?1049l)
```
```python
import os, signal, sys
resized = True
def on_winch(signum, frame):
    global resized; resized = True
signal.signal(signal.SIGWINCH, on_winch)   # Unix only
def size():
    ts = os.get_terminal_size(sys.stdout.fileno()); return ts.columns, ts.lines
```

### Windows caveat (dev box)
- Python `signal.SIGWINCH` is Unix-only; `signal.signal()` on Windows rejects it. On
  ConPTY, resize is host-driven via `ResizePseudoConsole(HPCON, COORD)`. So: guard the
  SIGWINCH handler with `hasattr(signal,'SIGWINCH')`; on Windows fall back to polling
  `shutil.get_terminal_size()` each frame.
Sources: man7 tmux(1), man7 TIOCSWINSZ(2const),
Python signal docs https://docs.python.org/3/library/signal.html ,
MS ResizePseudoConsole https://learn.microsoft.com/en-us/windows/console/resizepseudoconsole

---

## 4. display-popup AND split-window (launch + sizing)

### display-popup (tmux >= 3.2; alias `popup`)
```
display-popup [-BCEkN] [-b border-lines] [-c target-client] [-d start-directory]
  [-e VAR=val] [-h height] [-s style] [-S border-style] [-t target-pane]
  [-T title] [-w width] [-x position] [-y position] [shell-command [args...]]
```
- Popup is a per-client rectangular OVERLAY drawn OVER panes. It is NOT a pane and does NOT
  participate in the layout.
- It runs the command in its OWN terminal context sized to the popup dimensions. The app must
  read ITS OWN size from inside; do NOT assume underlying pane size, and do NOT derive size
  from the tmux `-w`/`-h` args (borders/status/defaults make that brittle).
- The app cannot resize the popup from inside (no app-driven window-resize escape); tmux owns
  popup geometry. Effectively fixed-size for the app's lifetime.
- `-w`/`-h`: cols/rows OR percentage (`80%`); default = HALF terminal size if omitted.
- `-x`/`-y`: `C`=center; `-x R`=right; `P`=pane bottom-left; `M`=mouse; `-y S`=status-relative;
  or numeric.
- `-E` close when command exits; `-EE` close only on success (leave open on failure = debug);
  `-k` any key dismisses after exit (else Esc/C-c); `-N` cancels a prior -E/-EE/-k.
- `-B` no border; `-b` border-lines; `-s` popup style; `-S` border style; `-T` title;
  `-d` start dir; `-e VAR=val` (repeatable); `-C` close any popup on the client.
- Inside an existing popup most placement flags are ignored (R5 note).
- capture-pane CANNOT capture popup contents (popup is not a pane). Confirmed.

```sh
tmux display-popup -E -w 80 -h 24 -x C -y C 'python3 ./anim.py'   # fixed 80x24 centered
tmux display-popup -E -w 80% -h 70% -x C -y C 'python3 ./anim.py'
```

### split-window
```
split-window [-bdefhIkPvZ] [-c dir] [-e VAR=val] [-F format] [-l size]
  [-p percentage] [-t target] [shell-command [args...]]
```
- `-h` L/R split (`-l` = columns); `-v` top/bottom (`-l` = rows); default `-v`.
- `-l size`: rows (v) or cols (h); may be `NN%`. Prefer `-l NN%` over deprecated `-p NN`.
- `-b` before/left/above; `-f` full width/height; `-d` don't focus; `-P` print pane info;
  `-F` format; `-c` start dir; `-e` env; `-Z` zoom; `-k` keep exited pane visible.
```sh
tmux split-window -v -l 24  'python3 ./anim.py'   # 24 rows
tmux split-window -h -l 80  'python3 ./anim.py'   # 80 cols
tmux split-window -v -l 30% 'python3 ./anim.py'
```

### resize-pane
```
resize-pane [-DLMRTUZ] [-t target] [-x width] [-y height] [adjustment]
```
- `-L/-R/-U/-D` by adjustment (default 1); `-x`/`-y` absolute (num or %); `-Z` toggle zoom;
  `-M` mouse; `-T` trim lines below cursor.
```sh
tmux resize-pane -t %3 -x 80 -y 24
tmux resize-pane -Z
```

Rule for animation apps: pick popup (fixed size, overlay, not scrapeable) OR split
(participates in layout, scrapeable, resizable). Either way the app reads real size and
full-redraws on resize.
Sources: man7 tmux(1); popup intro https://github.com/tmux/tmux/issues/2592 ; tmux CHANGES.

---

## 5. capture-pane FOR AGENT SCRAPING (drive-tui)

```
capture-pane [-aepPqCJMN] [-b buffer-name] [-S start] [-E end] [-t target-pane]
```
Man-verified flag semantics (WebFetch of man7 tmux(1), 2026-07-07):
- `-p` : print to stdout (else saved to a paste buffer; read with `show-buffer -b name`).
- `-e` : include escape sequences for text AND background attributes (SGR in output).
- `-C` : also escape non-printable chars as octal `\xxx`.
- `-T` : "ignores trailing positions that do not contain a character" (TRIM trailing).
- `-N` : "preserves trailing spaces at each line's end" (PRESERVE trailing).
- `-J` : "preserves trailing spaces AND joins any wrapped lines; -J implies -T".
         (Verified: -J both preserves trailing spaces and joins wraps, and implies -T.)
- `-S start` / `-E end`: 0 = first visible line; negatives = history; `-S -` = start of
  history; `-E -` = end of visible pane. Default range = visible pane only.
- `-a` : capture the ALTERNATE screen; history NOT accessible; errors if no alt screen
         unless `-q`. (CORRECTION: `-a` is NOT "all buffers".)
- `-t target-pane` : select pane.

What the agent actually gets:
- Plain `-p`: visible grid as text, NO color. Wrapped physical rows stay separate unless -J.
  Trailing whitespace not reliably preserved unless -N or -J.
- `-p -J`: clean logical lines (wraps joined) -> best for TEXT parsing / classify().
- `-p -e -J`: embedded SGR escapes -> for COLOR verification; strip `\x1b\[[0-9;:]*m` for text.
- capture-pane captures whatever is currently displayed (alt or normal); `-a` forces alt.
- Popup contents are NOT capturable.
- Cursor position is NOT in the output. Get it separately:
  `tmux display-message -p -t %1 '#{cursor_x} #{cursor_y}'`.

Recommended drive-tui scrape calls:
```sh
tmux capture-pane -p -J -t "$PANE"                 # clean text for classify/explain
tmux capture-pane -p -J -S - -E - -t "$PANE"       # full history through visible end
tmux capture-pane -p -e -J -t "$PANE"              # keep color to verify a themed frame
tmux display-message -p -t "$PANE" '#{cursor_x} #{cursor_y}'   # cursor
```
Note: our smartcli_core uses pyte over pywinpty directly; capture-pane is the tmux-native
equivalent an EXTERNAL agent would use to scrape a pane driven by our tools. Same discipline:
join wraps + strip SGR for text; keep -e only when checking colors.
Sources: man7 tmux(1) capture-pane + WebFetch verification.

---

## 6. COMMON FAILURE MODES (exact enable/disable pairs)

For EACH: cause -> exact escape pair -> fix. A well-behaved app traps EXIT/INT/TERM/HUP and
restores everything (cannot trap KILL).

1) COLORS WRONG / washed out
   Cause: wrong default-terminal, or outer RGB not advertised -> tmux quantizes to 256/16.
   Fix (config, section 1). Not an app bug.

2) BOX-DRAWING -> mojibake `lqqqk` / `x` / `q`
   Cause: ACS (DEC line-drawing) vs UTF-8 mismatch.
     `\e(0` = designate DEC Special/Line Drawing set; `\e(B` = back to USASCII.
     In ACS: q=horizontal, x=vertical, l/m/k/j=corners. If terminal/locale/tmux/terminfo
     disagree you see literal q/x/lqqqk.
   Fix: UTF-8 locale (`export LANG=en_US.UTF-8; export LC_ALL=en_US.UTF-8`), start `tmux -u`
   (tmux -u asserts UTF-8), and PREFER real UTF-8 box chars over ACS. cmd-art should emit
   Unicode box chars (U+2500 etc.), never ACS, and never rely on `\e(0`.
   Sources: xterm ctlseqs; SO https://stackoverflow.com/questions/8483798 ;
   FAQ https://github.com/tmux/tmux/wiki/FAQ#how-do-i-use-utf-8

3) CURSOR LEFT HIDDEN after exit
   Cause: sent `\e[?25l` (DECTCEM hide / civis), didn't restore on exit/crash.
     hide `\e[?25l`  show `\e[?25h`
   Fix: always `printf '\033[?25h'` on every exit path; trap EXIT INT TERM HUP.

4) MOUSE MODE LEAKING (clicks emit garbage in shell afterwards)
   Cause: enabled mouse reporting, didn't disable on exit.
     `\e[?1000h/l` normal   `\e[?1002h/l` button-event   `\e[?1003h/l` any-event
     `\e[?1006h/l` SGR mouse   `\e[?1004h/l` focus in/out
     (SGR reports look like `\e[<b;x;yM` press / `...m` release.)
   Fix: disable all on exit: `printf '\033[?1000l\033[?1002l\033[?1003l\033[?1006l\033[?1004l'`.
   Note: cmd-art does NOT need mouse — simplest fix is to never enable it. tmux `mouse on`
   means tmux ALSO grabs mouse (all-or-nothing from tmux's view).
   Sources: xterm ctlseqs; tmux issue https://github.com/tmux/tmux/issues/2116

5) LEFTOVER CHARS / RESIZE CORRUPTION
   Cause: cached size / partial redraw (section 3).
     `\e[2J` clear  `\e[H` home  `\e[K` clear-to-EOL  `\e[0m` reset SGR
   Fix: re-query size on SIGWINCH, full clear + redraw on change.

6) CURSOR-KEYS / KEYPAD MODE LEAKING
     `\e[?1h/l` DECCKM app/normal cursor keys ; `\e=`/`\e>` DECKPAM/DECKPNM keypad
   Fix: restore on exit if you ever set them. cmd-art shouldn't set these — avoid.
   Sources: xterm ctlseqs; MS VT https://learn.microsoft.com/en-us/windows/console/console-virtual-terminal-sequences

### Canonical teardown (superset; a well-behaved TUI runs this on trap)
```sh
cleanup() {
  printf '\033[0m'                                  # reset SGR
  printf '\033[?25h'                                # show cursor
  printf '\033[?1000l\033[?1002l\033[?1003l\033[?1006l'  # mouse off
  printf '\033[?1004l'                              # focus reporting off
  printf '\033[?2004l'                              # bracketed paste off
  printf '\033[?1l'                                 # normal cursor keys
  printf '\033>'                                    # normal keypad
  printf '\033[?1049l'                              # leave alt screen (if used)
}
trap cleanup EXIT INT TERM HUP
```
Prefer terminfo names (smcup/rmcup, civis/cnorm, smkx/rmkx, sgr0) via tput over hardcoded
xterm escapes when you want portability beyond xterm-compatibles.

---

## 7. AUDIT OF OUR CURRENT CODE (what's already right / what's missing)

Files: skills/cmd-art/fx/core.py (play loop), skills/cmd-art/fx/cli.py (ctx_factory).

ALREADY CORRECT in core.py play():
- enters alt screen (\e[?1049h), hides cursor (\e[?25l), NOWRAP, CLEAR once, HOME+redraw each
  frame (flicker-free). Enter is INSIDE try; finally always restores RESET/WRAP/SHOW/ALT_LEAVE.
- No-TTY degrade: single plain frame, no alt buffer.
- Never enables mouse / cursor-keys / keypad (so no leak risk there) — GOOD.

MISSING / TO FIX:
- [core.py] finally only guards KeyboardInterrupt. tmux `kill-pane` / `respawn-pane -k` send
  SIGTERM (also SIGHUP on detach). Python's default SIGTERM handler exits WITHOUT running
  `finally` -> alt screen + hidden cursor LEAK. Install SIGTERM/SIGHUP handlers that raise
  (or set a stop flag) so finally runs. (Cannot catch SIGKILL — document that.)
- [cli.py:72-77] width/height resolved ONCE and captured in ctx_factory closure. On pane
  resize the animation keeps drawing at the old size -> wrap/garbage/stale borders (section 3).
  Fix: install a SIGWINCH handler (guarded by hasattr(signal,'SIGWINCH') for Windows), set a
  dirty flag, re-read shutil.get_terminal_size() in the loop, and re-CLEAR + rebuild ctx on
  change. On Windows, poll size each frame instead.
- cmd-art should emit only UTF-8 box chars (already the case in show.py sep U+2502), never ACS.

---

## 8. SOURCE URLS
- tmux man: https://man7.org/linux/man-pages/man1/tmux.1.html
- tmux FAQ RGB: https://github.com/tmux/tmux/wiki/FAQ#how-do-i-use-rgb-colour
- tmux FAQ UTF-8: https://github.com/tmux/tmux/wiki/FAQ#how-do-i-use-utf-8
- tmux popup intro: https://github.com/tmux/tmux/issues/2592
- tmux mouse-leak issue: https://github.com/tmux/tmux/issues/2116
- tmux RGB-degrade issue: https://github.com/tmux/tmux/issues/299
- tmux source (color/degrade): tty-term.c, tty.c, colour.c (raw.githubusercontent.com/tmux/tmux/master/)
- xterm ctlseqs: https://invisible-island.net/xterm/ctlseqs/ctlseqs.html
- box-drawing SO: https://stackoverflow.com/questions/8483798/tmux-borders-displayed-as-x-q-instead-of-lines
- ArchWiki tmux: https://wiki.archlinux.org/title/Tmux
- Python signal (SIGWINCH Unix-only): https://docs.python.org/3/library/signal.html
- MS ResizePseudoConsole: https://learn.microsoft.com/en-us/windows/console/resizepseudoconsole
- MS VT sequences: https://learn.microsoft.com/en-us/windows/console/console-virtual-terminal-sequences
