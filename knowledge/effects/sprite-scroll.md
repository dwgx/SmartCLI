# Sprite Scroll (moving glyph block)

The cheapest animated entity: a static multi-line ASCII block blitted at a moving `(x, y)` into a `CellGrid` in painter's order, with a small cycle of sub-frames for local motion (spinning wheels, flapping fins). This is `sl`'s whole trick and the base entity type in `asciiquarium`'s scene framework.

## Model
```
Sprite {
  frames: [ [multi-line glyph block], ... ]   # 2-3 sub-frames for sub-motion
  pos: (x, y)                                  # top-left cell of the block
  depth: int                                   # painter's order key (see color-mask-sprites)
}
each tick:
  x += dx                                      # scroll
  frame = frames[tick % len(frames)]           # cycle wheels/exhaust
  blit(frame, pos)                             # write block at offset, skip transparent cells
```
Blit = copy each non-transparent glyph of the block into `grid[y+r][x+c]`; painter's order (draw far→near) handles overlap without a pixel z-buffer.

## Borrow
A `Sprite` over `CellField` — write block at offset, painter's order for layering. Combine with [[color-mask-sprites]] for a parallel color layer, and an integer-`depth` sort for multi-sprite scenes. `sl` cycles 2–3 wheel frames to fake rotation while the whole train scrolls; the same split (global position vs. tiny local frame cycle) drives fish, birds, banners.

**Source:** https://github.com/mtoyoda/sl and https://github.com/cmatsuoka/asciiquarium (distilled in `../sources/deep-art.md` §10–11)

## See also
- [[sl]]
- [[asciiquarium]]
- [[color-mask-sprites]]
- [[cell-grid-model]]
