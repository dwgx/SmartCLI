# Textual — CSS box model on a cell grid

A Python TUI framework that puts a real CSS box model, grid layout, and a compositor over the terminal cell grid.

**Source:** https://github.com/Textualize/textual

## How it works
- **Box model:** `border-box` by default — padding and border subtract from the content area (not added outside). Margins **collapse** to the greater of adjacent margins, not the sum.
- **Fractional units:** `fr` = available space ÷ Σ(fr). Grid resolves fixed + `%` + `auto` tracks first, then divides the leftover among `fr` tracks. `grid-gutter` sits on the container, spans on the child, and too-few track values cycle across cells.
- **Compositor:** "switches the primitive" — it composites `Segment`s, not a char grid: find-cuts → apply-cuts → discard-occluded → combine. A **Spatial Map** buckets widgets into 100×20 tiles for near-constant-time culling of what overlaps a region.
- **Animation:** `animate(attr, duration|speed, easing=in_out_cubic, on_complete)` runs non-blocking.
- **Input:** a key binding search **bubbles up the DOM** to the App; `priority=True` bindings are checked first. Mouse: `Click` > Down/Up; `Enter`/`Leave` bubble; `capture_mouse()` locks the target.

## What to borrow
- The whole box-model + grid + `fr` rule set as SmartCLI's layout semantics ([[box-model-on-cell-grid]], [[fractional-space-distribution]]).
- DOM-bubbling key resolution with a priority tier for input dispatch.
- Compositor + spatial-map for correctly (and cheaply) layering overlapping widgets ([[rendering-model]]).

## See also
- [[box-model-on-cell-grid]]
- [[fractional-space-distribution]]
- [[rendering-model]]
- [[flicker-free-rendering]]
