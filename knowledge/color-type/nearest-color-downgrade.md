# Nearest-Color Downgrade (tmux colour.c)

Map a truecolor RGB value down to the closest 256-color index by comparing the best cube candidate against the best grayscale candidate and picking whichever has the smaller squared-Euclidean distance.

- Distance metric: `(R-r)² + (G-g)² + (B-b)²`.
- Cube quantizer per channel value `v`: `v<48 → 0; v<114 → 1; else (v-35)/40`.
- Grayscale candidate: `avg = (r+g+b)/3; idx = avg>238 ? 23 : (avg-3)/10; grey = 8 + 10*idx`.
- Compute both the quantized cube color and the grayscale color, then choose the candidate with the smaller distance to the original.

**Source:** https://github.com/tmux/tmux/blob/master/colour.c

**See also:** [[256-color-cube]], [[truecolor-24bit]]
