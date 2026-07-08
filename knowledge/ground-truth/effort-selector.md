# /effort Selector — violet-ripple selector case study

**What it is:** SmartCLI's worked replica of a `/effort`-style multi-stage picker (low/medium/high/xhigh/max/ultracode) whose ultracode state washes a rectangular **cosine ripple** of violet behind the text. It is the flagship demonstration that a rich animated selector decomposes into the four engine primitives — **not** a bespoke script. The authoritative, runnable implementation is `skills/tui-ui/examples/effort_selector.py`; read that for the exact constants. This note captures the *technique* and the *discipline*, not a table of magic numbers.

The lesson this case taught (a dozen failed rounds) is method, not code — see [[hard-lessons]]. The primitive decomposition is in [[rendering-model]].

---

## The shape (what to get right before writing render code)

- The ultracode glow is an **8-row rectangle** of violet, anchored at the selected marker column and expanding outward — NOT a 1–2 row bar (that scale error wrecked a dozen early rounds; [[hard-lessons]] rule 2).
- It is a **cosine ripple over aspect-corrected distance**: cells are ~2:1 tall:wide, so the row delta is scaled ×2 before computing distance (the `((row-anchor)*2)^2` law from [[rendering-model]]). The wavefront expands over time; cells beyond the travel radius stay untouched, so the block visibly grows from the marker side.
- Only the **ultracode** state has a background ripple block. Other stages have no background — only the selected word is recolored + bold, the rest dim gray. `max` is an intrinsic rotating rainbow, `xhigh` an intrinsic L→R shimmer — active only on the lit word.

## The compositing model (the whole point)

The ultracode ripple is one `field.Ripple(origin=marker_col, wavelength, travel=elapsed·rate, palette=violet-ramp)`, sampled per cell with the aspect-corrected distance, white text composited *over* it. So the selector = **layout (label/marker positions) + one Ripple field + text over** — a dozen lines of field definition. This is exactly the [[rendering-model]] thesis. See `ui/field.py::Ripple` for the primitive and `examples/effort_selector.py` for how it composes.

## Navigation gotcha (survives independent of the visuals)

A picker that runs in **application cursor mode** (DECCKM) needs arrow keys sent as **SS3** (`ESC O C` / `ESC O D`), not CSI (`ESC [ C`). Sending CSI moves nothing — an early source of contaminated captures. Always confirm the marker actually moved before trusting a capture. See [[application-cursor-mode]] / [[application-cursor-keys-deckm]].

---

**Source:** Load-bearing project artifact — authority is SmartCLI's own verified replica `skills/tui-ui/examples/effort_selector.py` (run it: `python skills/tui-ui/examples/effort_selector.py --once --stage ultracode --frame 1`) and the primitive it composes, `ui/field.py::Ripple`. The exact palette/geometry/layout constants live in that code, kept as the single source of truth.

**See also:** [[hard-lessons]], [[rendering-model]], [[color-interpolation]], [[hsv-cycling-lolcat]], [[terminal-cell-aspect-ratio]], [[application-cursor-mode]], [[application-cursor-keys-deckm]], [[flicker-free-rendering]], [[box-drawing-glyphs]]
