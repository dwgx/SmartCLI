# Key Encoding Reference (bytes to WRITE to the PTY)

The bytes you write to the PTY master to simulate keypresses. Default Enter is CR `\r` (0x0d), not LF — raw-mode TUIs expect the terminal Enter sequence.

Anchors:
```
ESC=\x1b  CSI=\x1b[  SS3=\x1bO  CR=\r=0x0d  LF=\n=0x0a  DEL=\x7f  BS=\x08
```

| Key | Bytes | | Key | Bytes |
|---|---|---|---|---|
| Enter | `\r` 0x0d | | Tab | `\t` 0x09 |
| Shift-Tab | `\x1b[Z` | | Escape | `\x1b` |
| Space | 0x20 | | Backspace | `\x7f` (or `\x08`) |
| Ctrl-C | `\x03` | | Ctrl-D (EOF) | `\x04` |
| Ctrl-N | `\x0e` | | Ctrl-P | `\x10` |
| Ctrl-L (redraw) | `\x0c` | | Ctrl-U (kill line) | `\x15` |
| Ctrl-Z | `\x1a` | | | |

Arrows — normal cursor mode: Up `\x1b[A` Down `\x1b[B` Right `\x1b[C` Left `\x1b[D`.
Arrows — application cursor mode (DECCKM): Up `\x1bOA` Down `\x1bOB` Right `\x1bOC` Left `\x1bOD` (see [[application-cursor-mode]]).

Home `\x1b[H` (or `\x1bOH`, or `\x1b[1~`); End `\x1b[F` (or `\x1bOF`, or `\x1b[4~`).
Insert `\x1b[2~`; Delete `\x1b[3~`; PageUp `\x1b[5~`; PageDown `\x1b[6~`.
F1-F4 `\x1bOP \x1bOQ \x1bOR \x1bOS` (older `\x1b[11~..14~`); F5 `\x1b[15~` F6 `\x1b[17~` F7 `\x1b[18~` F8 `\x1b[19~` F9 `\x1b[20~` F10 `\x1b[21~` F11 `\x1b[23~` F12 `\x1b[24~`.
Modified keys add a param: `CSI 15;2~` = Shift-F5; `;2`=Shift `;3`=Alt `;5`=Ctrl `;6`=Shift+Ctrl.

**Source:** https://invisible-island.net/xterm/ctlseqs/ctlseqs.html , https://learn.microsoft.com/en-us/windows/console/console-virtual-terminal-sequences

**See also:** [[application-cursor-mode]], [[list-menu-navigation]], [[fuzzy-search-filter]], [[pager-navigation]], [[cursor-row-binding]]
