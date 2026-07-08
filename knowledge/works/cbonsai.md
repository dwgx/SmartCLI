# cbonsai — procedural ASCII bonsai generator

Grows a random ASCII bonsai tree via recursive branching, drawing character-by-character for a live "growing" animation.

**Source:** https://gitlab.com/jallbrit/cbonsai (verified: `cbonsai.c`)

## How it works
- Core is a recursive `branch(y, x, type, life)`. `lifeStart = 32`; `age = lifeStart - life`; a `multiplier = 5` scales growth energy.
- Five branch **types** each get a per-type dice-rolled `dx`/`dy`:
  - *trunk* — direction is age-dependent (leans then straightens),
  - *shootLeft* / *shootRight* — `d10` roll, alternate sides,
  - *dying* — `d15` with wide spread,
  - *dead* — small jitter.
- **Shoot spawning** is cooldown-gated: `shootCooldown = multiplier * 2`, alternating left/right, so side branches appear at a controlled rate rather than every step.
- **Glyphs** picked by movement direction: `/` `~` `\` `|` and combinations (`/|\`, `\|`); leaves are random glyphs from a set; growth is clamped at a ground line.
- Live mode: `nanosleep(0.03s)` between each drawn character.

## What to borrow
- A template for organic procedural forms: a turtle that walks into a `CellGrid` (mutable glyph buffer), *not* a per-frame math field. Recursion + per-type direction dice + cooldown-gated spawning generalizes to vines, lightning, coral, cracks.
- Direction→glyph selection is the moving-turtle cousin of a box-drawing junction table.

## See also
- [[procedural-branching]]
- [[box-drawing-glyphs]]
- [[cell-grid-model]]
- [[rendering-model]]
