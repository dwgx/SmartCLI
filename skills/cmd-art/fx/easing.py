"""easing.py — standard easing functions for effect animation.

Each takes a progress ratio t in [0,1] and returns an eased value (usually in
[0,1], though back/elastic overshoot outside it by design). These are the
canonical Penner/Robert-Penner easings used everywhere from CSS to game engines
and terminaltexteffects; text effects use them to move characters from a start
to a target position with natural acceleration instead of a linear slide.

Shared so effects don't each re-derive the math. Pure stdlib.
"""
from __future__ import annotations

import math

_C1 = 1.70158            # back-easing overshoot constant
_C2 = _C1 * 1.525
_C3 = _C1 + 1.0
_C4 = (2 * math.pi) / 3
_C5 = (2 * math.pi) / 4.5


def _clamp01(t: float) -> float:
    return 0.0 if t < 0 else (1.0 if t > 1 else t)


def linear(t): return _clamp01(t)


def in_quad(t): t = _clamp01(t); return t * t
def out_quad(t): t = _clamp01(t); return 1 - (1 - t) * (1 - t)
def in_out_quad(t):
    t = _clamp01(t)
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2


def in_cubic(t): t = _clamp01(t); return t ** 3
def out_cubic(t): t = _clamp01(t); return 1 - (1 - t) ** 3
def in_out_cubic(t):
    t = _clamp01(t)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def in_sine(t): t = _clamp01(t); return 1 - math.cos(t * math.pi / 2)
def out_sine(t): t = _clamp01(t); return math.sin(t * math.pi / 2)
def in_out_sine(t): t = _clamp01(t); return -(math.cos(math.pi * t) - 1) / 2


def out_back(t):
    t = _clamp01(t)
    return 1 + _C3 * (t - 1) ** 3 + _C1 * (t - 1) ** 2


def in_out_back(t):
    t = _clamp01(t)
    if t < 0.5:
        return ((2 * t) ** 2 * ((_C2 + 1) * 2 * t - _C2)) / 2
    return ((2 * t - 2) ** 2 * ((_C2 + 1) * (t * 2 - 2) + _C2) + 2) / 2


def out_elastic(t):
    t = _clamp01(t)
    if t == 0 or t == 1:
        return t
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * _C4) + 1


def out_bounce(t):
    t = _clamp01(t)
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


# name -> function, for effects that take an easing by string param.
EASINGS = {
    "linear": linear,
    "in_quad": in_quad, "out_quad": out_quad, "in_out_quad": in_out_quad,
    "in_cubic": in_cubic, "out_cubic": out_cubic, "in_out_cubic": in_out_cubic,
    "in_sine": in_sine, "out_sine": out_sine, "in_out_sine": in_out_sine,
    "out_back": out_back, "in_out_back": in_out_back,
    "out_elastic": out_elastic, "out_bounce": out_bounce,
}


def get(name: str):
    """Look up an easing by name, defaulting to in_out_cubic."""
    return EASINGS.get(name, in_out_cubic)
