# HSV Rainbow Cycling (lolcat)

Generate a smooth rainbow by driving RGB from three phase-shifted sine waves as a function of character position.

- `red   = sin(freq*i) * 127 + 128`
- `green = sin(freq*i + 2π/3) * 127 + 128`
- `blue  = sin(freq*i + 4π/3) * 127 + 128`
- Position seed: `@os + i/spread` (per-character offset).
- Defaults: `freq = 0.1`, `spread = 3.0`.

**Source:** https://github.com/busyloop/lolcat/blob/master/lib/lolcat/lol.rb

**See also:** [[color-interpolation]], [[truecolor-24bit]]
