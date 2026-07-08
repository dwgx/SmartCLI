# Palette: viridis

Matplotlib's perceptually-uniform default sequential colormap; representative stops (dark purple → yellow).

- Exact hex anchors: `#440154 #414487 #2A788E #22A884 #7AD151 #FDE725`.

## Usage
Treat the anchors as gradient stops on a normalized scalar `t ∈ [0,1]` (6 stops → segment `i = floor(t*5)`, local `f = t*5 − i`), then blend adjacent stops with [[color-interpolation]] (per-channel lerp; blend in linear-light for accuracy). Perceptual uniformity means equal `t` steps read as equal brightness steps — ideal for heatmaps, luminance ramps, and any scalar→color mapping where banding must be invisible. The full matplotlib table has 256 entries; these 6 anchors reconstruct it closely under linear interpolation.

**Source:** https://github.com/matplotlib/matplotlib/blob/main/lib/matplotlib/_cm_listed.py

**See also:** [[color-interpolation]], [[palette-solarized]], [[palette-synthwave84]]
