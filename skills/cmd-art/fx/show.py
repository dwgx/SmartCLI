"""Scripted shows: play a sequence of (effect, theme, seconds) segments, with
an optional split-screen combinator -- all inside ONE alt-screen session so
segment changes never flicker.

Spec grammar (CLI ``--seq``):
    "donut:fire:4,plasma::3,rain:matrix-green:5"
    segment = effect[:theme[:seconds]]      theme empty -> effect/default theme
    split segment = "left|right" in the effect slot:
    "donut|fire:synthwave:6"  -> donut left, fire right, 6s, synthwave both

Script file (``--script show.json``) is a JSON list of objects:
    {"effect": "donut", "theme": "fire", "seconds": 4, "params": {"speed": 2}}
    {"split": ["donut", "fire"], "themes": ["ocean", "fire"], "seconds": 6}
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from typing import Optional

from . import registry
from .base import Effect, FrameCtx
from .core import play
from .theme import Theme, get_theme
from .util import frame_lines


# --------------------------------------------------------------------------
# Split-screen combinator
# --------------------------------------------------------------------------
class Split(Effect):
    """Render two effects side by side, each themed independently.

    Not registered: it is a combinator you build from two real effects. Lines
    are ANSI-aware padded to the half width so the seam stays vertical.
    """

    name = "split"
    description = "Two effects side by side (combinator, not registered)."

    def __init__(self, left: Effect, right: Effect,
                 left_theme: Optional[Theme] = None,
                 right_theme: Optional[Theme] = None,
                 left_params: Optional[dict] = None,
                 right_params: Optional[dict] = None):
        self.left, self.right = left, right
        self.left_theme, self.right_theme = left_theme, right_theme
        self.left_params = left_params if left_params is not None else \
            type(left).param_defaults()
        self.right_params = right_params if right_params is not None else \
            type(right).param_defaults()

    def setup(self) -> None:
        self.left.setup()
        self.right.setup()

    def teardown(self) -> None:
        try:
            self.left.teardown()
        finally:
            self.right.teardown()

    def render(self, ctx: FrameCtx) -> str:
        lw = (ctx.width - 1) // 2
        rw = ctx.width - 1 - lw
        lctx = dataclasses.replace(
            ctx, width=lw, theme=self.left_theme or ctx.theme,
            params=self.left_params)
        rctx = dataclasses.replace(
            ctx, width=rw, theme=self.right_theme or ctx.theme,
            params=self.right_params)
        lls = frame_lines(self.left.render(lctx), ctx.height, lw)
        rls = frame_lines(self.right.render(rctx), ctx.height, rw)
        sep = "\x1b[0m\x1b[2m\u2502\x1b[0m"
        return "\n".join(l + sep + r for l, r in zip(lls, rls))


# --------------------------------------------------------------------------
# Show: a timed sequence of segments
# --------------------------------------------------------------------------
@dataclass
class Segment:
    effect: Effect               # instance (may be a Split)
    seconds: float = 4.0
    theme: Optional[Theme] = None
    params: dict = field(default_factory=dict)
    label: str = ""


class _ShowRunner(Effect):
    """Adapter: exposes a whole Show as one Effect for core.play().

    Sub-effect setup/teardown fire exactly at segment boundaries, and the
    active segment gets a LOCAL clock (t restarts at 0 each segment).
    """

    name = "_show"
    description = "internal Show adapter"

    def __init__(self, segments: list[Segment]):
        if not segments:
            raise ValueError("show needs at least one segment")
        self.segments = segments
        self._starts = []
        acc = 0.0
        for seg in segments:
            self._starts.append(acc)
            acc += max(0.1, seg.seconds)
        self.total = acc
        self._current = -1

    def _segment_at(self, t: float) -> int:
        idx = len(self.segments) - 1
        for i in range(len(self.segments)):
            end = self._starts[i] + max(0.1, self.segments[i].seconds)
            if t < end:
                idx = i
                break
        return idx

    def setup(self) -> None:
        self._current = -1

    def render(self, ctx: FrameCtx) -> str:
        idx = self._segment_at(ctx.t)
        seg = self.segments[idx]
        if idx != self._current:
            if self._current >= 0:
                try:
                    self.segments[self._current].effect.teardown()
                except Exception:
                    pass
            seg.effect.setup()
            self._current = idx
        local = dataclasses.replace(
            ctx,
            t=ctx.t - self._starts[idx],
            theme=seg.theme or ctx.theme,
            params=seg.params or type(seg.effect).param_defaults(),
        )
        return seg.effect.render(local)

    def teardown(self) -> None:
        if self._current >= 0:
            try:
                self.segments[self._current].effect.teardown()
            except Exception:
                pass
        self._current = -1


class Show:
    """Build + play a scripted sequence of effect segments."""

    def __init__(self, segments: list[Segment]):
        self.segments = segments
        self.runner = _ShowRunner(segments)

    @property
    def total_seconds(self) -> float:
        return self.runner.total

    def play(self, *, width: int, height: int, theme: Theme,
             fps: float = 30.0) -> None:
        def ctx_factory(t, frame_index):
            return FrameCtx(t=t, frame_index=frame_index, width=width,
                            height=height, theme=theme, params={})
        play(self.runner, fps=fps, seconds=self.total_seconds,
             ctx_factory=ctx_factory)


# --------------------------------------------------------------------------
# Spec parsing
# --------------------------------------------------------------------------
def _make_effect(name: str, params: Optional[dict] = None):
    cls = registry.get(name)
    coerced = cls.parse_params({k: v for k, v in (params or {}).items()})
    return cls(), coerced


def _seg_from_names(effect_spec: str, theme_name: str, seconds: float,
                    params: Optional[dict] = None,
                    themes: Optional[list] = None) -> Segment:
    if "|" in effect_spec:
        lname, rname = (s.strip() for s in effect_spec.split("|", 1))
        lth = get_theme(themes[0]) if themes else None
        rth = get_theme(themes[1]) if themes and len(themes) > 1 else None
        if theme_name and not themes:
            lth = rth = get_theme(theme_name)
        le, lp = _make_effect(lname)
        re_, rp = _make_effect(rname)
        if lth is None:
            lth = get_theme(type(le).preferred_theme)
        if rth is None:
            rth = get_theme(type(re_).preferred_theme)
        eff = Split(le, re_, lth, rth, lp, rp)
        return Segment(effect=eff, seconds=seconds, theme=None, params={},
                       label=f"{lname}|{rname}")
    eff, coerced = _make_effect(effect_spec, params)
    theme = get_theme(theme_name) if theme_name else \
        get_theme(type(eff).preferred_theme)
    return Segment(effect=eff, seconds=seconds, theme=theme, params=coerced,
                   label=effect_spec)


def parse_seq(spec: str, default_seconds: float = 4.0) -> list[Segment]:
    """Parse the compact ``effect[:theme[:seconds]],...`` grammar."""
    segments = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(":")
        name = parts[0].strip()
        theme = parts[1].strip() if len(parts) > 1 else ""
        secs = float(parts[2]) if len(parts) > 2 and parts[2].strip() else \
            default_seconds
        segments.append(_seg_from_names(name, theme, secs))
    if not segments:
        raise ValueError(f"empty show spec: {spec!r}")
    return segments


def parse_script(path: str, default_seconds: float = 4.0) -> list[Segment]:
    """Parse the JSON script format (see module docstring)."""
    data = json.loads(open(path, encoding="utf-8").read())
    if not isinstance(data, list):
        raise ValueError("show script must be a JSON list of segment objects")
    segments = []
    for i, obj in enumerate(data):
        if not isinstance(obj, dict):
            raise ValueError(f"segment {i}: expected an object")
        secs = float(obj.get("seconds", default_seconds))
        if "split" in obj:
            pair = obj["split"]
            if not (isinstance(pair, list) and len(pair) == 2):
                raise ValueError(f"segment {i}: 'split' must be [left, right]")
            segments.append(_seg_from_names(
                f"{pair[0]}|{pair[1]}", obj.get("theme", ""), secs,
                themes=obj.get("themes")))
        else:
            segments.append(_seg_from_names(
                obj["effect"], obj.get("theme", ""), secs,
                params=obj.get("params") or {}))
    if not segments:
        raise ValueError("show script has no segments")
    return segments
