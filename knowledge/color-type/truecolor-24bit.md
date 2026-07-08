# Truecolor (24-bit) ANSI

24-bit direct RGB color: each of foreground and background takes explicit R/G/B bytes (0..255).

- Foreground: `ESC[38;2;R;G;Bm`
- Background: `ESC[48;2;R;G;Bm`
- R, G, B each 0..255.
- Detect support via environment: `COLORTERM=truecolor` or `COLORTERM=24bit`.

**Source:** https://invisible-island.net/xterm/ctlseqs/ctlseqs.html and https://github.com/termstandard/colors#checking-for-colorterm

**See also:** [[256-color-cube]], [[nearest-color-downgrade]], [[color-interpolation]]
