# Application Cursor Keys (DECCKM, mode 1)

**Statement:** When a TUI enables DECCKM, arrow keys switch from CSI encoding to SS3 encoding — the #1 arrow-key driving bug.

**Detail / exact escape sequences:**
- Enable: `CSI ?1h` = `ESC [ ? 1 h`
- With DECCKM enabled, arrows send **SS3**: Up = `ESC O A` (`ESC O A`), not the default **CSI** form `ESC [ A`.
- So: sending `ESC[A` to a program that has enabled DECCKM fails; you must send `ESC O A`.

CSI = `ESC [`; SS3 = `ESC O`.

**Source:** https://xorg.freedesktop.org/archive/X11R7.0/doc/ctlseqs.txt and https://invisible-island.net/xterm/ctlseqs/ctlseqs.html

**See also:** [[hunt-the-esc-byte]], [[tmux-send-keys-literal]], [[alternate-screen-buffer]]
