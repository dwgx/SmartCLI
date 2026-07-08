# Screen Snapshot Capture

A PTY yields a byte stream, not a screen; to observe a rendered grid you feed the master bytes into a headless terminal emulator that maintains a rows×cols cell matrix.

Pipeline:
```
spawn child under PTY
  -> read master bytes
  -> decode UTF-8 + ANSI/VT100/xterm escapes
  -> feed headless emulator
  -> snapshot visible buffer
       (each cell: char, fg, bg, bold, dim, italic, underline,
        reverse, blink, hidden, strike, wide/continuation)
  -> cursor x/y from emulator state
```

A snapshot = the terminal grid of cells (char + fg/bg/bold/reverse/underline attrs) + cursor row/col + which buffer (normal/alternate) is active. Use a real VT parser, not regex: CSI can arrive as 8-bit `0x9b` and escapes split across reads.

**Source:** https://invisible-island.net/xterm/ctlseqs/ctlseqs.html

**See also:** [[emulator-libraries]], [[alternate-screen-detection]], [[snapshot-stability-hash]], [[quiescence-detection]], [[cursor-row-binding]]
