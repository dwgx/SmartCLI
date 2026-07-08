# Deep-Dive: TUI Layout & Interaction Techniques — Raw Notes

> Research date: 2026-07-08. Companion to `works-tui.md` (the survey). This file goes
> one level deeper on the ~8 most instructive works, extracting the CONCRETE technique
> for each of: box model / flex layout / rendering diff / animation / color degradation /
> mouse+key handling. Every claim is tied to a fetched primary source URL. Where a page
> was only high-level, that is flagged and the exact math is drawn from the raw source
> file that did contain it (e.g. termenv `color.go`).

Maps into KB: `principles/` (box model, flicker-free, layout), `tui-patterns/`,
`color-type/` (degrade), and the `rendering-model` kernel.

---

## 1. Textual (Python) — CSS box model + grid + fr + compositor + animation + input

- Repo: https://github.com/Textualize/textual
- Layout guide: https://textual.textualize.io/guide/layout/
- Styles/box model: https://textual.textualize.io/guide/styles/
- Animation: https://textual.textualize.io/guide/animation/
- Input: https://textual.textualize.io/guide/input/
- Compositor deep-dive: https://textual.textualize.io/blog/2024/12/12/algorithms-for-high-performance-terminal-apps/

### Box model (from styles guide)
- Layering inside-out: **content area → padding → border → margin**. Border adds exactly
  **2 rows + 2 cols** (one per edge). Padding int = N rows+cols all sides; 2-tuple =
  (top/bottom, left/right); 4-tuple = top,right,bottom,left (clockwise, CSS order).
- **`box-sizing` default = `border-box`**: padding+border are SUBTRACTED from the content
  area, widget stays the declared size (height 6 + border + pad 1 ⇒ only 2 content lines).
  `content-box`: padding+border ADDED, content stays declared size, widget grows.
- **`outline`** is set like border but does NOT change size and may overlap content.
- **Margins collapse**: adjacent widgets pick the GREATER of the two margins, not sum.

### Sizing units
- `fr` (fraction): available space ÷ (sum of all fr for that axis), assigned proportionally
  (2fr/1fr ⇒ 2/3 and 1/3). Widgets auto-fill parent WIDTH but NOT height — height needs
  explicit `100%`.
- Units: fixed cells, `%` (of parent), `vw`/`vh` (of terminal), `w`/`h` (of available,
  ≤ terminal if nested), `auto` (fit content). Caps: `min/max-width`, `min/max-height`.

### Layouts
- `vertical` (default for Screen; auto vertical scrollbar via `overflow-y: auto`),
  `horizontal` (no auto scrollbar), `grid`.
- **Grid**: `grid-size: <cols> [rows]` — omit rows ⇒ rows added on demand; fixed rows ⇒
  overflow widgets hidden. Cells fill left-to-right, top-to-bottom.
- **Track sizing**: `grid-columns` / `grid-rows` take space-separated per-track values of
  `fr` / `%` / fixed int / `auto`. **Too-few values CYCLE** (`2 4` over 4 cols ⇒ `2 4 2 4`).
  **Space-distribution order**: size fixed + `%` + `auto` tracks first, THEN divide the
  remainder among `fr` tracks in proportion to their fr values.
- **Gutter**: `grid-gutter` on the CONTAINER only (not children); 1 value uniform, 2 values
  = vertical then horizontal. `grid-gutter: 1 2` compensates for the ~2:1 cell aspect.
- **Spans**: `column-span`/`row-span` on the CHILD; combine for rectangular blocks; spanning
  past available cols is capped; a span can push later cells to a new row.

### Compositor (blog) — "switch the primitive"
- Never a 2D char grid (breaks on double-width CJK/emoji). Everything is a **Segment**
  (string+style, from Rich), ANSI only at the end. Merge overlapping widgets per line:
  (1) **find cuts** = collect all begin/end offsets; (2) **apply cuts** = split each list
  into non-overlapping "chops"; (3) **discard** occluded chops (keep top-most only);
  (4) **combine** survivors. `_compositor.py` + `_spatial_map.py` are reusable (author invites it).
- **Spatial Map**: grid-bucketing at tile **100 cols × 20 lines**; dict tile→widgets;
  visible-widget cull ~constant-time regardless of count (1000 widgets ≈ 8). Cacheable
  while scrolling. Partial updates redraw only the changed region.

### Animation
- `widget.animate(attr, value=, duration=|speed=, easing=, on_complete=)` and identical
  `styles.animate(...)`. `duration` = total seconds; `speed` = units/second (0→10 @ 2 ⇒ 5 s).
- **Default easing = `in_out_cubic`** (accelerate then decelerate). Interpolates in fixed
  small increments over time; non-blocking (driven by the app's timer loop). `on_complete`
  callback when done. Preview easings via `textual easing` (textual-dev).

### Input
- **Key** event (`textual.events.Key`): `key` (single char or long name, modifiers prefixed
  `ctrl+p`, `shift+home`; Shift+letter ⇒ capital), `character` (printable or None),
  `name` (Python-safe: lowercase, `+`→`_`, uppercase gets `upper_` prefix ⇒ `ctrl_p`,
  `upper_p`), `is_printable`, `aliases` (Tab ⇒ `["tab","ctrl+i"]`, indistinguishable in
  the terminal). Handle via `on_key` or `key_<name>`; bindings preferred.
- **Binding resolution**: check focused widget's `BINDINGS`, then search UP the DOM to the
  App. `priority=True` bindings checked FIRST and un-overridable (that's how `ctrl+q` quit
  is guaranteed). `show=False` hides from Footer.
- **Focus**: one widget at a time; `can_focus`; Tab/Shift+Tab cycle; `Focus`/`Blur` events;
  CSS `:focus`.
- **Mouse**: coords `x` (col), `y` (line); `(0,0)` screen- or widget-relative. Events:
  `MouseMove` (+modifiers), `MouseDown`→`MouseUp`→`Click` (prefer `Click`), `Enter`/`Leave`
  (bubble — check `event.node is self`), `MouseScrollDown/Up/Left/Right`. **Bubbling**:
  events propagate UP the DOM toward App. `capture_mouse()`/`release_mouse()` route all
  mouse events to one widget (coords may go negative). NOTE: page doesn't name the SGR-1006
  escape mode or a stop-propagation API — those live in other API docs (flag).

---

## 2. Ratatui (Rust) — Cassowary constraint layout + immediate-mode buffer diff

- Repo: https://github.com/ratatui/ratatui
- Layout: https://ratatui.rs/concepts/layout/
- Render under-the-hood: https://www.ratatui.rs/concepts/rendering/under-the-hood/

### Layout (Cassowary constraint solver)
- `Layout::default().direction(Direction::Vertical|Horizontal).constraints([...]).split(rect)`
  → indexed `Rc<[Rect]>`. Nest by feeding one layout's output rect into another's `split`.
- **`Constraint` variants**: `Length(u16)` (fixed, absolute), `Percentage(u16)` (of PARENT),
  `Ratio(a,b)` (of parent), `Min(u16)` (floor), `Max(u16)` (ceiling), `Fill(u16)`
  (proportional scaling factor into leftover, relative to other Fills).
- Solved by the **`cassowary` crate** (the constraint solver). When constraints conflict
  the solver returns a best-fit approximation (can be non-deterministic) rather than failing.
  By default leftover goes to the LAST area; a trailing `Min(0)` prevents that.
- **`Flex`** (excess-space positioning when constraints under-fill): `Legacy` (excess→last),
  `Start`, `End`, `Center`, `SpaceBetween`, `SpaceAround`. `.spacing(u16)` inserts uniform
  gaps. Order of constraints = order applied along the direction.

### Rendering (immediate mode + double-buffer diff)
- UI recreated from scratch each frame: `Terminal::draw(|frame| ...)`. A **`Cell`** =
  smallest unit (≈ a pixel): 1-wide **symbol string + style (fg/bg/modifiers) stored
  SEPARATELY** — embedded ANSI in a cell string is NOT interpreted (convert via
  `ansi-to-tui` first). Two `Buffer`s; each frame: wipe current, widgets draw into it,
  **diff current vs previous → emit only changed cells**, then **swap buffers**. All widgets
  share ONE buffer so later widgets overwrite earlier ⇒ render ORDER matters. Concrete
  diff + cursor-move code is in `buffer.rs`/`terminal.rs` (not the doc page). v0.30 added
  more precise buffer-diff options.

---

## 3. Bubble Tea + Lip Gloss (Go, Charm) — Elm loop + frame diff + Style structs + Join/Place

- Bubble Tea: https://github.com/charmbracelet/bubbletea  (key.go:
  https://github.com/charmbracelet/bubbletea/blob/master/key.go)
- Lip Gloss: https://github.com/charmbracelet/lipgloss

### Architecture + renderer (from works-tui, kept for cross-ref)
- Elm: `Init() Cmd`, `Update(Msg)`, `View()`. Many producers → ONE `chan Msg`, single
  consumer event loop (deterministic). `Cmd = func() Msg`; `BatchMsg` concurrent,
  `sequenceMsg` sequential; panics recovered. **Renderer** (`cursedRenderer`): double
  `uv.ScreenBuffer`, `flush` diffs frames → minimal ANSI, tracks **dirty lines**, cursor-move
  opts (tabs/backspace/`\n`), **60 Hz** flush ticker, wraps frames in **DEC-2026
  synchronized output** to kill tearing.

### Input model (key.go)
- `KeyPressMsg` / `KeyReleaseMsg` both are `type … Key`; satisfy `KeyMsg` interface
  (`fmt.Stringer` + `Key() Key`). **`Key` struct**: `Text` (printable chars), `Mod KeyMod`
  (ModCtrl/ModAlt/…), `Code rune` (special key or char), `ShiftedCode`, `BaseCode` (PC-101
  layout — Kitty-protocol/Windows only), `IsRepeat` (held — Kitty/Windows only).
  `Keystroke()` renders modifier order **ctrl, alt, shift, meta, hyper, super** (canonical,
  never reordered). Key constants aliased from `charmbracelet/ultraviolet` (`uv`): arrows,
  keypad, F1–F63, media. `KeyExtended` = multi-rune event. NOTE: the escape-sequence BYTE
  parser + `MouseMsg`/`WindowSizeMsg` live in the `ultraviolet` package, not key.go (flag).

### Lip Gloss — style structs + block layout
- `lipgloss.NewStyle()` → **value-type `Style`**, fluent setters each return a NEW copy
  (assignment = copy). Setters: inline (`Bold/Italic/Faint/Blink/Strikethrough/Underline/
  Reverse/Hyperlink`), color (`Foreground/Background/Border{Foreground,Background}`,
  `BorderForegroundBlend(a,b)` = gradient border), block (`Padding*`, `Margin*`,
  `PaddingChar/MarginChar` fill), sizing (`Width/Height/MaxWidth/MaxHeight/Align/Inline`).
  Shorthand is CSS-clockwise (`Padding(1,4,2)` = top / sides / bottom). `Inherit` pulls only
  UNSET rules; `Unset*` clears. Borders: `Normal/Rounded/Thick/Double/Markdown/ASCIIBorder()`
  or custom `Border{Top,Bottom,Left,Right,TopLeft,…}` struct.
- **Block composition**: `JoinHorizontal(pos, blocks…)` side-by-side (pos aligns on the
  vertical axis, float 0..1 = fraction from top of tallest); `JoinVertical(pos, …)` stacks
  (pos aligns horizontally). Impl (`join.go`): split into lines, measure max width/height,
  pad shorter lines per the pos float.
- **Placement**: `Place(w,h,hPos,vPos,block)`, `PlaceHorizontal(w,pos,block)`,
  `PlaceVertical(h,pos,block)` position content within whitespace (styleable).
- **Measurement (ANSI+Unicode aware)**: `Width/Height/Size(block)` skip escape sequences,
  count CJK/wide correctly. `Wrap(text,width,breakpoint)` preserves ANSI + hyperlinks across
  line breaks. Tabs → 4 spaces at render (`TabWidth(n)`, `NoTabConversion`).
- **Compositor** (newer): `NewLayer(content).X().Y().Z()` + `compositor.Compose(a,b,c).Render()`
  — cell-based layered compositing with per-layer mouse-click detection.
- **Color utils**: `Darken/Lighten/Complementary/Alpha`, `Blend1D(n,…)`, `Blend2D(w,h,rot,…)`.
  Adaptation: `HasDarkBackground`, `LightDark(bool)`, `Complete(profile)`, `compat`
  `AdaptiveColor`/`CompleteColor`. Downsampling happens in the drop-in `Print/Printf/Sprint…`
  writers (delegates to termenv-style degrade → see #4).

---

## 4. termenv (Go) — EXACT truecolor→256→16 color degradation

- Repo: https://github.com/muesli/termenv
- Raw source (formulas): https://raw.githubusercontent.com/muesli/termenv/master/color.go

### Profiles + detection
- 4 profiles, degrade chain **TrueColor → ANSI256 → ANSI(16) → Ascii**, always "closest
  match." `ColorProfile()` = capability detect; `EnvColorProfile()` = same but honors
  `NO_COLOR` / `CLICOLOR_FORCE`. (README doesn't spell the COLORTERM/TERM parse — that's in
  `profile.go`.)

### RGB → ANSI256 (`hexToANSI256Color`) — computes cube AND gray candidate, picks closer
- **Channel quantize** to 0..5 (`v2ci`):
  `v<48 → 0`, `v<115 → 1`, else `int((v-35)/40)`.
- **Cube index**: `ci = 36*r + 6*g + b` (0..215); represented color reconstructed via LUT
  `i2cv = [0, 0x5f, 0x87, 0xaf, 0xd7, 0xff]`.
- **Grayscale**: `average = (r+g+b)/3` (of the QUANTIZED 0..5 indices — coarse);
  `average>238 ? grayIdx=23 : grayIdx=(average-3)/10` (0..23); gray value `gv = 8 + 10*grayIdx`.
- **Select**: compare distances, `if colorDist <= grayDist: return 16 + ci` else
  `return 232 + grayIdx` (ties favor the cube).

### ANSI256 → ANSI16 (`ansi256ToANSIColor`)
- Brute-force nearest over the 16 base colors, keep min distance.

### Distance metric (important)
- NOT euclidean RGB. Uses **go-colorful `DistanceHSLuv`** (perceptually-oriented HSLuv
  space); colors loaded via `colorful.Hex`. This is the "closest match" that makes degrade
  look good vs naïve RGB nearest.

---

## 5. notcurses (C) — sub-cell "pixel" blitters + z-ordered planes

- Repo: https://github.com/dankamongmen/notcurses
- Visual man page: https://notcurses.com/notcurses_visual.3.html

### Blitters (rows×cols sub-cell divisions per cell)
| Blitter | Geometry | Glyphs |
|---|---|---|
| `NCBLIT_1x1` | 1×1 | spaces (ASCII-safe) |
| `NCBLIT_2x1` | 2×1 | half blocks ▄▀ (aspect-PRESERVING) |
| `NCBLIT_2x2` | 2×2 | halves ▌▐ + quadrants ▖▗▟▙ |
| `NCBLIT_3x2` | 3×2 | sextants (stretch ×1.5) |
| `NCBLIT_4x2` | 4×2 | octants (aspect-preserving, some color loss) |
| `NCBLIT_BRAILLE` | 4×2 | braille dots |
| `NCBLIT_PIXEL` | true px | sixel / Kitty |
| `NCBLIT_4x1 / 8x1` | 4/8×1 | plot blocks (graphs, not media) |

### Core constraint + selection
- **Only TWO colors available per cell** ⇒ pick 1 glyph + 2 colors. `1x1` and `2x2` are
  perfectly representable in 2 colors; higher geometries pack more sub-regions than 2 colors
  express, so they "increasingly require interpolation." Transparency always honored fully.
- Cell px dims should divide evenly by geometry; when not, segments are unequal (3×2 on an
  8×14-px cell ⇒ two 5-px + one 4-px vertical segments). (The exact per-glyph winner-choosing
  quantization is in source, not this page — flag.)
- **Default blitter** (`ncvisual_media_defblitter`): no-UTF8 ⇒ 1×1; NONE/SCALE ⇒ 2×1
  (aspect-preserving); STRETCH ⇒ 4×2 if octants else 3×2 if sextants else 2×2.
- **Pixel/sixel**: sixels render in 6-line bands; non-multiple-of-6 rows faked transparent;
  best sprixel = multiple of both cell height and 6. Kitty divides alpha by 2 per pixel.
- **Planes/piles/z**: draw onto z-ordered `ncplane`s; nothing shows until `ncpile_rasterize`
  flattens the pile to the physical display. Sprixels interact poorly w/ multiple planes.
  (Plane-flatten/compositing algorithm is in notcurses_render(3) — not fetched.)

---

## 6. chafa (C) — image→Unicode via per-cell coverage-bitmap symbol match

- Repo: https://github.com/hpjansson/chafa | Reference: https://hpjansson.org/chafa/ref/
- Rust port (confirms core): https://lib.rs/crates/chafa-syms-rs
- Symbol map ref: https://hpjansson.org/chafa/ref/chafa-ChafaSymbolMap.html

### Technique (confirmed via the pure-Rust port that targets bit-exact parity w/ chafa 1.19.0)
- **8×8 pixel grid per cell = 64 sub-pixels.** `draw_all_pixels` stretches the source to
  `width*8 × height*8` before selecting symbols (pre-sized path expects exactly
  `width*8*height*8` px).
- Per cell: choose the **Unicode symbol + fg + bg** that best reconstructs the 8×8 block.
  Each candidate symbol carries a **coverage bitmap** (which of the 64 sub-pixels it lights).
  Fg/bg colors are extracted per cell (the covered vs uncovered pixel groups). Candidates are
  **scored** and equal-score ties broken by a stable order (stock chafa's tie-break is
  platform-dependent sort). Symbol sets: builtin + generated **Braille / Sextant / Octant**,
  narrow + wide symbols. Color: RGB and **DIN99d** (perceptually uniform) spaces + dithering.
- NOTE: the exact cost function (popcount/hamming over the bitmap vs summed color-difference
  of the fg/bg partition) is in the C source / the port's source, not on the landing pages —
  flag for a source-level dig if the exact metric is needed. What's CONFIRMED: 8×8=64 grid,
  per-symbol coverage bitmap, per-cell fg/bg extraction, scored candidate selection.

---

## 7. fzf (Go) — FuzzyMatchV2 scoring (kept from works-tui; directly reusable)

- Repo: https://github.com/junegunn/fzf | Viz: https://timothya.com/learning/fzf
- Modified **Smith-Waterman DP**. Recurrence: `s1 = H[i-1][j-1] + matchScore + bonus`
  (consume pattern char); `s2 = H[i][j-1] + (inGap ? gapExt : gapStart)` (skip text);
  `H = max(s1,s2,0)`. Constants: match **+16**, gap-start **−3**, gap-ext **−1** (affine ⇒
  prefers one long gap). Bonuses: word-boundary **+8**, after whitespace/BOS **+10**, after
  `/ , : ; |` **+9**, camelCase/letter→digit **+7**, consecutive-run **+4**, first-char **×2**.
  Boundary bonus tuned to cancel after ~8 gap chars. Parallel **C matrix** tracks run length
  (`foob` prefers `foobar` over `foo-bar`). Phases: ASCII gate window → bonus+feasibility →
  int16 forward fill (cap M≤1000 else greedy V1) → backtrace H(+C) for matched positions.

---

## 8. yazi (Rust) — two-tier async scheduler + discardable tasks + 2-pass image preview

- Repo: https://github.com/sxyazi/yazi | Blog: https://yazi-rs.github.io/blog
- Everything time-consuming = async task off the render thread (Tokio). **Macro** workers
  (heavy, 10 default) + **micro** workers (small/urgent — mime, image preload, dir size, 5
  default); idle big cores help micro; 3 priority levels (low/normal/high) preempt.
  **Chunked dir load** (streams 100k-file dirs; re-reads only changed). **Discardable tasks**:
  fast nav aborts in-flight previews (Tokio `abort` for I/O; atomic per-line `ticket` for CPU
  highlight; interruptible Lua). **Render batching** merges actions into one render; progress
  bars render independently. Highlight bounded to visible window (first N lines; kills `jq`
  after N). **Two-pass image preview**: pre-downscale to cached lossy image, downscale again
  to fit on select; video/PDF pre-converted. Output Kitty/inline/sixel; **stdout locked only
  after image data prepared** (prevents corruption during fast nav); partial-erase preview so
  popups don't overlap, then redraw.

---

## Cross-cut summary → SmartCLI mapping

| Dimension | Best model to steal | Source |
|---|---|---|
| Box model | Textual `border-box` default (pad+border subtract from content); margins collapse to max | textual styles guide |
| Flex/proportional | Textual `fr` = space ÷ Σfr; Ratatui `Fill` + Cassowary constraints; Lip Gloss Join/Place | textual/ratatui/lipgloss |
| Grid | Textual: size fixed+%+auto tracks, THEN divide leftover among fr; gutter on container; spans on child | textual layout |
| Render diff | Ratatui double-buffer Cell diff + swap; Bubble Tea dirty-lines + 60Hz + DEC-2026; Textual segment compositor + spatial map | all three |
| Animation | Textual `animate(attr, duration|speed, easing=in_out_cubic)`, non-blocking timer, on_complete | textual animation |
| Color degrade | termenv: cube `16+36r+6g+b` w/ `v2ci` quantize + gray `232+idx`, pick closer via **HSLuv** distance | termenv color.go |
| Sub-cell pixels | notcurses blitter table (2×1 half aspect-safe, 2×4 braille, 3×2 sextant); chafa 8×8 coverage bitmap | notcurses/chafa |
| Key handling | Textual DOM-bubbling binding search + priority bindings; Bubble Tea canonical modifier order | textual/bubbletea |
| Mouse | Textual Click>Down/Up, Enter/Leave bubble, capture_mouse; SGR-1006 mode (impl detail, flag) | textual input |
| Fuzzy search | fzf FuzzyMatchV2 (exact constants) | fzf |
| Async off render thread | yazi two-tier scheduler + discardable tickets | yazi blog |

### Gaps flagged (need source-level dig if exact math wanted)
- chafa exact symbol COST function (popcount/hamming vs color-diff sum) — in C source only.
- notcurses per-glyph winner quantization + `ncpile_rasterize` compositing — in render(3)/source.
- Bubble Tea escape-BYTE→Msg parser + MouseMsg/WindowSizeMsg — in `ultraviolet` package, not key.go.
- termenv COLORTERM/TERM detection parse — in `profile.go`, not color.go.
- Textual SGR-1006 mouse mode + stop-propagation API — other API-doc pages.
