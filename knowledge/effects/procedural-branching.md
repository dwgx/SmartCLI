# Procedural Branching (stochastic turtle growth)

A turtle walks into a mutable `CellGrid` writing glyphs, its direction chosen by per-type dice rolls, with recursive side-branches gated by a cooldown. The reusable skeleton behind trees, lightning, vines, coral, and cracks — organic form as a stochastic walk, **not** a per-frame math field.

## The recursion
```
branch(y, x, type, life):
  while life > 0:
    life--
    age = lifeStart - life            # lifeStart = 32
    (dx, dy) = setDeltas(type, age, life, multiplier)   # multiplier = 5 scales all thresholds
    if dy > 0 and y > maxY-2: dy--     # ground clamp
    y += dy; x += dx
    glyph = chooseString(type, dx, dy) # direction -> /  ~  \  |  /|\  \|
    grid[y][x] = glyph
    maybe_recurse(...)                 # cooldown-gated side shoots
```

## Direction dice (`setDeltas`, 5 types)
- **trunk** — age-dependent: young leans (`d10 → dx∈-2..+2`), mid straightens (`dx = rand()%3-1`); `dy=-1` on an age cadence.
- **shootLeft / shootRight** — `d10` biased sideways, mirrored dx; alternate sides.
- **dying** — `d15` with a wide `dx∈-3..+3` spread.
- **dead** — small `rand()%3-1` jitter.

## Cooldown-gated branching
`shootCooldown` starts at `multiplier` and decrements each loop. A trunk spawns a shoot only when `shootCooldown ≤ 0` (then resets to `multiplier*2`), so side branches appear at a controlled rate instead of every step. New trunks fork on `rand()%8==0 && life>7`.

## Borrow
The type-switch + dice-roll `dx/dy` + cooldown-gated recursion is a drop-in `ProceduralWalk` primitive for any branching organic form. Direction→glyph selection is the moving-turtle cousin of a [[box-drawing-glyphs]] junction table. Draw live by `nanosleep(0.03s)` between glyphs for a visible grow.

**Source:** https://gitlab.com/jallbrit/cbonsai (verified `cbonsai.c`; distilled in `../sources/deep-art.md` §3)

## See also
- [[cbonsai]]
- [[box-drawing-glyphs]]
- [[cell-grid-model]]
- [[rendering-model]]
