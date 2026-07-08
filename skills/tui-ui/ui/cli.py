"""ui CLI: widgets | demo | gallery.

Run as a package from ``skills/tui-ui``::

    python -m ui widgets
    python -m ui demo table --width 80 --height 12 --theme dashboard
    python -m ui gallery --width 120 --height 40

or by path (the PEP-366 prelude makes the direct form work from any cwd)::

    python skills/tui-ui/ui/cli.py gallery

Every command renders ONCE to stdout and exits — bounded, no loop. Output is a
tmux-safe ANSI string (SGR + newlines) you can pipe, print, or feed to the
pyte->PNG harness.
"""
from __future__ import annotations

import os
import sys

if __package__ in (None, ""):  # executed by path: bootstrap the ui package
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "ui"
    import ui  # noqa: F401

import argparse

from . import registry
from .box import Box, Fr
from .core import get_theme, theme_names
from .layout import Grid, HStack, Page, VStack, grid


def _ensure_utf8():
    try:
        enc = (getattr(sys.stdout, "encoding", "") or "").lower()
        if enc.replace("-", "") not in ("utf8", "utf8mb4"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _enable_vt():
    _ensure_utf8()
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)
            import ctypes as _c
            mode = _c.c_uint32()
            if k.GetConsoleMode(h, _c.byref(mode)):
                k.SetConsoleMode(h, mode.value | 0x0001 | 0x0004)
        except Exception:
            os.system("")


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def cmd_widgets(args) -> int:
    widgets = registry.all_widgets()
    if args.json:
        import json
        print(json.dumps([{"key": w.key, "summary": getattr(w, "summary", "")}
                          for w in widgets], indent=2))
    else:
        wkey = max((len(w.key) for w in widgets), default=4)
        for w in widgets:
            print(f"{w.key:<{wkey}}  {getattr(w, 'summary', '')}")
    for mod, _tb in registry.load_errors():
        print(f"warning: {mod} failed to import", file=sys.stderr)
    return 0


def cmd_demo(args) -> int:
    _enable_vt()
    theme = get_theme(args.theme)
    try:
        cls = registry.get(args.name)
    except KeyError as exc:
        raise SystemExit(f"error: {exc.args[0]}")
    widget = cls.sample(theme)
    # Wrap in a titled panel-ish box so the demo shows the widget in context.
    page = Page(Box(content=widget, padding=(0, 0), bg=theme.bg),
                width=args.width, height=args.height, bg=theme.bg)
    print(page.to_ansi())
    return 0


def _build_gallery(theme, width, height):
    """Compose a web-like dashboard 'page' from several widgets.

    Layout (top->bottom): a banner header, a badge status row, a middle region
    (left column = Resources meter + Files tree; right = Services table), a Tabs
    detail panel, and a Deploy progress footer. Fixed heights are chosen so each
    bordered box gets enough rows; the middle table flexes to fill the width.
    """
    from .widgets import (Badge, Banner, Meter, ProgressBar, Table, Tabs, Tree)

    def panel(content, title, h=None, border="single", w=None):
        return Box(content=content, border=border, title=title, padding=(0, 1),
                   bg=theme.bg, fg=theme.fg, border_fg=theme.border,
                   height=h, width=w if w is not None else "auto")

    banner = Banner("DASH", theme=theme)
    bh = banner.measure(width, 10)[1]
    header = Box(content=banner, padding=(0, 1), border="rounded",
                 border_fg=theme.accent, bg=theme.bg, height=bh + 2)

    status_row = Box(content=HStack([
        Box(content=Badge("ONLINE", kind="ok", theme=theme), bg=theme.bg, width="auto"),
        Box(content=Badge("3 ALERTS", kind="warn", theme=theme), bg=theme.bg, width="auto"),
        Box(content=Badge("v2.4.1", kind="accent", theme=theme), bg=theme.bg, width="auto"),
    ], gap=1), bg=theme.bg, height=1)

    resources = panel(Meter(theme=theme), "Resources", h=5)
    filetree = panel(Tree(theme=theme), "Files", h=Fr(1))
    services = panel(Table(theme=theme), "Services", w=Fr(1))
    mid = HStack([VStack([resources, filetree], gap=0), services], gap=1)

    tabs = panel(Tabs.sample(theme), "Details", h=6, border="rounded")
    footer = panel(ProgressBar(0.73, label="Deploy", theme=theme), "Progress",
                   h=3, border="rounded")

    # Give the middle region the leftover rows so nothing clips.
    fixed = (bh + 2) + 1 + 6 + 3
    mid_h = max(6, height - fixed)
    mid_box = Box(content=mid, bg=theme.bg, height=mid_h)

    root = VStack([header, status_row, mid_box, tabs, footer], gap=0, bg=theme.bg)
    return Page(root, width=width, height=height, bg=theme.bg)


def cmd_gallery(args) -> int:
    _enable_vt()
    theme = get_theme(args.theme)
    page = _build_gallery(theme, args.width, args.height)
    print(page.to_ansi())
    return 0


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ui",
        description="HTML/CSS-like terminal layout engine + web-style widgets.")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("widgets", help="list registered widgets")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_widgets)

    sp = sub.add_parser("demo", help="render one widget sample to stdout")
    sp.add_argument("name", help="widget key (see 'widgets')")
    sp.add_argument("--width", type=int, default=60)
    sp.add_argument("--height", type=int, default=12)
    sp.add_argument("--theme", help=f"palette ({', '.join(theme_names())})")
    sp.set_defaults(func=cmd_demo)

    sp = sub.add_parser("gallery", help="render a composed dashboard 'page'")
    sp.add_argument("--width", type=int, default=100)
    sp.add_argument("--height", type=int, default=30)
    sp.add_argument("--theme", help=f"palette ({', '.join(theme_names())})")
    sp.set_defaults(func=cmd_gallery)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    registry.load_all()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
