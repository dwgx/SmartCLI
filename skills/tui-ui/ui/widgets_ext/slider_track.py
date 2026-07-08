"""slider_track.py — a thin SOLID track with a ▲ position marker + tick labels.

WHY
---
A discrete selector (the ``/effort`` stage rail: low·medium·high·xhigh·max┊ultracode)
needs three things drawn in register: a thin *solid* rail, a triangle marker sitting
directly under the currently-selected stop, and the stage labels spread beneath at
their own columns. Codex rendered the rail as dashed/segmented; the real thing is a
single unbroken ``─``. This widget owns that composition so any picker/slider can
reuse it: a horizontal solid line (optionally two-tone with a dotted ``┊`` divider),
a ``▲``/``△`` marker at a chosen stop, and an optional row of labels.

Positions can be given two ways:
  * ``positions`` — explicit cell columns for each stop (what /effort needs: the
    stages are NOT evenly spaced and a ``┊`` separator eats a column). This is the
    load-bearing mode for the replica.
  * else evenly distributed across ``[0, width)`` by ``count``/``labels``.

Params
------
* ``labels``       : stop labels (drawn on the label row under the track).
* ``positions``    : explicit marker column per stop (len == labels); optional.
* ``selected``     : index of the active stop → marker column + label highlight.
* ``width``        : track cell width (default: fill region).
* ``track_color``  : rail color (left/main segment).
* ``track_color2`` : optional 2nd rail color for cells at/after ``divider_col``.
* ``divider_col``  : column to draw a dotted ``┊`` separator (e.g. /effort col 73
                     relative to track origin); also splits the two track colors.
* ``divider_color``: color of the ``┊``.
* ``marker``       : marker glyph (default filled ``▲``; ``△`` for hollow).
* ``marker_color`` : marker color; defaults to the selected label's accent.
* ``label_colors`` : optional per-stop RGB for labels (else fg / muted).
* ``track_start``  : x offset where the rail begins within the region (default 0).

Rows rendered: track (row 0), marker (row 1), labels (row 2).
"""
from __future__ import annotations

from typing import Optional, Sequence

from .. import core
from ..core import BOLD, Canvas, parse_color
from ..core import width as cell_width
from ..registry import register
from ..widgets import Widget


@register
class SliderTrack(Widget):
    """A thin solid rail + ▲ marker at a fractional/explicit stop + tick labels."""
    key = "slider_track"
    summary = "Thin solid slider rail with ▲ marker and tick labels"

    TRACK_ROW = 0
    MARKER_ROW = 1
    LABEL_ROW = 2

    def __init__(self, labels: Sequence[str] = ("low", "mid", "high"), *,
                 positions: Optional[Sequence[int]] = None, selected: int = 0,
                 width: Optional[int] = None, track_char: str = "─",
                 track_color=None, track_color2=None,
                 divider_col: Optional[int] = None, divider_char: str = "┊",
                 divider_color=None, marker: str = "▲", marker_color=None,
                 label_colors: Optional[Sequence] = None, track_start: int = 0,
                 show_labels: bool = True, theme=None):
        super().__init__(theme)
        self.labels = list(labels)
        self.positions = list(positions) if positions is not None else None
        self.selected = max(0, min(selected, len(self.labels) - 1)) if self.labels else 0
        self.width = width
        self.track_char = track_char[:1] or "─"
        self.track_color = parse_color(track_color) if track_color is not None else self.theme.muted
        self.track_color2 = parse_color(track_color2) if track_color2 is not None else None
        self.divider_col = divider_col
        self.divider_char = divider_char[:1] or "┊"
        self.divider_color = parse_color(divider_color) if divider_color is not None else self.theme.muted
        self.marker = marker[:1] or "▲"
        self.marker_color = parse_color(marker_color) if marker_color is not None else None
        self.label_colors = ([parse_color(c) if c is not None else None for c in label_colors]
                             if label_colors is not None else None)
        self.track_start = track_start
        self.show_labels = show_labels

    # -- geometry ----------------------------------------------------------
    def _track_width(self, region_w: int) -> int:
        return (self.width or region_w) - self.track_start

    def marker_col(self, region_w: int) -> int:
        """Absolute column of the marker for the selected stop (public helper)."""
        if not self.labels:
            return self.track_start
        if self.positions is not None:
            return self.positions[self.selected]
        tw = max(1, self._track_width(region_w))
        n = len(self.labels)
        frac = 0.0 if n <= 1 else self.selected / (n - 1)
        return self.track_start + int(round(frac * (tw - 1)))

    def measure(self, avail_w, avail_h):
        if self.positions is not None:
            w = max(self.positions) + 2
        else:
            w = self.width or avail_w
        return (max(8, w), 3 if self.show_labels else 2)

    def render(self, region_w, region_h):
        cv = Canvas(region_w, max(2, region_h), bg=self.theme.bg)
        tw = self._track_width(region_w)

        # -- track row: solid rail, optional two-tone split at divider_col --
        for i in range(max(0, tw)):
            x = self.track_start + i
            if x >= region_w:
                break
            if self.divider_col is not None and x == self.divider_col:
                cv.set(x, self.TRACK_ROW, self.divider_char, fg=self.divider_color, bg=self.theme.bg)
                continue
            col = self.track_color
            if self.track_color2 is not None and self.divider_col is not None and x > self.divider_col:
                col = self.track_color2
            cv.set(x, self.TRACK_ROW, self.track_char, fg=col, bg=self.theme.bg)

        # -- marker row: single ▲ under the selected stop -------------------
        mcol = self.marker_col(region_w)
        sel_color = self._label_color(self.selected, selected=True)
        mk_color = self.marker_color or sel_color
        if 0 <= mcol < region_w:
            cv.set(mcol, self.MARKER_ROW, self.marker, fg=mk_color, bg=self.theme.bg, attrs=BOLD)

        # -- label row: stage names, selected = bold + accent --------------
        if self.show_labels and region_h > self.LABEL_ROW:
            for i, label in enumerate(self.labels):
                is_sel = (i == self.selected)
                color = self._label_color(i, selected=is_sel)
                lw = cell_width(label)
                if self.positions is not None:
                    start = self.positions[i] - lw // 2      # center on the stop col
                else:
                    start = self.marker_col_for(i, region_w) - lw // 2
                start = max(0, start)
                cv.put_text(start, self.LABEL_ROW, label, fg=color, bg=self.theme.bg,
                            attrs=BOLD if is_sel else 0)
        return cv

    def marker_col_for(self, index: int, region_w: int) -> int:
        if self.positions is not None:
            return self.positions[index]
        tw = max(1, self._track_width(region_w))
        n = len(self.labels)
        frac = 0.0 if n <= 1 else index / (n - 1)
        return self.track_start + int(round(frac * (tw - 1)))

    def _label_color(self, index: int, *, selected: bool) -> core.RGB:
        if self.label_colors is not None and self.label_colors[index] is not None:
            return self.label_colors[index]
        return self.theme.accent if selected else self.theme.muted

    @classmethod
    def sample(cls, theme):
        return cls(["low", "medium", "high", "xhigh", "max"], selected=2, theme=theme)
