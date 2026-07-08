# GitHub Copilot CLI banner — "From pixels to characters"

The engineering story behind Copilot CLI's animated ASCII startup banner. Despite the title, there is **no image pipeline** — frames are hand-authored and colored by a semantic-role map.

**Source:** https://github.blog/engineering/from-pixels-to-characters-the-engineering-behind-github-copilot-clis-animated-ascii-banner/

## How it works
- Frames are hand-authored in a Photoshop-like ANSI editor (open-sourced as **Ascii-Motion**).
- Each frame = `{ title, duration_ms, content: string, colors: Record<"row,col", role> }` — the glyph content is one string; color is a **separate** map from `"row,col"` to a *semantic role*.
- At render: truncate each line to 80 columns → resolve each character's color from its role → **run-length group** consecutive same-color chars into segments → emit via Ink `<Text color>` nodes.
- Colors are **4-bit ANSI semantic roles** (`eyes`, `head`, `goggles`, `border`, `block_text`, …) with dark/light theme tables — *not* truecolor. Terminals remap 4-bit palettes by theme, so it degrades gracefully.
- Prototype loop: `readline.cursorTo(0,0)` + `clearScreenDown` + `setInterval(75ms ≈ 13 fps)`.
- Gated to under 3 seconds, opt-in, and **skipped entirely under `--screen-reader`**.

## What to borrow
- Separate the **content string** from a `"row,col" → semantic-role` color map instead of baking hues into the art.
- **4-bit semantic roles** + dark/light theme tables for graceful, theme-aware degradation (contrast the truecolor approach and [[256-color-cube]]).
- Run-length segment batching to cut the number of escape writes.
- Accessibility + duration gating as a first-class banner concern.

## See also
- [[256-color-cube]]
- [[ansi-sgr-color]]
- [[color-mask-sprites]]
- [[react]]
