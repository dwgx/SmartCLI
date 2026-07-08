# Box Model on a Cell Grid

**Statement:** Lay out widgets with a CSS-like box model where borders are whole cells, not strokes; four nested boxes (margin → border → padding → content) size everything in integer cells.

**Exact formulas:**
```
outer_w = margin_l + border_l + padding_l + content_w + padding_r + border_r + margin_r
outer_h = margin_t + border_t + padding_t + content_h + padding_b + border_b + margin_b

Each present border side consumes exactly 1 CELL. A border "adds two rows and two columns."
Padding order = CSS 4-tuple (top, right, bottom, left).
Margins collapse by taking the LARGER of adjacent margins (Textual behavior).
gutter = padding + border  (per axis).

box-sizing (Textual default = border-box, NOT content-box):
  border-box:  given width IS the border box;  content = width - gutter.
  content-box: given width is content;         border box = content + gutter.
```
Textual internals:
```python
class BoxModel(NamedTuple):
    width: Fraction   # content + padding + border
    height: Fraction
    margin: Spacing
# Widget._get_box_model():
gutter = styles.gutter                        # padding + border
if styles.box_sizing == "border-box":
    content_width  = resolved_width  - gutter.width
    content_height = resolved_height - gutter.height
```
Keep layout math in integer cells; keep fr/ratio intermediates as Fraction; floor cumulative offsets at placement.

**Source:** https://textual.textualize.io/guide/styles/ (border adds 2 rows/cols, padding order, margin collapse; box_model.py https://github.com/Textualize/textual/blob/main/src/textual/box_model.py ; MDN box model https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Styling_basics/Box_model — project research R7 §1)

**See also:** [[cell-grid-model]], [[fractional-space-distribution]], [[box-drawing-glyphs]], [[cell-width-measurement]]
