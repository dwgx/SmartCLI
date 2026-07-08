# Pattern B — Fuzzy Search / Filter (fzf-style)

Recognize an incremental fuzzy finder by its prompt line + live match-count + pointer, and drive it by typing enough of a distinctive substring to narrow `X/Y` to a small set, then Enter.

### Recognition
- A **prompt line** `> ` (default `--prompt`); the typed query appears after it.
- An **info/match-count line** `X/Y` (matched/total, from FZF_MATCH_COUNT / FZF_TOTAL_COUNT) at the left end of a horizontal separator (`─` unicode / `-` with `--no-unicode`).
- A **pointer** on the current item: `▌` (unicode) or `>` (`--no-unicode`).
- A **multi-select marker**: `┃` (unicode) or `>` (`--no-unicode`) on chosen rows.
- Layout: `default` = list rises from bottom, prompt/info at bottom; `reverse` = prompt/info at top; `reverse-list` = list at top, prompt at bottom.
- Behavioral tell: typing a char narrows the list live and the `X/Y` count drops.

### Drive (fzf default binds)
- Type query: literal chars; list filters after each byte.
- Down: Down `\x1b[B`, `ctrl-j` (0x0a), `ctrl-n` `\x0e` (down-match; remapped to next-history when `--history` set).
- Up: Up `\x1b[A`, `ctrl-k` 0x0b, `ctrl-p` `\x10` (up-match; history-remapped as above).
- Accept: Enter `\r`.
- Toggle multi-select: Tab `\t` (`toggle+down`), Shift-Tab `\x1b[Z` (`toggle+up`).
- Abort: Ctrl-C `\x03`, Ctrl-G `\x07`, Ctrl-Q `\x11`, or Esc `\x1b`.
- Clear query: Ctrl-U `\x15`; backspace `\x7f`.

Strategy: type enough of the distinctive substring that `X/Y` shows a small `Y` (ideally 1), verify the pointer is on the desired row, then Enter. For multiple: Tab each, then Enter.

### Done
fzf exits (process ends, alt screen leaves), chosen line(s) print to stdout / are consumed by the calling command, shell prompt returns. Abort keys exit non-zero with no selection. Recognize completion: the fuzzy UI (prompt + `X/Y` + pointer) disappears from the snapshot.

**Source:** fzf man page — https://man7.org/linux/man-pages/man1/fzf.1.html (mined via WebFetch of man/man1/fzf.1)

**See also:** [[list-menu-navigation]], [[key-encoding-reference]], [[verify-movement-step-by-step]], [[alternate-screen-detection]]
