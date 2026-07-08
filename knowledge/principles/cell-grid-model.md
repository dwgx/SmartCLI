# Cell Grid Model

**Statement:** A terminal is a `W x H` grid of character cells, each holding `{char, fg_rgb, bg_rgb, attr}`; all rendering resolves to writing cells, never pixels.

**Real params / model:**
```
Terminal model: W columns x H rows.
Each cell = { ch, fg_rgb, bg_rgb, attr }  (attr = bold/dim/italic/underline/reverse...)
Frame t = elapsed seconds OR integer frame index.
Layout is done in INTEGER cells; keep fractional (fr/ratio) intermediates as
Fraction and floor CUMULATIVE offsets at placement time to avoid drift.
Wide chars occupy 2 horizontally adjacent cells (see cell-width-measurement).
A Buffer = 2D array of Cells + blit(child_buffer, x, y) that respects wide-cell occupancy.
Root serializes Buffer -> ANSI once (SGR run-length, skip control cells).
```

**Source:** https://textual.textualize.io/guide/layout/ (integer `Size(cols, rows)` grid; build-ready cell/Buffer model summarized in project research R7 §1/§7, terminal `{ch,fg,bg,attr}` model in R1)

**See also:** [[cell-width-measurement]], [[box-model-on-cell-grid]], [[sub-cell-resolution]], [[terminal-cell-aspect-ratio]], [[flicker-free-rendering]], [[ansi-sgr-color]]
