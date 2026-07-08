# Cell Width Measurement (wcwidth / UAX #11)

**Statement:** Never use `len(s)` for terminal layout; measure display width in cells via `wcwidth`/`wcswidth` (UAX #11 East Asian Width), because wide chars take 2 cells and controls/zero-width take 0.

**Real rules / API:**
```
UAX #11 East_Asian_Width classes:  F/W -> 2 cells ;  Na/H/N/A -> 1  (A "ambiguous" configurable to 2).

Python wcwidth:
  wcwidth(ch): ASCII fast path 1; C0/C1 controls -1; zero-width table 0; wide/fullwidth 2;
               ambiguous 1 (or 2 if ambiguous_width=2); else 1.
  wcswidth(s): -1 if any control char; U+200D ZWJ = 0 (zeros following emoji component);
               U+FE0F VS16 can widen narrow symbol to 2; regional-indicator pair = one flag width 2;
               Fitzpatrick modifiers add 0; grapheme cluster width currently capped at 2.
  STABLE (SemVer-frozen): wcwidth, wcswidth ONLY. Other helpers are newer and may evolve.

Rich rich.cells: cell_len(text), set_cell_size(text,total) (crop/pad exact), chop_cells, split_graphemes.
  Controls (<32, 0x7F..0x9F) -> 0. Splitting never bisects a double-width cell (spaces substituted).

Engine policy: display_width(s) = max(wcswidth(s), 0); slice by GRAPHEME clusters accumulating cell
widths, not by Python indices; reserve 1 cell for ellipsis; strip/parse ANSI as zero-width before measuring.

Critical test strings:
  "é"=1  "界"=2  "♀"=1  "♀️"=2  "👩‍💻"=2  "🇯🇵"=2  "\x1b[31mred" -> measure "red"=3
```

**Source:** https://www.unicode.org/reports/tr11/ (UAX #11; wcwidth spec/API https://wcwidth.readthedocs.io/en/latest/specs.html + https://wcwidth.readthedocs.io/en/latest/api.html ; Rich cells https://github.com/Textualize/rich/blob/master/rich/cells.py — all in project research R7 §4)

**See also:** [[cell-grid-model]], [[box-model-on-cell-grid]], [[box-drawing-glyphs]], [[sub-cell-resolution]], [[fractional-space-distribution]]
