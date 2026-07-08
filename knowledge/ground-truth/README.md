# Ground Truth — Measured Reality, Not Guesses

The load-bearing corner of the graph. Everything here is **primary-source**: exact constants and per-cell measurements from real programs, frame-by-frame animation measurements, and the hard-won discipline for producing them. These entries are the reference standard for any **replica** task — reproducing a real, existing TUI/CLI effect.

**Core discipline:** replica tasks are won by *measuring ground truth*, never by head-canon. Get the real bytes (decompile / drive-and-capture / screenshot-to-frames), quantify scale and form, extract exact parameters, build against truth, verify on the real run path. See [[hard-lessons]] for the ten rules and [[effort-selector]] for the worked case.

## Entries
- [[effort-selector]] — the worked violet-ripple selector replica: an 8-row rectangular cosine ripple over aspect-corrected distance, composed as one `field.Ripple` + layout + text-over, plus the SS3 (`ESC O C`) application-cursor navigation gotcha. Authoritative implementation: `skills/tui-ui/examples/effort_selector.py`.
- [[hard-lessons]] — the ten rules for replicating real effects (get ground truth first, confirm scale, multi-frame, real-run verification, CRLF, isatty, UTF-8, self-drive with SmartCLI). Pointer to `skills/tui-ui/references/HARD-LESSONS.md`.
- [[rendering-model]] — the four-primitive kernel (CellField / SubcellRaster / BoxJunction / ColorModel) all widgets compose from; the `ASPECT=2.0` geometric truth. Pointer to `skills/tui-ui/references/RENDERING-MODEL.md`.

## Provenance note
The two pointer entries ([[hard-lessons]], [[rendering-model]]) summarize load-bearing documents that live with the tui-ui skill (`skills/tui-ui/references/`). They are marked **unsourced** in the web-URL sense — their authority is primary project experience, not an external citation. [[effort-selector]] points at SmartCLI's own verified replica (`skills/tui-ui/examples/effort_selector.py`) as its source of truth.
