"""preview_pane.py — content preview widget (fzf --preview style).

The natural companion to a fuzzy list: show the content of the selected item in
a side pane, with an optional title bar and line numbers. A drop-in tui-ui
widget; renders text content to a Canvas, wrapping/clipping to the region.
"""
from __future__ import annotations

from typing import Optional

from ..core import Canvas, DIM, BOLD
from ..registry import register
from ..widgets import Widget


@register
class PreviewPane(Widget):
    """A titled pane that previews multi-line text content with line numbers.

    Pair it with fuzzy_filter_list: as the selection changes, feed the selected
    item's content in as ``content``. Long lines are clipped; a scroll offset
    keeps a target line in view.
    """
    key = "preview_pane"
    summary = "content preview pane (title + line numbers), pairs with fuzzy list"

    def __init__(self, content: str = "", title: str = "", top: int = 0,
                 line_numbers: bool = True, width: Optional[int] = None,
                 height: Optional[int] = None, theme=None):
        from ..core import get_theme
        self.content = content
        self.title = title
        self.top = top                    # first visible line (scroll offset)
        self.line_numbers = line_numbers
        self.width = width
        self.height = height
        self.theme = theme or get_theme("dashboard")

    def measure(self, avail_w, avail_h):
        return (self.width or avail_w, self.height or avail_h)

    def render(self, region_w, region_h):
        th = self.theme
        cv = Canvas(region_w, max(1, region_h), bg=th.bg)
        y = 0
        body_top = 0
        if self.title:
            accent = getattr(th, "accent", th.fg)
            cv.fill_rect(0, 0, region_w, 1, " ", fg=th.fg, bg=th.bg)
            cv.put_text(0, 0, self.title[:region_w], fg=accent, bg=th.bg, attrs=BOLD)
            body_top = 1
        lines = self.content.split("\n")
        gutter = 0
        if self.line_numbers and lines:
            gutter = len(str(len(lines))) + 1     # width of the line-number column
        n_body = region_h - body_top
        top = max(0, self.top)              # negative scroll would wrap via -index
        for i in range(n_body):
            li = top + i
            if li >= len(lines):
                break
            y = body_top + i
            x = 0
            if self.line_numbers:
                num = str(li + 1).rjust(gutter - 1)
                cv.put_text(0, y, num, fg=th.fg, bg=th.bg, attrs=DIM)
                x = gutter
            cv.put_text(x, y, lines[li][:max(0, region_w - x)], fg=th.fg, bg=th.bg)
        return cv

    @classmethod
    def sample(cls, theme):
        content = ("def render(self, ctx):\n"
                   "    grid = new_grid(w, h)\n"
                   "    for cell in cells:\n"
                   "        grid[y][x] = shade(cell)\n"
                   "    return grid_to_str(grid)\n"
                   "\n"
                   "# preview pane pairs with the\n"
                   "# fuzzy list to the left.")
        return cls(content, title="src/core/render.py", theme=theme)
