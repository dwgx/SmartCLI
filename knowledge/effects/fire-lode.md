# Fire (Lode cooling-buffer)

A classic fire effect: seed a hot random bottom row, then repeatedly average each cell with the cells below it using a divisor slightly greater than 4 so heat cools as it rises.

## Formula / params
- Seed bottom row: `fire[h-1][x] = abs(32768 + rand()) % 256`.
- Propagation kernel:
  `fire[y][x] = ((fire[y+1][x-1] + fire[y+1][x] + fire[y+1][x+1] + fire[y+2][x]) * 32) / 129`.
- The divisor 129 gives ~4.0155 (> 4), which is the cooling factor; there is no separate subtractive decay term.
- Ramp: ` .:*oO&8#@`.

## Source
Source: https://lodev.org/cgtutor/fire.html

## See also
- [[fire-doom-psx]]
- [[ascii-luminance-ramp]]
