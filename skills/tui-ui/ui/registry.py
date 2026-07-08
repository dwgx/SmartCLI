"""registry.py — widget registry with ``@register`` + folder discovery.

Widgets self-register at import time. :func:`load_all` imports :mod:`ui.widgets`
plus every module under ``ui/widgets_ext/``, so DROPPING A NEW MODULE in that
folder is all it takes to add a widget — mirrors fx/patterns. A module that fails
to import is reported (stderr + :func:`load_errors`) but never takes the rest of
the catalog down.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
import traceback
from typing import Optional

_REGISTRY: dict[str, type] = {}
_LOADED = False
_LOAD_ERRORS: list[tuple[str, str]] = []


class RegistryError(Exception):
    pass


def register(cls: Optional[type] = None, *, replace: bool = False):
    """Class decorator: add a widget to the registry under its ``key``."""
    def _do(c: type) -> type:
        key = getattr(c, "key", "") or c.__name__.lower()
        key = key.lower()
        if not replace and key in _REGISTRY:
            raise RegistryError(f"widget key already registered: {key!r}")
        _REGISTRY[key] = c
        return c
    return _do(cls) if cls is not None else _do


def get(key: str) -> type:
    load_all()
    k = key.lower().strip()
    if k not in _REGISTRY:
        raise KeyError(f"unknown widget {key!r}. Known: {', '.join(sorted(_REGISTRY))}")
    return _REGISTRY[k]


def all_widgets() -> list[type]:
    load_all()
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def widget_names() -> list[str]:
    load_all()
    return sorted(_REGISTRY)


def load_errors() -> list[tuple[str, str]]:
    return list(_LOAD_ERRORS)


def load_all(force: bool = False) -> None:
    """Import ui.widgets and every ui/widgets_ext/*.py so ``@register`` runs."""
    global _LOADED
    if _LOADED and not force:
        return
    _LOADED = True
    # Core widgets module.
    try:
        importlib.import_module("ui.widgets")
    except Exception:
        tb = traceback.format_exc()
        _LOAD_ERRORS.append(("ui.widgets", tb))
        print(f"[ui] WARNING: ui.widgets failed to load: {tb.strip().splitlines()[-1]}",
              file=sys.stderr)
    # Extension folder (drop-in widgets).
    try:
        import ui.widgets_ext as pkg
        for info in pkgutil.iter_modules(pkg.__path__):
            if info.name.startswith("_"):
                continue
            mod = f"{pkg.__name__}.{info.name}"
            try:
                importlib.import_module(mod)
            except Exception:
                tb = traceback.format_exc()
                _LOAD_ERRORS.append((mod, tb))
                print(f"[ui] WARNING: widget module {mod} failed to load (skipped): "
                      f"{tb.strip().splitlines()[-1]}", file=sys.stderr)
    except Exception:
        pass
