# Hunt the ESC byte

**Statement:** Grep for the ESC byte in its various encodings to locate ANSI/color/keybinding/layout constants in a minified TUI bundle.

**Detail / real params:**
- ESC = `0x1B`.
- In JS bundles it appears as a literal ESC char, `\x1b`, `\033` (octal), or an embedded literal.
- CSI = `ESC [`; SS3 = `ESC O`.

Search these forms to find the ANSI escape / color / keybinding / layout constants inside a minified Ink/React TUI.

**Source:** https://invisible-island.net/xterm/ctlseqs/ctlseqs.html

**See also:** [[ripgrep-binary-search]], [[strings-utf16le]], [[node-sea-blob]], [[application-cursor-keys-deckm]], [[alternate-screen-buffer]]
