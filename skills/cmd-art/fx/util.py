"""Shared frame-assembly helpers: colored grids, ANSI-aware padding, ramps.

Effects build a (char, color) grid; :func:`grid_to_str` turns it into a frame
string emitting a truecolor escape ONLY when the color changes between adjacent
cells (the single biggest output-size optimization for full-screen effects).
"""
from __future__ import annotations

import re

from .core import RESET, rgb

RGB = tuple[int, int, int]

_ANSI_RE = re.compile(r"\x1b\[[0-9;:]*[A-Za-z]")


def new_grid(width: int, height: int):
    """height x width grid of ``None`` cells. Cell = None | (char, RGB | None)."""
    return [[None] * width for _ in range(height)]


def grid_to_str(grid, bg: bool = False) -> str:
    """Join a cell grid into a frame string with minimal color escapes.

    Cells: ``None`` -> plain space; ``(ch, None)`` -> uncolored char;
    ``(ch, (r,g,b))`` -> truecolor char. Every row ends with RESET so partial
    rows never bleed color into the next line. ``bg=True`` colors backgrounds.
    """
    lines = []
    for row in grid:
        parts = []
        last = None
        for cell in row:
            if cell is None:
                if last is not None:
                    parts.append(RESET)
                    last = None
                parts.append(" ")
                continue
            ch, color = cell
            if color != last:
                parts.append(RESET if color is None else rgb(*color, bg=bg))
                last = color
            parts.append(ch)
        parts.append(RESET)
        lines.append("".join(parts))
    return "\n".join(lines)


def visible_len(line: str) -> int:
    """Length of *line* in terminal cells, ignoring ANSI escapes.

    Assumes single-width glyphs (true for the ASCII/box/block chars we emit).
    """
    return len(_ANSI_RE.sub("", line))


def pad_visible(line: str, width: int) -> str:
    """Right-pad *line* with spaces to *width* visible cells (no truncation)."""
    gap = width - visible_len(line)
    return line + (" " * gap if gap > 0 else "")


def frame_lines(frame: str, height: int, width: int) -> list[str]:
    """Split a frame into exactly *height* lines, each padded to *width* cells."""
    lines = frame.split("\n")[:height]
    while len(lines) < height:
        lines.append("")
    return [pad_visible(ln, width) for ln in lines]


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v
