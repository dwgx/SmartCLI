# Box-Drawing Glyphs

**Statement:** Draw borders and rules with real Unicode box-drawing characters (U+2500..U+257F), never with DEC ACS line-drawing, so frames render correctly across terminals and inside tmux.

**Exact glyph table (role → single / rounded / heavy / double):**
```
horizontal  ─ 2500 | ─ 2500 | ━ 2501 | ═ 2550
vertical    │ 2502 | │ 2502 | ┃ 2503 | ║ 2551
top-left    ┌ 250C | ╭ 256D | ┏ 250F | ╔ 2554
top-right   ┐ 2510 | ╮ 256E | ┓ 2513 | ╗ 2557
bot-left    └ 2514 | ╰ 2570 | ┗ 2517 | ╚ 255A
bot-right   ┘ 2518 | ╯ 256F | ┛ 251B | ╝ 255D
tee-right   ├ 251C | ├ 251C | ┣ 2523 | ╠ 2560
tee-left    ┤ 2524 | ┤ 2524 | ┫ 252B | ╣ 2563
tee-down    ┬ 252C | ┬ 252C | ┳ 2533 | ╦ 2566
tee-up      ┴ 2534 | ┴ 2534 | ┻ 253B | ╩ 2569
cross       ┼ 253C | ┼ 253C | ╋ 254B | ╬ 256C
```
Rounded reuses light edges/junctions; only the four corners differ (arcs U+256D..U+2570).
Ellipsis truncation uses U+2026 (…): `set_cell_size(text, width-1) + "…"`.

Why NOT ACS: `\e(0` (DEC Special/Line Drawing) vs UTF-8 mismatch produces mojibake `lqqqk` / `x` / `q`. Emit real UTF-8 box chars and never rely on `\e(0`; use a UTF-8 locale and start `tmux -u`.

**Source:** https://www.unicode.org/charts/PDF/U2500.pdf (U+2500 chart; per-style glyph table from Rich box.py https://github.com/Textualize/rich/blob/master/rich/box.py , project research R7 §3; ACS mojibake failure mode + fix from research R6 §6.2, https://github.com/tmux/tmux/wiki/FAQ#how-do-i-use-utf-8 )

**See also:** [[cell-grid-model]], [[box-model-on-cell-grid]], [[cell-width-measurement]], [[cursor-and-screen-control]], [[sub-cell-resolution]]
