"""tui-ui — an HTML/CSS-like terminal layout engine + web-style widgets.

Design web-like UIs in the terminal (and inside tmux): a cell-grid Canvas, a CSS
box model (margin/border/padding/content), flexbox/grid layout with ``fr`` units,
and composable widgets (Panel, Table, Card, ProgressBar, Tabs, Tree, ...). Output
is a tmux-safe ANSI string — printable, composable, and renderable to PNG by the
pyte harness.

Quick start::

    from ui import Page, VStack, HStack, Panel, Table, get_theme
    theme = get_theme("dashboard")
    page = Page(VStack([Panel("hello", title="Hi", theme=theme)]), width=80, height=24)
    print(page.to_ansi())
"""
from __future__ import annotations

from .core import (BOX_STYLES, Canvas, Cell, Theme, THEMES, draw_border,
                   get_theme, gradient, parse_color, rgb, theme_names, width)
from .box import Box, Fr
from .layout import Grid, HStack, Page, Stack, VStack, grid, resolve_tracks
from . import registry

__all__ = [
    "Canvas", "Cell", "Theme", "THEMES", "BOX_STYLES", "draw_border",
    "get_theme", "theme_names", "gradient", "parse_color", "rgb", "width",
    "Box", "Fr", "VStack", "HStack", "Stack", "Grid", "grid", "Page",
    "resolve_tracks", "registry",
]
