# Conway's Game of Life (B3/S23)

A cellular automaton on a grid where each cell lives or dies each generation based on its 8 Moore neighbors, following the birth-3 / survive-2-or-3 rule.

## Formula / params
- Neighborhood: 8-cell Moore (orthogonal + diagonal).
- Rules:
  - Live cell with < 2 live neighbors dies (underpopulation).
  - Live cell with 2 or 3 live neighbors survives.
  - Live cell with > 3 live neighbors dies (overpopulation).
  - Dead cell with exactly 3 live neighbors becomes live (reproduction).
- Rule string: B3/S23.
- Ramp: live `#` / `O`, dead ` ` / `.`.

## Source
Source: https://en.wikipedia.org/wiki/Conway%27s_Game_of_Life

## See also
- [[ascii-luminance-ramp]]
