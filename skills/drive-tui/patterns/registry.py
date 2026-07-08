"""Pattern registry: ``@register`` + pkgutil auto-discovery of recipes/.

Mirrors fx.registry: drop a module into ``patterns/recipes/`` and it shows up
in :func:`all_patterns` / classify automatically; a broken module is skipped
with a warning instead of breaking every other recipe.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
import traceback
from typing import Optional

from .base import Pattern


class RegistryError(Exception):
    pass


_REGISTRY: dict[str, Pattern] = {}   # name -> singleton instance
_LOADED = False
_LOAD_ERRORS: list[tuple[str, str]] = []


def register(cls: Optional[type] = None, *, replace: bool = False):
    """Class decorator for Pattern subclasses. Stores a singleton instance."""
    def _do(c: type) -> type:
        if not (isinstance(c, type) and issubclass(c, Pattern)):
            raise RegistryError(f"@register expects a Pattern subclass, got {c!r}")
        if not c.name:
            raise RegistryError(f"{c.__name__} must set a non-empty 'name'")
        key = c.name.lower()
        if not replace and key in _REGISTRY:
            raise RegistryError(f"pattern name already registered: {key!r}")
        _REGISTRY[key] = c()
        return c

    return _do(cls) if cls is not None else _do


def get(name: str) -> Pattern:
    load_all()
    key = name.lower().strip()
    if key not in _REGISTRY:
        raise KeyError(
            f"unknown pattern {name!r}. Known: {', '.join(sorted(_REGISTRY))}")
    return _REGISTRY[key]


def all_patterns() -> list[Pattern]:
    load_all()
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def load_errors() -> list[tuple[str, str]]:
    return list(_LOAD_ERRORS)


def load_all(force: bool = False) -> None:
    global _LOADED
    if _LOADED and not force:
        return
    _LOADED = True
    from . import recipes as pkg
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue
        mod_name = f"{pkg.__name__}.{info.name}"
        try:
            importlib.import_module(mod_name)
        except Exception:
            tb = traceback.format_exc()
            _LOAD_ERRORS.append((mod_name, tb))
            print(f"[patterns] WARNING: recipe module {mod_name} failed to load "
                  f"(skipped): {tb.strip().splitlines()[-1]}", file=sys.stderr)
