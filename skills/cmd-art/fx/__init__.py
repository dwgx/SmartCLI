"""fx -- pluggable terminal visual-effects framework (pure Python stdlib).

Layers:

* :mod:`fx.core`     terminal primitives + the flicker-free bounded play loop
* :mod:`fx.theme`    named palettes / gradient + HSV helpers
* :mod:`fx.base`     Effect / StaticEffect ABCs, FrameCtx, Param schema
* :mod:`fx.registry` ``@register`` + auto-discovery of ``fx/effects/*.py``
* :mod:`fx.show`     scripted multi-effect shows, split-screen combinator
* :mod:`fx.cli`      ``list | show | play | gallery | random`` CLI

Add an effect = drop a module into ``fx/effects/`` containing::

    from ..base import Effect, FrameCtx, Param
    from ..registry import register

    @register
    class MyThing(Effect):
        name = "mything"
        description = "..."
        def render(self, ctx: FrameCtx) -> str: ...
"""
from .base import DEFAULT_RAMP, Effect, FrameCtx, Param, StaticEffect
from .registry import all_effects, by_tag, get, load_all, register
from .theme import THEMES, Theme, get_theme, theme_names

__all__ = [
    "Effect", "StaticEffect", "FrameCtx", "Param", "DEFAULT_RAMP",
    "register", "get", "all_effects", "by_tag", "load_all",
    "Theme", "THEMES", "get_theme", "theme_names",
]

__version__ = "0.1.5"
