> **⚠️ SUPERSEDED — historical only.** This spec was written from PNG *estimation*
> before the measured ground truth existed. It is now contradicted by measured
> reality and MUST NOT be cited as authoritative. Known contradictions:
> - Divider glyph: this says `┊` (U+250A) at col 73; the shipping code + ground truth
>   use `┆` (U+2506) — see `examples/effort_selector.py` and
>   `knowledge/ground-truth/effort-selector.md`.
> - Palette: this says left-end `#4C5BD4` / glow ramp `#C7A8FF…#4A1E8C`; measured truth
>   is periwinkle border `#b1b9f9`, accent `#8c50f0`, cosine ripple `#3e1676→#8c50f0`.
> - Main-rule glyph: this says `─` (U+2500); code renders `▔` (U+2594).
>
> **Authoritative source of truth:** `D:/Project/SmartCLI/knowledge/ground-truth/effort-selector.md`
> ([[effort-selector]]) and `examples/effort_selector.py`. Retained only as a record of
> the pre-measurement guess.

# Effort Selector — Precise Build Spec (measured from reference PNGs)

Source of truth: screenshots of the real /effort-style selector. This spec covers
**only the region from the "Effort" label DOWN**. No logo, no version line, no
ANTHROPIC warning block. Widget is interactive (←/→ move selection, Enter confirm,
Esc cancel) and animated (ultracode violet glow pulses/flows).

Reference frames read:
- Stage low  = 34d827f6 (real)
- Stage medium = f390a596 (real)
- Stage xhigh = c87d6416 (real)
- ultracode glow frame A (rounded rectangle, mid) = 3b547141
- ultracode glow frame B (wide soft vertical bands, peak) = e8fc4b99
- ultracode glow frame C (small radial blob, min) = 77b07db5
- codex FAIL (blocky full-width plasma) = ultracode_1_124x31, low_0_124x31

---

## 1. Coordinate system

Terminal reference width ≈ **124 columns** (matches the smoke sizes; the real
screenshots are 1115 px ≈ 9 px/char ≈ 124 cols). All columns below are 0-indexed
for a 124-col terminal; scale proportionally for other widths. Left content margin
is **col 4** (the "Effort" label and hint both start at col 4).

Row layout, expressed **relative to the "Effort" label row = R0** (each R is one
text line; blank rows are real spacer lines):

| Row | Content |
|-----|---------|
| R-1 | **Main rule** — full-width violet gradient solid line (col 0 → 123) |
| R0  | `Effort` — bold white, starts col 4 |
| R1  | (blank) |
| R2  | `Faster` at col 30 (left) … `Smarter` right-aligned ending ~col 91 |
| R3  | **Slider track** — solid `─` from col 30→91, dotted `┊` separator at col 73 |
| R4  | **Marker row** — single `▲` at the selected stage's column, else blank |
| R5  | **Stage row** — `low  medium  high  xhigh  max ┊ ultracode` |
| R6  | Subtitle `xhigh + workflows` (only when on ultracode), starts ~col 75 |
| R7  | (blank) |
| R8  | Hint `←/→ to adjust · Enter to confirm · Esc to cancel`, starts col 4 |

Total widget height = 10 rows (R-1 … R8).

### Stage label columns (center / start)
Stages are spread across the track. Measured centers (124-col grid):

| Stage      | label start col | center col | track marker col (▲) |
|------------|-----------------|------------|----------------------|
| low        | 29              | 31         | 31                   |
| medium     | 36              | 41         | 41                   |
| high       | 48              | 51         | 51                   |
| xhigh      | 56              | 60         | 60                   |
| max        | 68              | 70         | 70                   |
| *(sep `┊`)*| —               | 73         | 73                   |
| ultracode  | 78              | 83         | 83                   |

Even spacing: low→max are ~9–10 cols apart. The **dotted vertical separator `┊`
(U+250A) sits at col 73**, between `max` and `ultracode`, and is drawn on BOTH the
track row (R3) and visually continues down toward the stage row. It is dim
gray (#5A5A6A), light/faint.

---

## 2. Main rule (R-1) — VIOLET GRADIENT SOLID LINE

- Character: solid `─` (U+2500), **full terminal width** (col 0 → 123). One line.
- **NOT** gray dashed `----` (that is codex's cheap version — forbidden).
- Color: horizontal **violet gradient**, blue-violet on the left → violet on the
  right. Per-cell interpolation across the width:
  - left  end #4C5BD4 (indigo-blue)
  - mid       #7C5CE0 (violet)
  - right end #A78BFA (light violet)
- It is a single-pixel-thin solid rule, full brightness (not dimmed). This is the
  divider that separates the effort panel from the content above.

---

## 3. Slider track (R3) — THIN SOLID LINE

- Character: solid `─` (U+2500). **NOT** dashed.
- Span: col 30 → col 91 (≈61 chars), aligned so the left end sits under `Faster`
  and the right end under `Smarter`.
- Two-segment coloring:
  - **Left segment** col 30 → 72 (up to the separator): dim neutral gray
    **#6E7080** (faint, un-emphasized rail).
  - **Separator** col 73: `┊` dotted vertical, dim gray **#5A5A6A**.
  - **Right segment** col 74 → 91 (the ultracode reach): **violet #A07CE9**
    (the "smarter/ultracode" side of the rail is tinted violet even when not
    selected).
- `Faster` (R2, col 30) and `Smarter` (R2, right end ~col 85–91) labels are
  **white #E6E6E6**, not bold.

### Marker (R4)
- Character: `▲` (U+25B2), filled up-triangle.
- One per render, positioned at the selected stage's marker col (table above),
  directly under the track line.
- Color: matches the selected stage's highlight color (see §5). White/bright when
  neutral; e.g. gold when low is selected, violet when ultracode.

---

## 4. Stage row (R5) & subtitle (R6)

- Row text (single spaces collapsed for spacing shown; use the center cols above):
  `low   medium   high   xhigh   max ┊ ultracode`
- The dotted `┊` at col 73 divides the five "normal" stages from `ultracode`.
- **Subtitle** `xhigh + workflows` on R6 appears **only when ultracode is the
  active stage**, positioned under `ultracode` (start ~col 75). Color: dim gray
  **#8A8A99**.
- Hint R8 `←/→ to adjust · Enter to confirm · Esc to cancel` — dim gray
  **#8A8A99**, the `·` separators slightly dimmer.

---

## 5. Per-stage colors & highlight

**Selected** stage = **bold + its accent color**. **Unselected** stages = dim gray
**#6E7080** (muted, low-contrast), EXCEPT `ultracode` which is always drawn in
violet (never fully dimmed).

| Stage     | Accent color (selected)                                                                 | Notes |
|-----------|------------------------------------------------------------------------------------------|-------|
| low       | **#FFC107** (amber/gold), bold                                                           | |
| medium    | **#4EBA65** (green), bold                                                                | |
| high      | **brighten #494C64 → ~#8E92B8** for visibility, bold                                     | base #494C64 too dark; lift ~40% |
| xhigh     | **#A07CE9** (violet) with a subtle **violet↔white flicker** on the selected label       | oscillate label between #A07CE9 and #E9DEFF each ~200ms |
| max       | **rainbow shoulder gradient** across the letters: `#FAC35F #69905F #0C0C0C #F58B57 #FAC35F #7DA3D2 #EB5F57` | per-glyph gradient (7 stops mapped across "max" + shoulder); animate the gradient offset for a slow shimmer |
| ultracode | **violet**, bold; core lavender **#C4A8FF**, always tinted even when unselected          | brightest when selected; drives the glow (§6) |

`max` rainbow: distribute the 7 stops across the visible glyphs (and, if animating,
slide the gradient window one stop per frame for a shimmering shoulder effect).

---

## 6. Ultracode violet glow — LOCAL, ROUNDED, RADIAL, PULSING

This is the signature effect and where codex failed. Build it as a **radial glow
field centered on the `ultracode` label**, composited BEHIND the text (text stays
readable on top). The glow **pulses/breathes**: its radius oscillates over time
while the bright core stays locked over `ultracode`.

### Geometry
- **Center** of the radial field: the `ultracode` label center (≈ col 83, R5),
  vertically centered on the ultracode block (spans roughly R2→R6 at peak).
- **Falloff**: intensity = f(distance from center), smooth (e.g. `1 - (d/R)²` or a
  gaussian). **Bright core → soft, rounded edges.** Corners are ROUNDED, never a
  hard rectangle.
- **Never hard-edged blocks.** Sample cells with sub-cell dithering/soft alpha so
  edges feather out. Codex used opaque rectangular column cells with sharp borders
  — forbidden.

### Color ramp (core → edge)
- core / hottest:  **#C7A8FF → #B98CF0** (light lavender, near-white center)
- mid:             **#8B5CF6 / #7C4DD6** (violet)
- outer:           **#5A2EA6**
- edge / fade:     **#4A1E8C** (deep purple) → fully transparent
Blend the glow color with the underlying dark bg using alpha = intensity, so the
edges dissolve into the panel background rather than cutting off.

### Animation (3 measured keyframes → interpolate & loop, breathing)
The three reference frames are three radii of the SAME centered radial pulse:

- **Frame C (min radius)** — small rounded blob (~circular/hex) covering only
  `ultracode` + its subtitle + the marker (≈ cols 76–92, R4–R6). Bright, tight,
  clearly rounded. This is the trough of the pulse.
- **Frame A (mid radius)** — rounded rectangle with rounded corners reaching left
  to ~`max` (≈ cols 63–96), covering R2→R6. Bright violet core still over
  ultracode; edges soft.
- **Frame B (peak radius)** — glow expands wide as **soft vertical light bands /
  shafts** radiating outward, brightest at the ultracode center and fading with
  distance. Even at peak it stays a soft radial field with vertical streaks — NOT
  uniform, NOT hard blocks. (In the reference it can reach near full width, but the
  user-locked requirement is to keep it **concentrated and soft**: prefer capping
  the peak so the core stays visibly localized over ultracode with smooth falloff.
  Do not fill the whole panel with flat opaque violet.)

**Loop**: radius eases C → A → B → A → C (breathing), period ~1.5–2.5s, easing
in/out (sine). Optional: a slow vertical-band phase drift within the field for the
"flowing" look at larger radii. The bright center never leaves the ultracode label.

### Text over glow
- `ultracode` label: keep bold, bright (#E9DEFF / near-white) so it reads on top of
  the glow.
- `Smarter`, `xhigh + workflows`, and any track chars under the glow stay legible
  (light foreground); do NOT let the glow wash them to low contrast the way codex
  did (codex desaturated the overlapped text into the plasma).

---

## 7. Explicit contrast — what codex did wrong (avoid)

1. **Main rule**: codex used a gray dashed `--------` full-width rule. → Use a
   VIOLET GRADIENT SOLID `─` rule instead.
2. **Track**: codex's track read as dashed/segmented. → Use a THIN SOLID `─` line
   (gray left, violet right).
3. **Ultracode glow**: codex rendered a **full-width, blocky, hard-edged column
   plasma** (opaque rectangular cells spanning the entire panel, sharp borders,
   uniform bright bands edge-to-edge) that also **washed out the overlapped text**.
   → Use a **LOCAL, ROUNDED, RADIAL** glow: bright center over `ultracode`, smooth
   feathered falloff, rounded corners, pulsing radius, text stays crisp on top.
4. Codex over-dimmed nothing / lacked stage accent colors → apply the exact
   per-stage accents in §5 with bold on the selected stage.

---

## 8. Interaction

- `←` / `→` : move selection among [low, medium, high, xhigh, max, ultracode].
  Clamp at ends. Moving updates the ▲ marker column, the highlighted stage
  accent+bold, shows/hides the ultracode glow (only active on ultracode) and the
  `xhigh + workflows` subtitle (only on ultracode).
- `Enter`  : confirm the current stage → return it, close widget.
- `Esc`    : cancel → return nothing/previous, close widget.
- Animation timer runs only while `ultracode` is selected (drives the glow pulse);
  the `max` rainbow shimmer runs while `max` is selected.
