# TerminalTextEffects (TTE) — the motion/animation architecture reference

A Python library of terminal text animations, but more valuable as a clean reference architecture for *temporal* animation: effects are iterators that yield ANSI frames.

**Source:** https://github.com/ChrisBuilds/terminaltexteffects (verified: `engine/motion.py`)

## How it works
- **Contract:** each effect is an iterator that yields ANSI frame strings. The driver just pulls frames.
- **Motion model:** a `Waypoint(coord, bezier_control)` names a target; a `Path` is a sequence of `Segment(start, end, distance)`. Total steps `max_steps = round(total_distance / speed)`.
- `step()` per frame: `t = step / max_steps` → `ease(t)` → `factor * total_distance` → find the active segment for that distance → lerp (or evaluate the bezier) to the coordinate. Crucially, **easing is applied over the whole path**, so motion flows across segment boundaries instead of restarting each segment.
- `double_row_diff=True` bakes character-aspect correction into path length (a vertical cell counts more).
- An "origin segment" stitches the character's current live position into the path so motion is continuous; events chain and loop paths.

## What to borrow
- **The architecture:** `speed → max_steps → eased t → coordinate`. Treat **Motion (temporal)** as a first-class axis alongside `CellField` (spatial) in [[rendering-model]].
- The iterator-yields-ANSI contract makes effects composable and non-blocking.
- Aspect correction belongs in the path metric, matching [[terminal-cell-aspect-ratio]].

## See also
- [[rendering-model]]
- [[terminal-cell-aspect-ratio]]
- [[flicker-free-rendering]]
