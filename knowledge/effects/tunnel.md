# Tunnel

An infinite textured tunnel produced by precomputing per-pixel distance and angle tables into a wrapped texture, then animating texture offsets over time.

## Formula / params
- Constant: `ratio = 32`.
- Distance table: `distance = int(ratio * texHeight / sqrt((x-w/2)^2 + (y-h/2)^2)) % texHeight`.
- Angle table: `angle = int(0.5 * texWidth * atan2(y-h/2, x-w/2) / PI)`.
- Animation offsets: `shiftX = int(texWidth * 1.0 * anim)`, `shiftY = int(texHeight * 0.25 * anim)`.
- Sample: `texture[(distance + shiftX) % texWidth][(angle + shiftY) % texHeight]`.
- Ramp: map texel to ` .:-=+*#`.

## Source
Source: https://lodev.org/cgtutor/tunnel.html

## See also
- [[plasma]]
- [[ascii-luminance-ramp]]
