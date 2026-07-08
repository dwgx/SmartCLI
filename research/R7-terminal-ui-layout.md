# R7 — HTML/CSS-like Layout Engine + Web-style Widgets for the Terminal

> **Archived first-pass research** — superseded by [`../knowledge/sources/`](../knowledge/sources/); folded into [`../knowledge/principles/`](../knowledge/principles/README.md) + `skills/tui-ui`. See [`README.md`](README.md). Kept for provenance.


Research date: 2026-07-07. Method: 3 parallel codex live-web-search runs (--search, effort medium),
cross-checked against Rich/Textual source + docs + Unicode specs, plus a WebFetch verification of the
wcwidth public API. Goal: enable an AI to "design UIs like web pages" in a TUI.

Note on verification: wcwidth's extra functions (`width`, `iter_graphemes`, `wcstwidth`, `ljust`, etc.)
were confirmed real via https://wcwidth.readthedocs.io/en/latest/api.html — but only `wcwidth` and
`wcswidth` carry a SemVer stability guarantee; the rest are newer (0.3.0+/0.8.0+) and may evolve.

---

## Primary source URLs

Box model / layout / renderables:
- Textual styles (box model, border adds 2 rows/cols, padding order, margin collapse): https://textual.textualize.io/guide/styles/
- Textual layout guide: https://textual.textualize.io/guide/layout/
- Textual dock: https://textual.textualize.io/styles/dock/
- Textual box_model.py: https://github.com/Textualize/textual/blob/main/src/textual/box_model.py
- Textual widget.py (_get_box_model): https://github.com/Textualize/textual/blob/main/src/textual/widget.py
- Textual css/styles.py: https://github.com/Textualize/textual/blob/main/src/textual/css/styles.py
- Textual css/scalar.py (Scalar, Unit): https://github.com/Textualize/textual/blob/main/src/textual/css/scalar.py
- Textual _resolve.py (fr resolution): https://github.com/Textualize/textual/blob/main/src/textual/_resolve.py
- Textual _arrange.py (dock partition): https://github.com/Textualize/textual/blob/main/src/textual/_arrange.py
- MDN box model: https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Styling_basics/Box_model
- W3C CSS Grid (fr = flexible length): https://www.w3.org/TR/css-grid-1/

Rich renderable pipeline:
- Rich protocol (__rich__, __rich_console__, __rich_measure__): https://rich.readthedocs.io/en/stable/protocol.html
- Rich console.py (render, render_lines, _render_buffer): https://github.com/Textualize/rich/blob/master/rich/console.py
- Rich segment.py: https://github.com/Textualize/rich/blob/master/rich/segment.py
- Rich measure.py (Measurement.get): https://github.com/Textualize/rich/blob/master/rich/measure.py
- Rich style.py (Style.render -> ANSI SGR): https://github.com/Textualize/rich/blob/master/rich/style.py
- Rich markup docs: https://rich.readthedocs.io/en/stable/markup.html

Layout math / width:
- Rich _ratio.py (ratio_resolve / ratio_distribute / ratio_reduce): https://github.com/Textualize/rich/blob/main/rich/_ratio.py
- Rich layout.py (ColumnSplitter / RowSplitter): https://github.com/Textualize/rich/blob/main/rich/layout.py
- Rich cells.py (cell_len, set_cell_size, chop_cells, split_graphemes): https://github.com/Textualize/rich/blob/main/rich/cells.py
- Rich _wrap.py (divide_line word wrap): https://github.com/Textualize/rich/blob/main/rich/_wrap.py
- Unicode UAX #11 East Asian Width: https://www.unicode.org/reports/tr11/
- Unicode Box Drawing chart U+2500..U+257F: https://www.unicode.org/charts/PDF/U2500.pdf
- wcwidth spec: https://wcwidth.readthedocs.io/en/latest/specs.html
- wcwidth API: https://wcwidth.readthedocs.io/en/latest/api.html
- wcwidth source: https://github.com/jquast/wcwidth/blob/master/wcwidth/_wcwidth.py

Widgets:
- Rich box.py: https://github.com/Textualize/rich/blob/master/rich/box.py
- Rich panel.py: https://github.com/Textualize/rich/blob/master/rich/panel.py
- Rich padding.py: https://github.com/Textualize/rich/blob/master/rich/padding.py
- Rich table.py: https://github.com/Textualize/rich/blob/main/rich/table.py
- Rich progress.py + progress_bar.py: https://github.com/Textualize/rich/blob/main/rich/progress_bar.py
- Rich tree.py: https://github.com/Textualize/rich/blob/main/rich/tree.py
- Rich columns.py: https://github.com/Textualize/rich/blob/main/rich/columns.py
- Rich rule.py: https://github.com/Textualize/rich/blob/main/rich/rule.py
- Textual _progress_bar.py: https://github.com/Textualize/textual/blob/main/src/textual/widgets/_progress_bar.py
- Textual renderables/bar.py: https://github.com/Textualize/textual/blob/main/src/textual/renderables/bar.py
- Textual _tabs.py / _tabbed_content.py / _tree.py under: https://github.com/Textualize/textual/tree/main/src/textual/widgets
- pyfiglet: https://github.com/pwaller/pyfiglet

---

## 1. Box model on a cell grid

Treat the screen as an integer grid `Size(cols, rows)`. Four nested boxes (CSS order):
margin box (empty spacing outside) -> border box (glyph cells) -> padding box (blank/styled) -> content box.

```
outer_w = margin_l + border_l + padding_l + content_w + padding_r + border_r + margin_r
outer_h = margin_t + border_t + padding_t + content_h + padding_b + border_b + margin_b
```

Borders are CELLS, not strokes: each present side consumes exactly 1 cell. Textual docs state a border
"adds two rows and two columns". Padding order is CSS 4-tuple (top, right, bottom, left). Margins collapse
by taking the LARGER of adjacent margins (Textual behavior).

Default box-sizing in Textual is `border-box` (not the historical CSS `content-box`):
- border-box: given width IS the border box; content = width - gutter.
- content-box: given width is content; border box = content + gutter.
Where `gutter = padding + border` on each axis.

Textual internals (verbatim shape):
```python
class BoxModel(NamedTuple):
    width: Fraction   # content + padding + border
    height: Fraction
    margin: Spacing

# Widget._get_box_model():
gutter = styles.gutter           # padding + border
if styles.box_sizing == "border-box":
    content_width  = resolved_width  - gutter.width
    content_height = resolved_height - gutter.height
model = BoxModel(content_width + gutter.width, content_height + gutter.height, styles.margin)
```

Rich has no full box model but composable primitives: `rich.padding.Padding` (stores
top/right/bottom/left via `unpack()` with 1/2/4-value CSS arities), `rich.box.Box` (border glyph table),
`rich.panel.Panel` (border + padding + title).

Engine recipe:
```python
def resolve_border_box(spec, parent_size):
    gutter_w = spec.border.l + spec.border.r + spec.padding.l + spec.padding.r
    gutter_h = spec.border.t + spec.border.b + spec.padding.t + spec.padding.b
    if spec.box_sizing == "border-box":
        border_w  = resolve(spec.width, parent_size.cols)
        content_w = max(0, border_w - gutter_w)
    else:
        content_w = resolve(spec.width, parent_size.cols)
        border_w  = content_w + gutter_w
    return content_w, border_w
```
Keep layout math in integer cells; keep `fr`/ratio intermediates as `Fraction`; floor CUMULATIVE offsets
at placement time to avoid drift.

---

## 2. Layout algorithms

Vertical/horizontal stacks = integer grid allocation; each child gets `(x, y, w, h)`.
Rich names them `RowSplitter` (allocates widths) and `ColumnSplitter` (allocates heights).

CSS-like scalar units (Textual `Unit`): CELLS (bare int), FRACTION (`fr`), PERCENT (`%`),
WIDTH (`w`), HEIGHT (`h`), VIEW_WIDTH (`vw`), VIEW_HEIGHT (`vh`), AUTO.

### fr / fractional space distribution — THE KEY ALGORITHM
Do NOT round each track independently (produces total +/- 1 errors). Two equivalent correct methods:

(a) Rich `ratio_resolve(total, edges)` — carry-remainder:
```python
sizes = [edge.size or None for edge in edges]
while None in sizes:
    flexible = [(i,e) for i,(s,e) in enumerate(zip(sizes,edges)) if s is None]
    remaining = total - sum(s or 0 for s in sizes)
    if remaining <= 0:
        return [e.minimum_size if s is None else s for s,e in zip(sizes,edges)]
    portion = Fraction(remaining, sum(e.ratio or 1 for _,e in flexible))
    for i,e in flexible:                       # lock any min-size violation, restart
        if portion * e.ratio <= e.minimum_size:
            sizes[i] = e.minimum_size; break
    else:
        remainder = Fraction(0)
        for i,e in flexible:
            size, remainder = divmod(portion * e.ratio + remainder, 1)
            sizes[i] = size
        break
return sizes
# total=10, ratios [1,1,1] -> [3,3,4] (remainder carried forward)
```

(b) Textual `_resolve.resolve` — cumulative-floor:
```python
remaining = total - gutter_total - consumed_fixed
fraction_unit = Fraction(remaining) / sum(fr_values)   # each track = fr * fraction_unit
offsets = [0] + [floor(acc) for acc in accumulate(w1,gap,w2,gap,...)]
widths  = [offsets[i+1]-offsets[i] for ...]
# 10 cells, 1fr 1fr 1fr -> floored offsets [0,3,6,10] -> widths [3,3,4]
```
Both: fixed sizes subtracted first; flexible share remainder by weight; min/max violations locked and the
pass repeats until stable (Textual `resolve_fraction_unit` iterates min AND max constraints).

### Flexbox-style grow/shrink (practical TUI form)
```python
base = fixed_or_preferred_size; free = container - sum(base)
if free > 0:  # grow
    child = base + remainder_distribute(free * grow / sum(grow))
if free < 0:  # shrink (weighted by base), clamp to min, repeat if any hit min
    child = base - remainder_distribute(abs(free) * shrink*base / sum(shrink*base))
```

### Alignment (integer padding; extra cell goes right/bottom, matches Rich `Align`)
```python
# horizontal: left=0 ; center=(box_w-content_w)//2 ; right=box_w-content_w
# right_pad = box_w - content_w - left_pad
# vertical: top=0 ; middle=(box_h-content_h)//2 ; bottom=box_h-content_h
```

### Word wrap (Rich `_wrap.divide_line`)
- Tokenize words as regex `\s*\S+\s*` (word carries adjacent whitespace).
- Fit test uses `cell_len(word.rstrip())`.
- Word fits remaining line -> append. Doesn't fit but > width: fold=True splits by cell via `chop_cells`;
  fold=False breaks before the word (later cropped/ellipsized). Fits a fresh line -> break at word start.
- Full justification: distribute extra spaces into gaps right-to-left cyclically; never justify last line.

---

## 3. Drawing primitives

Box-drawing glyphs (Unicode U+2500..U+257F; rounded arcs U+256D..U+2570). One table per style; each is a
dict keyed by role. `─ │ ┌ ┐ └ ┘ ├ ┤ ┬ ┴ ┼` (single/light).

| role | single | rounded | heavy | double |
|---|---|---|---|---|
| horizontal | ─ 2500 | ─ 2500 | ━ 2501 | ═ 2550 |
| vertical   | │ 2502 | │ 2502 | ┃ 2503 | ║ 2551 |
| top-left   | ┌ 250C | ╭ 256D | ┏ 250F | ╔ 2554 |
| top-right  | ┐ 2510 | ╮ 256E | ┓ 2513 | ╗ 2557 |
| bot-left   | └ 2514 | ╰ 2570 | ┗ 2517 | ╚ 255A |
| bot-right  | ┘ 2518 | ╯ 256F | ┛ 251B | ╝ 255D |
| tee-right  | ├ 251C | ├ 251C | ┣ 2523 | ╠ 2560 |
| tee-left   | ┤ 2524 | ┤ 2524 | ┫ 252B | ╣ 2563 |
| tee-down   | ┬ 252C | ┬ 252C | ┳ 2533 | ╦ 2566 |
| tee-up     | ┴ 2534 | ┴ 2534 | ┻ 253B | ╩ 2569 |
| cross      | ┼ 253C | ┼ 253C | ╋ 254B | ╬ 256C |

(Rounded reuses light straight edges + light junctions; only the four corners differ.)

Truncation with ellipsis U+2026 (mirrors Rich `Text.truncate(overflow="ellipsis")`):
```python
def truncate_ellipsis(text, width):
    if cell_width(text) <= width: return pad_right(text, width)
    if width <= 0: return ""
    return set_cell_size(text, width - 1) + "…"
```
Align/pad text to width using `set_cell_size` (crop or pad) then left/right/center pad with spaces.

---

## 4. Width handling (columns must not misalign)

Never use `len(s)`. Use display-CELL width. UAX #11 East_Asian_Width classes: F/W -> 2 cells;
Na/H/N/A -> 1 (A "ambiguous" configurable to 2). Unicode warns EAW alone is insufficient for emulators.

Python `wcwidth`:
- `wcwidth(ch)`: ASCII fast path 1; C0/C1 controls -1; zero-width table 0; wide/fullwidth 2; ambiguous 1
  (or 2 if `ambiguous_width=2`); else 1.
- `wcswidth(s)`: -1 if any control char; U+200D ZWJ contributes 0 and can zero following emoji component;
  U+FE0F VS16 can widen narrow symbol to 2; U+FE0E VS15 requests text presentation; regional-indicator
  pairs = one flag width 2; Fitzpatrick modifiers add 0; grapheme cluster width currently capped at 2.
- Stable/guaranteed: `wcwidth`, `wcswidth`. Newer helpers exist (`width`, `iter_graphemes`, `wcstwidth`,
  `ljust/rjust/center`, `strip_sequences`, `wrap`, `clip`) but are NOT SemVer-frozen. Verified via API docs.

Rich `rich.cells`: `cell_len(text)`, `cached_cell_len`, `get_character_cell_size(ch)`,
`set_cell_size(text, total)` (crop/pad exact), `chop_cells(text, width)`, `split_graphemes`.
- Controls (<32, 0x7F..0x9F) -> 0. If no ZWJ/VS16 present, `cell_len` just sums per-char widths.
- Splitting never bisects a double-width cell; Rich substitutes spaces on both sides if a cut lands inside.

Policy for the engine: `display_width(s) = max(wcswidth(s), 0)` (or reject -1 controls); slice by
grapheme clusters accumulating cell widths, not by Python indices; reserve 1 cell for ellipsis; strip/parse
ANSI escapes as zero-width control before measuring.

Critical test strings:
```
"é"=1  "界"=2  "♀"=1  "♀️"=2  "👩‍💻"=2  "🇯🇵"=2  "\x1b[31mred"->measure "red"=3
```

---

## 5. Rich renderable composition (the pattern to mirror)

Two protocols:
- Simple: `def __rich__(self) -> str/renderable` (markup ok).
- Advanced: `def __rich_console__(self, console, options) -> RenderResult` yields Segments and/or nested
  renderables. Optional `def __rich_measure__(self, console, options) -> Measurement(min, max)`.

`Segment = NamedTuple(text: str, style: Optional[Style], control: Optional[Sequence])`.
Has `.cell_length`, `.is_control`, `Segment.split_lines/split_cells/adjust_line_length/apply_style/line`.
Wide chars = 2 cells, control segments = 0 cells (why layout depends on Segment, not str length).

Pipeline (`Console.render`):
1. `rich_cast()` resolves `__rich__` recursively.
2. If object has `__rich_console__`, call it with ConsoleOptions (carries max_width budget).
3. Else strings -> `Text`.
4. Recursively render yielded child renderables until only Segments remain.
5. `render_lines()` splits/crops/pads Segments to terminal-width lines.
6. `_render_buffer()` -> ANSI via `Style.render()` (SGR escapes) or plain text.

Measurement (`Measurement.get(console, options, renderable)`) drives width negotiation: parent measures
children (min/max cell width), decides each child's width budget, passes it down via ConsoleOptions.

Markup `[bold red]...[/]` is parsed to Style BEFORE render; ANSI is emitted only at the buffer stage.
Escape literal brackets with Rich's markup escape utility.

Mirror this: every widget = object with `render(width, height) -> list[list[Cell]]` (or yields Segments)
and `measure(available) -> (min, max)`. Parent measures children, resolves fr/ratio, hands each a width
budget, composites child cell-grids into its own, then the root serializes the cell grid to ANSI once.

---

## 6. Widget catalog (render approach each)

- Panel/frame + title: bordered rect; measure child, panel_w-2 for borders, render child lines, emit top
  border with title text spliced+aligned (title_align left/center/right), body rows wrapped in vertical
  glyphs, bottom border (subtitle). Rich `rich.panel.Panel` / `Panel.fit`; glyphs from `rich.box.Box`.
- Table: each `Column` has width/min/max/ratio/no_wrap/justify. `_measure_column` gets (min,max) per cell
  incl padding; `_calculate_column_widths` starts from maxima; if expand+ratio distribute via
  `ratio_distribute`; if over-wide `_collapse_widths` shrinks wrappable cols then `ratio_reduce`. Render
  with box glyphs, header/footer, show_lines, show_edge, collapse_padding, section separators.
  `rich.table.Table` (+ `Table.grid` for borderless).
- Card: no first-class class — compose `Panel` shell + inner `Group`/`Table.grid`/`Columns`/`Text`. Card
  lists -> `rich.columns.Columns` or `Table.grid`.
- Progress bar/meter: cells = ratio*width. Rich uses HALF-cell precision (full `━`, halves `╺`/`╸`), not
  eighths. For 1/8-cell precision map fractional remainder to `█▉▊▋▌▍▎▏` (U+2588..U+258F). Label/%/ETA are
  separate columns. Rich `Progress`, `BarColumn`, `TextColumn`, `TaskProgressColumn`, `TimeRemainingColumn`,
  `progress_bar.ProgressBar`. Textual `ProgressBar` + `renderables.bar.Bar`.
- Tabs/tabbed content: fixed/auto-width label cells; track active id; style active differently; underline
  highlight range under active tab (Textual `Underline` uses `renderables.bar.Bar`); content area switches
  pane. Textual `Tab/Tabs/TabbedContent/TabPane/ContentSwitcher`. Rich has no interactive tabs (use
  Text/Table.grid/Columns for static).
- Key/value list (definition list): 2-col grid, col1 = measured max key width (fixed), col2 wraps to
  remainder, usually no border. `Table.grid(padding=(0,2))` or `Table(show_header=False, box=None)`.
- Tree: DFS; track per-ancestor is-last-child; emit guide prefix (space / `│` continuation / `├──` fork /
  `└──` end) then label; expanded nodes recurse, collapsed skip. Rich `rich.tree.Tree` (TREE_GUIDES /
  ASCII_GUIDES). Textual `Tree`/`TreeNode` with NodeExpanded/Collapsed/Selected messages.
- Banner/big text: text -> multiline glyphs from a FIGlet font; render each line as Text; cache per
  font/text. `pyfiglet.Figlet` / `figlet_format` (Rich has none).
- Columns/grid: measure every child; pick column count that fits width; optional equal width; row-first or
  column-first; internally a `Table.grid` with collapsed padding. `rich.columns.Columns`.
- Rule/divider: fill width with repeated char; if title, sanitize + truncate + align, split remaining width
  around title for center. `rich.rule.Rule` / `Console.rule`.
- Badge/label/pill: single-line Text with padding spaces + fg/bg style; `[ label ]` or inverse video;
  Powerline caps only with Nerd Font. Width = cell length of padded label. Rich: styled `Text` /
  `Panel.fit(box=SQUARE)`. Textual: `Label`/`Static` + CSS.

---

## 7. Build-ready design summary

Core model: a `Cell` = (char, style). A `Buffer` = 2D array of Cells + a `blit(child_buffer, x, y)` that
respects wide-char occupancy. Every widget implements:
```python
def measure(self, available: Size) -> Measurement   # (min_w, max_w)
def render(self, region: Size) -> Buffer            # exact region.w x region.h cells
```
Layout container resolves child sizes with the carry-remainder `fr`/ratio algorithm (§2), places children
by cumulative-floored offsets, blits their buffers. Root serializes Buffer -> ANSI once (SGR run-length,
skip control cells). All widths via `wcswidth`/`cell_len`; slice by grapheme cluster; box glyphs from a
per-style dict (§3). This is Rich's renderable-composition pattern (§5) with Textual's box model (§1) and
fr resolution (§2) layered on top.
