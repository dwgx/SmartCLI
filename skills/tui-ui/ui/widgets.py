"""widgets.py — web-style widgets as renderables.

Every widget implements the engine protocol:

    measure(avail_w, avail_h) -> (min_w, natural_h)   # cell size it wants
    render(region_w, region_h) -> Canvas              # exact-size cell grid

so widgets drop into any Box / VStack / HStack / Grid / Page. Optional ``width``
/``height`` attributes let a parent stack treat a widget as fixed or ``fr``.

Catalog: Panel, Table, Card, ProgressBar, Meter, Tabs, KeyValueList, Tree, Rule,
Badge, Banner. Each self-registers via :mod:`ui.registry` so ``python -m ui
widgets`` discovers them and ``demo <name>`` renders a sample.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import core
from .core import (BAR_EIGHTHS, BAR_FULL, BOLD, DIM, REVERSE, Canvas, Theme,
                   get_theme, parse_color)
from .core import width as cell_width
from .box import Box
from .registry import register


def _wrap_words(text: str, width_cells: int) -> list[str]:
    """Word-wrap *text* to *width_cells*, folding over-long words (Rich-ish)."""
    if width_cells <= 0:
        return [""]
    out: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            cand = word if not line else line + " " + word
            if cell_width(cand) <= width_cells:
                line = cand
                continue
            if line:
                out.append(line)
            # fold a word longer than the line
            while cell_width(word) > width_cells:
                out.append(core.slice_cells(word, width_cells))
                word = word[len(core.slice_cells(word, width_cells)):]
            line = word
        out.append(line)
    return out or [""]


class Widget:
    """Base widget with a theme slot and sensible measure defaults."""
    width = None
    height = None

    def __init__(self, theme: Optional[Theme] = None):
        self.theme = theme or get_theme(None)

    def measure(self, avail_w: int, avail_h: int) -> tuple[int, int]:
        return (avail_w, 1)

    def render(self, region_w: int, region_h: int) -> Canvas:  # pragma: no cover
        raise NotImplementedError

    # sample used by `demo`/`gallery`; override per widget
    @classmethod
    def sample(cls, theme: Theme) -> "Widget":
        return cls(theme=theme)


# ==========================================================================
# Rule / Divider
# ==========================================================================
@register
class Rule(Widget):
    """A horizontal divider filling the width, with an optional aligned title."""
    key = "rule"
    summary = "Horizontal divider line with optional title"

    def __init__(self, title: str = "", *, char: str = "─", align: str = "center",
                 fg=None, theme=None):
        super().__init__(theme)
        self.title = title
        self.char = char
        self.align = align
        self.fg = fg

    def measure(self, avail_w, avail_h):
        return (max(cell_width(self.title) + 4, 8), 1)

    def render(self, region_w, region_h):
        fg = parse_color(self.fg) if self.fg is not None else self.theme.border
        cv = Canvas(region_w, max(1, region_h), bg=self.theme.bg)
        if not self.title:
            cv.put_text(0, 0, self.char * region_w, fg=fg)
            return cv
        label = " " + self.title + " "
        lw = cell_width(label)
        if lw >= region_w:
            cv.put_text(0, 0, core.truncate(self.title, region_w), fg=self.theme.fg)
            return cv
        rest = region_w - lw
        if self.align == "left":
            left, right = 1, rest - 1
        elif self.align == "right":
            left, right = rest - 1, 1
        else:
            left = rest // 2
            right = rest - left
        cv.put_text(0, 0, self.char * left, fg=fg)
        cv.put_text(left, 0, label, fg=self.theme.fg, attrs=BOLD)
        cv.put_text(left + lw, 0, self.char * right, fg=fg)
        return cv

    @classmethod
    def sample(cls, theme):
        return cls("Section Divider", theme=theme)


# ==========================================================================
# Badge / Pill
# ==========================================================================
@register
class Badge(Widget):
    """A small inline label chip: ``[ label ]`` or inverse-video pill."""
    key = "badge"
    summary = "Inline status label / pill"

    def __init__(self, label: str = "OK", *, kind: str = "accent",
                 pill: bool = True, theme=None):
        super().__init__(theme)
        self.label = label
        self.kind = kind
        self.pill = pill

    def _color(self):
        return {"ok": self.theme.ok, "warn": self.theme.warn,
                "err": self.theme.err, "accent": self.theme.accent,
                "muted": self.theme.muted}.get(self.kind, self.theme.accent)

    def _text(self):
        return f" {self.label} " if self.pill else f"[{self.label}]"

    def measure(self, avail_w, avail_h):
        return (cell_width(self._text()), 1)

    def render(self, region_w, region_h):
        cv = Canvas(region_w, max(1, region_h), bg=self.theme.bg)
        color = self._color()
        text = self._text()
        if self.pill:
            cv.put_text(0, 0, text, fg=self.theme.bg, bg=color, attrs=BOLD)
        else:
            cv.put_text(0, 0, text, fg=color, attrs=BOLD)
        return cv

    @classmethod
    def sample(cls, theme):
        return cls("PASSED", kind="ok", theme=theme)


# ==========================================================================
# Panel
# ==========================================================================
@register
class Panel(Widget):
    """A bordered frame with a title and a (word-wrapped) body."""
    key = "panel"
    summary = "Bordered frame with title + body text"

    def __init__(self, body="", *, title: str = "", border: str = "rounded",
                 title_align="left", padding=(0, 1), theme=None,
                 body_fg=None, border_fg=None):
        super().__init__(theme)
        self.body = body
        self.title = title
        self.border = border
        self.title_align = title_align
        self.padding = padding
        self.body_fg = body_fg
        self.border_fg = border_fg

    def _box(self, inner_content):
        return Box(content=inner_content, border=self.border,
                   title=self.title, title_align=self.title_align,
                   padding=self.padding, bg=self.theme.bg,
                   fg=parse_color(self.body_fg) if self.body_fg is not None else self.theme.fg,
                   border_fg=parse_color(self.border_fg) if self.border_fg is not None else self.theme.border)

    def measure(self, avail_w, avail_h):
        return self._box(self.body if isinstance(self.body, str) else self.body).measure(avail_w, avail_h)

    def render(self, region_w, region_h):
        # Word-wrap string bodies to the content width.
        content = self.body
        if isinstance(self.body, str):
            inner_w = max(1, region_w - 2 - (self.padding[1] if isinstance(self.padding, tuple) else self.padding) * 2)
            content = "\n".join(_wrap_words(self.body, inner_w))
        return self._box(content).render(region_w, region_h)

    @classmethod
    def sample(cls, theme):
        return cls("A panel wraps content in a titled, bordered frame. "
                   "Body text word-wraps to the inner width.",
                   title="Panel", theme=theme)


# ==========================================================================
# ProgressBar / Meter
# ==========================================================================
@register
class ProgressBar(Widget):
    """A progress bar with 1/8-cell precision (U+2588..U+258F) + optional label."""
    key = "progress"
    summary = "Progress bar with 1/8-cell precision and percent"

    def __init__(self, ratio: float = 0.42, *, label: str = "", show_pct: bool = True,
                 gradient: bool = True, theme=None):
        super().__init__(theme)
        self.ratio = core.clamp01(ratio)
        self.label = label
        self.show_pct = show_pct
        self.gradient = gradient

    def measure(self, avail_w, avail_h):
        w = 10
        if self.label:
            w += cell_width(self.label) + 1
        if self.show_pct:
            w += 5
        return (max(w, 12), 1)

    def render(self, region_w, region_h):
        cv = Canvas(region_w, max(1, region_h), bg=self.theme.bg)
        x = 0
        if self.label:
            x += cv.put_text(0, 0, self.label + " ", fg=self.theme.fg)
        suffix = f" {int(round(self.ratio * 100)):3d}%" if self.show_pct else ""
        bar_w = max(1, region_w - x - cell_width(suffix))
        filled = self.ratio * bar_w
        full = int(filled)
        frac = filled - full
        # draw filled portion cell-by-cell for gradient coloring
        for i in range(full):
            col = self.theme.color_at(i / max(1, bar_w - 1)) if self.gradient else self.theme.accent
            cv.set(x + i, 0, BAR_FULL, fg=col, bg=self.theme.bg)
        eighth = int(round(frac * 8))
        if 0 < eighth < 8 and full < bar_w:
            col = self.theme.color_at(full / max(1, bar_w - 1)) if self.gradient else self.theme.accent
            cv.set(x + full, 0, BAR_EIGHTHS[eighth], fg=col, bg=self.theme.bg)
            full += 1
        for i in range(full, bar_w):
            cv.set(x + i, 0, "─", fg=self.theme.muted, bg=self.theme.bg)
        if suffix:
            cv.put_text(x + bar_w, 0, suffix, fg=self.theme.fg, attrs=BOLD)
        return cv

    @classmethod
    def sample(cls, theme):
        return cls(0.62, label="Build", theme=theme)


@register
class Meter(Widget):
    """A labelled stack of horizontal bars (a small bar chart)."""
    key = "meter"
    summary = "Multi-row labelled bar chart / meters"

    def __init__(self, items=None, *, theme=None):
        super().__init__(theme)
        # items: list of (label, ratio)
        self.items = items or [("CPU", 0.72), ("MEM", 0.48), ("DISK", 0.91)]

    def measure(self, avail_w, avail_h):
        lw = max((cell_width(l) for l, _ in self.items), default=0)
        return (lw + 20, len(self.items))

    def render(self, region_w, region_h):
        cv = Canvas(region_w, max(len(self.items), region_h), bg=self.theme.bg)
        lw = max((cell_width(l) for l, _ in self.items), default=0)
        for i, (label, ratio) in enumerate(self.items):
            if i >= cv.h:
                break
            cv.put_text(0, i, core.pad(label, lw), fg=self.theme.fg)
            bar = ProgressBar(ratio, show_pct=True, theme=self.theme)
            sub = bar.render(region_w - lw - 1, 1)
            cv.blit(sub, lw + 1, i)
        return cv

    @classmethod
    def sample(cls, theme):
        return cls(theme=theme)


# ==========================================================================
# KeyValueList (definition list)
# ==========================================================================
@register
class KeyValueList(Widget):
    """A 2-column key/value list: keys right-padded to max key width, values wrap."""
    key = "kv"
    summary = "Two-column key/value (definition) list"

    def __init__(self, pairs=None, *, gap: int = 2, theme=None, key_fg=None):
        super().__init__(theme)
        self.pairs = pairs or [("Status", "running"), ("Region", "us-east-1"),
                               ("Uptime", "14d 3h"), ("Nodes", "128")]
        self.gap = gap
        self.key_fg = key_fg

    def _kw(self):
        return max((cell_width(str(k)) for k, _ in self.pairs), default=0)

    def measure(self, avail_w, avail_h):
        kw = self._kw()
        vw = max((cell_width(str(v)) for _, v in self.pairs), default=0)
        return (kw + self.gap + vw, len(self.pairs))

    def render(self, region_w, region_h):
        cv = Canvas(region_w, max(len(self.pairs), region_h), bg=self.theme.bg)
        kw = self._kw()
        kfg = parse_color(self.key_fg) if self.key_fg is not None else self.theme.muted
        val_x = kw + self.gap
        y = 0
        for k, v in self.pairs:
            if y >= cv.h:
                break
            cv.put_text(0, y, core.pad(str(k), kw), fg=kfg)
            for i, line in enumerate(_wrap_words(str(v), max(1, region_w - val_x))):
                if y >= cv.h:
                    break
                cv.put_text(val_x, y, line, fg=self.theme.fg)
                y += 1
        return cv

    @classmethod
    def sample(cls, theme):
        return cls(theme=theme)


# ==========================================================================
# Banner (figlet big text)
# ==========================================================================
@register
class Banner(Widget):
    """Big FIGlet text via pyfiglet, colored with a theme gradient.

    Degrades gracefully to a bold uppercase label when pyfiglet is unavailable.
    """
    key = "banner"
    summary = "Big FIGlet text banner (needs pyfiglet)"

    _cache: dict = {}

    def __init__(self, text: str = "TUI", *, font: str = "standard", theme=None):
        super().__init__(theme)
        self.text = text
        self.font = font

    def _lines(self) -> list[str]:
        cache_key = (self.text, self.font)
        if cache_key in Banner._cache:
            return Banner._cache[cache_key]
        try:
            import pyfiglet
            art = pyfiglet.Figlet(font=self.font).renderText(self.text)
            lines = [l for l in art.rstrip("\n").split("\n")]
        except Exception:
            lines = [self.text.upper()]
        # trim trailing empty columns/rows
        while lines and not lines[-1].strip():
            lines.pop()
        Banner._cache[cache_key] = lines
        return lines

    def measure(self, avail_w, avail_h):
        lines = self._lines()
        return (max((cell_width(l) for l in lines), default=0), len(lines))

    def render(self, region_w, region_h):
        lines = self._lines()
        cv = Canvas(region_w, max(len(lines), region_h), bg=self.theme.bg)
        for y, line in enumerate(lines):
            if y >= cv.h:
                break
            for x, ch in enumerate(line):
                if x >= region_w:
                    break
                if ch != " ":
                    col = self.theme.color_at(x / max(1, region_w - 1))
                    cv.set(x, y, ch, fg=col, bg=self.theme.bg, attrs=BOLD)
        return cv

    @classmethod
    def sample(cls, theme):
        return cls("TUI", theme=theme)


# ==========================================================================
# Table
# ==========================================================================
@register
class Table(Widget):
    """A bordered table with auto column sizing (cell-width aware).

    Columns start at their max content width; if the total overflows the region,
    the widest wrappable columns are shrunk first. Header is bold/accent.
    """
    key = "table"
    summary = "Auto-sized data table with borders + header"

    def __init__(self, headers=None, rows=None, *, border: str = "single",
                 justify=None, theme=None, show_edge: bool = True):
        super().__init__(theme)
        self.headers = headers or ["Name", "Status", "CPU%"]
        self.rows = rows or [["api-gateway", "healthy", "12"],
                             ["worker-01", "healthy", "63"],
                             ["cache-西storage", "degraded", "88"],
                             ["deploy-🚀bot", "healthy", "5"]]
        self.border = border
        self.justify = justify or ["left"] * len(self.headers)
        self.show_edge = show_edge

    def _col_widths(self, budget: int) -> list[int]:
        ncol = len(self.headers)
        widths = [cell_width(str(h)) for h in self.headers]
        for row in self.rows:
            for c in range(ncol):
                if c < len(row):
                    widths[c] = max(widths[c], cell_width(str(row[c])))
        # account for per-cell padding (1 each side) + separators
        pad = 2
        sep = ncol + 1  # vertical bars incl edges
        total = sum(widths) + pad * ncol + sep
        avail_content = budget - pad * ncol - sep
        if sum(widths) > avail_content and avail_content > 0:
            # shrink widest columns until fit
            while sum(widths) > avail_content and any(w > 1 for w in widths):
                i = max(range(ncol), key=lambda k: widths[k])
                widths[i] -= 1
        return widths

    def measure(self, avail_w, avail_h):
        widths = self._col_widths(avail_w)
        total = sum(widths) + 2 * len(self.headers) + (len(self.headers) + 1)
        return (total, len(self.rows) + 3)

    def render(self, region_w, region_h):
        g = core.BOX_STYLES.get(self.border, core.BOX_STYLES["single"])
        widths = self._col_widths(region_w)
        ncol = len(self.headers)
        bcol = self.theme.border

        def sep_row(left, mid, right):
            parts = [left]
            for i, w in enumerate(widths):
                parts.append(g["h"] * (w + 2))
                parts.append(right if i == ncol - 1 else mid)
            return "".join(parts)

        top = sep_row(g["tl"], g["tee_d"], g["tr"])
        head_div = sep_row(g["tee_r"], g["cross"], g["tee_l"])
        bottom = sep_row(g["bl"], g["tee_u"], g["br"])

        lines_meta = []  # (text, is_border)
        lines_meta.append((top, True))
        lines_meta.append((self.headers, "header"))
        lines_meta.append((head_div, True))
        for row in self.rows:
            lines_meta.append((row, "row"))
        lines_meta.append((bottom, True))

        cv = Canvas(region_w, max(len(lines_meta), region_h), bg=self.theme.bg)
        for y, (data, kind) in enumerate(lines_meta):
            if y >= cv.h:
                break
            if kind is True:
                cv.put_text(0, y, data, fg=bcol)
                continue
            x = 0
            cv.set(x, y, g["v"], fg=bcol)
            x += 1
            for c in range(ncol):
                w = widths[c]
                val = str(data[c]) if c < len(data) else ""
                aligned = core.pad(core.truncate(val, w), w, self.justify[c] if c < len(self.justify) else "left")
                if kind == "header":
                    cv.put_text(x + 1, y, aligned, fg=self.theme.accent, attrs=BOLD)
                else:
                    fg = self.theme.fg
                    if val in ("degraded", "error", "failed"):
                        fg = self.theme.err
                    elif val in ("healthy", "ok", "running"):
                        fg = self.theme.ok
                    cv.put_text(x + 1, y, aligned, fg=fg)
                x += w + 2
                cv.set(x, y, g["v"], fg=bcol)
                x += 1
        return cv

    @classmethod
    def sample(cls, theme):
        return cls(theme=theme)


# ==========================================================================
# Tabs
# ==========================================================================
@register
class Tabs(Widget):
    """A tab strip with an active tab underlined, plus the active pane's body."""
    key = "tabs"
    summary = "Tab strip with active underline + content pane"

    def __init__(self, tabs=None, *, active: int = 0, body=None, theme=None):
        super().__init__(theme)
        self.tabs = tabs or ["Overview", "Metrics", "Logs"]
        self.active = active
        self.body = body if body is not None else "Active tab content renders here."

    def measure(self, avail_w, avail_h):
        w = sum(cell_width(t) + 3 for t in self.tabs)
        return (max(w, 20), 4)

    def render(self, region_w, region_h):
        cv = Canvas(region_w, max(4, region_h), bg=self.theme.bg)
        x = 0
        spans = []  # (start, width) of active for underline
        for i, t in enumerate(self.tabs):
            label = f" {t} "
            lw = cell_width(label)
            if i == self.active:
                cv.put_text(x, 0, label, fg=self.theme.accent, attrs=BOLD)
                spans.append((x, lw))
            else:
                cv.put_text(x, 0, label, fg=self.theme.muted)
            x += lw + 1
        # underline row
        cv.put_text(0, 1, "─" * region_w, fg=self.theme.border)
        for sx, sw in spans:
            cv.put_text(sx, 1, "━" * sw, fg=self.theme.accent)
        # body
        for i, line in enumerate(_wrap_words(str(self.body), region_w)):
            if 2 + i >= cv.h:
                break
            cv.put_text(0, 2 + i, line, fg=self.theme.fg)
        return cv

    @classmethod
    def sample(cls, theme):
        return cls(active=1, body="Metrics pane: request rate 1.2k/s, p99 84ms.",
                   theme=theme)


# ==========================================================================
# Tree
# ==========================================================================
@register
class Tree(Widget):
    """A DFS tree with ├──/└── guide glyphs. Nodes are ``(label, [children])``."""
    key = "tree"
    summary = "Guide-line tree view (DFS)"

    def __init__(self, root=None, *, theme=None):
        super().__init__(theme)
        self.root = root or ("project", [
            ("src", [("core.py", []), ("box.py", []), ("layout.py", [])]),
            ("tests", [("test_ui.py", [])]),
            ("README.md", []),
        ])

    def _flatten(self):
        lines = []

        def walk(node, prefix, is_last, is_root):
            label, children = node
            if is_root:
                lines.append(("", label, True))
            else:
                connector = "└── " if is_last else "├── "
                lines.append((prefix + connector, label, False))
            child_prefix = prefix + ("    " if is_last else "│   ") if not is_root else ""
            for i, ch in enumerate(children):
                walk(ch, child_prefix, i == len(children) - 1, False)

        walk(self.root, "", True, True)
        return lines

    def measure(self, avail_w, avail_h):
        lines = self._flatten()
        w = max((cell_width(p + l) for p, l, _ in lines), default=0)
        return (w, len(lines))

    def render(self, region_w, region_h):
        lines = self._flatten()
        cv = Canvas(region_w, max(len(lines), region_h), bg=self.theme.bg)
        for y, (prefix, label, is_root) in enumerate(lines):
            if y >= cv.h:
                break
            x = cv.put_text(0, y, prefix, fg=self.theme.border)
            cv.put_text(x, y, label, fg=self.theme.accent if is_root else self.theme.fg,
                        attrs=BOLD if is_root else 0)
        return cv

    @classmethod
    def sample(cls, theme):
        return cls(theme=theme)


# ==========================================================================
# Card
# ==========================================================================
@register
class Card(Widget):
    """A panel shell composing a title, body text, a KV list, and a footer badge."""
    key = "card"
    summary = "Composite card: title + body + kv + badge footer"

    def __init__(self, title: str = "Service", body: str = "",
                 kv=None, badge: str = "healthy", badge_kind: str = "ok",
                 *, border: str = "rounded", theme=None):
        super().__init__(theme)
        self.title = title
        self.body = body or "A card composes a bordered shell around stacked content."
        self.kv = kv or [("Region", "us-east-1"), ("Replicas", "3/3")]
        self.badge = badge
        self.badge_kind = badge_kind
        self.border = border

    def _inner(self, inner_w, inner_h):
        from .layout import VStack
        parts = [
            Rule(theme=self.theme, char="─"),
        ]
        body_lines = _wrap_words(self.body, max(1, inner_w))
        body_box = Box(content="\n".join(body_lines), bg=self.theme.bg, fg=self.theme.fg,
                       height=len(body_lines))
        kv = KeyValueList(self.kv, theme=self.theme)
        badge = Badge(self.badge, kind=self.badge_kind, theme=self.theme)
        return VStack([body_box, Rule(theme=self.theme), kv, badge], gap=0)

    def measure(self, avail_w, avail_h):
        return (min(avail_w, 40), 9)

    def render(self, region_w, region_h):
        inner_w = max(1, region_w - 4)
        inner_h = max(1, region_h - 2)
        box = Box(content=self._inner(inner_w, inner_h), border=self.border,
                  title=self.title, title_align="left", padding=(0, 1),
                  bg=self.theme.bg, fg=self.theme.fg, border_fg=self.theme.border)
        return box.render(region_w, region_h)

    @classmethod
    def sample(cls, theme):
        return cls(theme=theme)
