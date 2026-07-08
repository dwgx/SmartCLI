# Bracketed paste (mode 2004)

**Statement:** In bracketed-paste mode, pasted input is wrapped in marker sequences so programs can distinguish it from typed input.

**Detail / exact escape sequences:**
- `CSI ?2004h` = `ESC [ ? 2 0 0 4 h` — "Set bracketed paste mode, xterm."
- `CSI ?2004l` — reset.
- Paste is wrapped in `ESC[200~` ... `ESC[201~` (the exact wrapper wording was truncated in the source fetch — **verify the wrapper bytes before relying on them**).

**Source:** https://invisible-island.net/xterm/ctlseqs/ctlseqs.html

**See also:** [[alternate-screen-buffer]], [[application-cursor-keys-deckm]], [[hunt-the-esc-byte]]
