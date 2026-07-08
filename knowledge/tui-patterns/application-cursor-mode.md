# Application Cursor Mode (DECCKM)

Many TUIs (vim, readline apps) switch arrow keys to the SS3 encoding; if arrows do nothing, the app is in DECCKM and you must resend them as SS3.

- App turns DECCKM on by emitting `\x1b[?1h`; off with `\x1b[?1l`. Watch the output stream for these.
- Normal cursor mode (CSI): Up `\x1b[A` Down `\x1b[B` Right `\x1b[C` Left `\x1b[D`.
- Application cursor mode (SS3): Up `\x1bOA` Down `\x1bOB` Right `\x1bOC` Left `\x1bOD`.

Rule: if arrow navigation has no effect, switch encoding (CSI ↔ SS3) and retry. Detect the mode by watching for `ESC[?1h` / `ESC[?1l` rather than guessing.

**Source:** https://invisible-island.net/xterm/ctlseqs/ctlseqs.html

**See also:** [[key-encoding-reference]], [[alternate-screen-detection]], [[list-menu-navigation]]
