# 256-Color Cube & Grayscale

The 256-color palette encodes a 6x6x6 RGB cube plus a 24-step grayscale ramp, selected with `ESC[38;5;Nm` (foreground) / `ESC[48;5;Nm` (background).

- Color cube, indices 16..231: `index = 16 + 36*r + 6*g + b`, with `r,g,b ∈ 0..5`.
- Channel intensity per coordinate: levels `{0, 95, 135, 175, 215, 255}`, i.e. `component = coord==0 ? 0 : coord*40 + 55`.
- Grayscale, indices 232..255: `gray = 8 + 10*i`, with `i ∈ 0..23`.
- Indices 0..15 are the standard/bright ANSI colors.

**Source:** https://github.com/ThomasDickey/xterm-snapshots/blob/master/256colres.h and https://en.wikipedia.org/wiki/ANSI_escape_code#8-bit

**See also:** [[truecolor-24bit]], [[nearest-color-downgrade]]
