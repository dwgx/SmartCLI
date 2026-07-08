# Terminal Emulator Libraries

Per-stack libraries for rendering a PTY byte stream into an observable screen grid; PTY-spawn libraries do not render a full screen and must be paired with an emulator.

| Stack | Library | Role |
|---|---|---|
| Python | `pyte` | in-memory VTxxx emulator. `Screen` = matrix w/ attrs; `Stream` parses escapes; `screen.cursor.x/.y`; `screen.display` = rendered text lines |
| Python | `pexpect` / `ptyprocess` | spawn/control under PTY; does NOT render full screen — pair with pyte |
| Node | `node-pty` | PTY spawn + byte IO |
| Node | `@xterm/headless` | headless terminal state; `buffer.active.cursorX/cursorY`, `.type` = normal/alternate, `getLine()` |
| Go | `hinshun/vt10x` | VT10x emulation backend |
| Shell | `tmux capture-pane` | let tmux emulate; capture pane (see [[tmux-capture-pane]]) |
| Shell | GNU `screen hardcopy` | dump displayed screen (+scrollback with `-h`) |

pexpect example: `child.expect([r'[$#] ', pexpect.TIMEOUT, pexpect.EOF], timeout=0.5)`; `expect_exact()` for literal strings. For screen-oriented apps `expect()` alone is insufficient — pair with snapshot stability, since visible state is assembled via cursor moves/overwrites.

**Source:** https://pyte.readthedocs.io/en/0.4.1/ , https://pexpect.readthedocs.io/en/stable/api/pexpect.html , https://github.com/microsoft/node-pty , https://xtermjs.org/docs/api/terminal/interfaces/ibuffer/ , https://www.npmjs.com/package/@xterm/headless , https://pkg.go.dev/github.com/hinshun/vt10x , https://man7.org/linux/man-pages/man1/screen.1.html

**See also:** [[screen-snapshot-capture]], [[tmux-capture-pane]], [[quiescence-detection]]
