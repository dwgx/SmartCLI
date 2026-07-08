# ANSI/VT SGR Color

**Statement:** Color and text attributes are set with SGR (Select Graphic Rendition) escape sequences; 24-bit truecolor and 256-color are the two palettes worth targeting.

**Exact escape sequences (ESC = 0x1b = `\033` = `\e` = `\x1b`):**
```
24-bit fg:   \e[38;2;R;G;Bm      (R,G,B 0..255)      hex: 1b 5b 33 38 3b 32 3b ...
24-bit bg:   \e[48;2;R;G;Bm
256 fg:      \e[38;5;Nm
256 bg:      \e[48;5;Nm
reset SGR:   \e[0m               (always reset at line/frame end)

256-color palette map:
  0..15    = system colors
  16..231  = 6x6x6 cube:  N = 16 + 36*r + 6*g + b   (r,g,b in 0..5)
             xterm component value = 0 if c==0 else 55 + 40*c
  232..255 = grayscale ramp:  gray = 8 + 10*(N-232)
```
Efficiency: emit a color escape only when it CHANGES between adjacent cells (SGR run-length) to cut output size dramatically.

**Source:** https://github.com/fnky/ANSI.md (also xterm ctlseqs https://invisible-island.net/xterm/ctlseqs/ctlseqs.html ; MS VT sequences https://learn.microsoft.com/en-us/windows/console/console-virtual-terminal-sequences )

**See also:** [[cell-grid-model]], [[truecolor-passthrough-tmux]], [[flicker-free-rendering]], [[box-drawing-glyphs]], [[cursor-and-screen-control]]
