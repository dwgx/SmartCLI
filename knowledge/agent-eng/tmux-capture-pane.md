# tmux capture-pane flags

**Statement:** `capture-pane` snapshots ground-truth pane state, optionally with color and scrollback.

**Detail / real params:**
- `-p` — write capture to stdout.
- `-e` — include escape sequences for color and text attributes.
- `-S` / `-E` — start / end line of the scrollback range (`0` = first visible line, negative values reach into history).
- `-J` — join wrapped lines and preserve trailing spaces.

Recipe for a full colored snapshot including history: `tmux capture-pane -p -e -J -S -`.

> Canonical flag reference: `principles/tmux-capture-pane.md` (fullest, man-verified line-join/SGR-strip semantics). Sibling angle: `tui-patterns/tmux-capture-pane.md` (let tmux be the emulator, plus `#{alternate_on}` detection). This entry is the agent-driving / ground-truth-scrape angle.

**Source:** https://man.openbsd.org/tmux

**See also:** [[tmux-send-keys-literal]], [[tmux-control-mode]], [[alternate-screen-buffer]], [[terminal-bench]]
