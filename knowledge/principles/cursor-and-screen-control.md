# Cursor and Screen Control (VT sequences)

**Statement:** Cursor visibility, positioning, screen clearing, and the alternate screen buffer are all driven by VT/xterm control sequences; a well-behaved TUI must restore every mode it sets on exit.

**Exact escape sequences:**
```
hide cursor:        \e[?25l          show cursor:     \e[?25h     (DECTCEM / civis-cnorm)
alternate screen:   \e[?1049h        leave:           \e[?1049l   (1049 = save cursor+switch+clear)
older alt screen:   \e[?47h  / \e[?47l
cursor home:        \e[H
absolute move:      \e[{row};{col}H
clear whole screen: \e[2J
clear to EOL:       \e[K
DEC line-drawing:   \e(0  (designate)   \e(B  (back to USASCII)
cursor keys app:    \e[?1h / \e[?1l   (DECCKM)
keypad app/normal:  \e=  /  \e>        (DECKPAM / DECKPNM)
mouse (normal):     \e[?1000h/l    button-event: \e[?1002h/l   any-event: \e[?1003h/l
mouse SGR:          \e[?1006h/l    focus in/out: \e[?1004h/l   bracketed paste: \e[?2004h/l
```
Canonical teardown (run on trap EXIT INT TERM HUP; cannot trap SIGKILL):
```sh
printf '\033[0m\033[?25h\033[?1000l\033[?1002l\033[?1003l\033[?1006l\033[?1004l\033[?2004l\033[?1l\033>\033[?1049l'
```
Windows: enable ENABLE_VIRTUAL_TERMINAL_PROCESSING so escapes work in classic conhost (Windows Terminal handles them natively).

**Source:** https://invisible-island.net/xterm/ctlseqs/ctlseqs.html (xterm ctlseqs; teardown superset + failure modes from project research R6 §6; Windows VT https://learn.microsoft.com/en-us/windows/console/console-virtual-terminal-sequences )

**See also:** [[ansi-sgr-color]], [[flicker-free-rendering]], [[tmux-alternate-screen]], [[resize-sigwinch-handling]], [[box-drawing-glyphs]]
