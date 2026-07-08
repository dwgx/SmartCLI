# Alternate screen buffer

**Statement:** TUIs run in a separate cleared alt-screen buffer, so naive primary-buffer capture reads stale content.

**Detail / exact escape sequences:**
- `CSI ?1049h` = `ESC [ ? 1 0 4 9 h` — saves cursor and switches to the (cleared) alternate buffer.
- `CSI ?1049l` — restores: switch back to the primary buffer and restore cursor.
- Older variants: `?1047` and `?47`.

The alt buffer has its own scrollback; capture it (not the primary buffer) to read a running TUI's real state.

**Source:** https://invisible-island.net/xterm/ctlseqs/ctlseqs.html

**See also:** [[application-cursor-keys-deckm]], [[bracketed-paste]], [[tmux-capture-pane]], [[hunt-the-esc-byte]], [[tmux-alternate-screen]] (VT + per-pane semantics), [[alternate-screen-detection]] (detecting the switch in the byte stream)
