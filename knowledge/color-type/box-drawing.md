# Box-Drawing (U+2500..U+257F)

The 128-character Unicode box-drawing block, in light/heavy/double weights plus rounded arcs, used to compose frames, tables, and tree connectors.

- **Light:** ─ 2500  │ 2502  ┌ 250C  ┐ 2510  └ 2514  ┘ 2518; junctions ├ 251C  ┤ 2524  ┬ 252C  ┴ 2534  ┼ 253C
- **Double:** ═ 2550  ║ 2551  ╔ 2554  ╗ 2557  ╚ 255A  ╝ 255D; junctions ╠ 2560  ╣ 2563  ╦ 2566  ╩ 2569  ╬ 256C
- **Heavy:** ━ 2501  ┃ 2503  ┏ 250F  ┓ 2513  ┗ 2517  ┛ 251B; junctions ┣ 2523  ┫ 252B  ┳ 2533  ┻ 253B  ╋ 254B
- **Rounded arc:** ╭ 256D  ╮ 256E  ╰ 2570  ╯ 256F

Auto-connecting: compute each cell's 4-edge bitmask (up/down/left/right plus weight) and map to the matching glyph — e.g. left+right = ─, +down = ┬, all four = ┼. Mixed light/heavy junctions occupy U+251C..U+254B.

**Source:** https://www.unicode.org/charts/PDF/U2500.pdf and https://en.wikipedia.org/wiki/Box-drawing_characters

**See also:** [[image-to-ansi-halfblock]], [[wcwidth-east-asian-width]], [[figlet-flf-spec]]
