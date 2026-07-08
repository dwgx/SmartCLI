# Fractional Space Distribution (fr / ratio)

**Statement:** Distribute flexible space (`fr` / ratio tracks) with a carry-remainder or cumulative-floor pass, never by rounding each track independently, or totals drift by ±1 cell.

**Exact algorithms:**
```
Subtract fixed sizes first; flexible tracks share the remainder by weight; lock any
min/max violation and repeat the pass until stable.

(a) Rich ratio_resolve(total, edges) — carry-remainder:
    remaining = total - sum(fixed)
    portion   = Fraction(remaining, sum(ratios of flexible))
    for each flexible edge:
        size, remainder = divmod(portion * ratio + remainder, 1)   # carry remainder forward
    # total=10, ratios [1,1,1] -> [3,3,4]

(b) Textual _resolve.resolve — cumulative-floor:
    remaining      = total - gutter_total - consumed_fixed
    fraction_unit  = Fraction(remaining) / sum(fr_values)
    offsets        = [0] + [floor(acc) for acc in accumulate(w1,gap,w2,gap,...)]
    widths[i]      = offsets[i+1] - offsets[i]
    # 10 cells, 1fr 1fr 1fr -> offsets [0,3,6,10] -> widths [3,3,4]
```
Flexbox-style grow/shrink (practical form):
```
base = fixed_or_preferred; free = container - sum(base)
free > 0: child = base + remainder_distribute(free * grow / sum(grow))          # grow
free < 0: child = base - remainder_distribute(|free| * shrink*base / sum(shrink*base))  # shrink, clamp to min, repeat
```
Alignment (extra cell goes right/bottom, matches Rich Align):
`left=0 ; center=(box_w-content_w)//2 ; right=box_w-content_w`.

**Source:** https://github.com/Textualize/rich/blob/main/rich/_ratio.py (ratio_resolve/ratio_distribute; Textual _resolve https://github.com/Textualize/textual/blob/main/src/textual/_resolve.py ; W3C CSS Grid fr https://www.w3.org/TR/css-grid-1/ — project research R7 §2)

**See also:** [[box-model-on-cell-grid]], [[cell-grid-model]], [[cell-width-measurement]]
