# tmux capture-pane

`tmux capture-pane` lets tmux do the terminal emulation and hands you an already-rendered pane, optionally SGR-annotated — a cheap alternative to embedding a full emulator.

Flags (`tmux capture-pane`):
```
-p   print to stdout
-e   include SGR escape sequences
-a   capture alternate screen
-S start / -E end   line range (0=first visible, negative=history, - = extremes)
-J   join wrapped lines
-N   keep trailing spaces
-T   ignore trailing empty
-C   escape non-printables as octal
-M   capture pane-mode (copy mode) screen
-q   quiet errors
```

Cursor / buffer via format string:
```
tmux display-message -p '#{cursor_x},#{cursor_y},#{alternate_on}'
```
`alternate_on` = 1 when the alternate screen is active (a full-screen TUI is running). So `-e` gives SGR-annotated text and `-a` grabs the alternate screen without embedding a VT emulator.

> Canonical flag reference: `principles/tmux-capture-pane.md` (fullest, man-verified). Sibling angle: `agent-eng/tmux-capture-pane.md` (ground-truth scrape for agent driving). This entry is the "let tmux do the emulation" alternative-to-embedding-an-emulator angle.

**Source:** https://man7.org/linux/man-pages/man1/tmux.1.html

**See also:** [[emulator-libraries]], [[alternate-screen-detection]], [[screen-snapshot-capture]]
