# tmux capture-pane (agent scraping)

**Statement:** An external agent scrapes a pane's contents with `capture-pane`; join wrapped lines and strip SGR for text parsing, keep escapes only when verifying color.

**Exact flags (man-verified):**
```
capture-pane [-aepPqCJMN] [-b buffer-name] [-S start] [-E end] [-t target-pane]
  -p : print to stdout (else saved to a paste buffer; read via show-buffer -b name).
  -e : include escape sequences (SGR) for text AND background attributes.
  -C : also escape non-printable chars as octal \xxx.
  -T : ignore trailing positions with no character (TRIM trailing).
  -N : preserve trailing spaces at each line's end.
  -J : preserve trailing spaces AND join wrapped lines; -J implies -T.
  -S start / -E end : 0 = first visible line; negatives = history; -S - = start of history;
       -E - = end of visible pane. Default range = visible pane only.
  -a : capture the ALTERNATE screen (history NOT accessible; errors if none unless -q).
       (NOT "all buffers".)
```
Recommended scrape calls:
```sh
tmux capture-pane -p -J -t "$PANE"                # clean text (wraps joined) for classify/explain
tmux capture-pane -p -J -S - -E - -t "$PANE"      # full history through visible end
tmux capture-pane -p -e -J -t "$PANE"             # keep SGR to verify a themed frame; strip \x1b\[[0-9;:]*m for text
tmux display-message -p -t "$PANE" '#{cursor_x} #{cursor_y}'   # cursor pos (NOT in capture output)
```
Notes: `-p` alone gives visible grid as text, NO color, wraps stay separate, trailing whitespace unreliable unless -N/-J. Popup contents are NOT capturable (a popup is not a pane).

> This is the canonical flag reference. Domain-specific siblings on the same tool: `agent-eng/tmux-capture-pane.md` (ground-truth scrape for agent driving) and `tui-patterns/tmux-capture-pane.md` (let tmux be the emulator + `#{alternate_on}` detection).

**Source:** https://man7.org/linux/man-pages/man1/tmux.1.html (capture-pane flag semantics, WebFetch-verified 2026-07-07 — project research R6 §5, R5 §B.5)

**See also:** [[tmux-alternate-screen]], [[tmux-launch-and-sizing]], [[truecolor-passthrough-tmux]], [[ansi-sgr-color]], [[cell-width-measurement]]
