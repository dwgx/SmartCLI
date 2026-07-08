"""Effect registry: ``@register`` + discovery.

Effects self-register at import time; :func:`load_all` walks ``fx/effects/``
with :mod:`pkgutil` and imports every module, so dropping a new ``.py`` file in
that folder is ALL it takes to add an effect. A module that fails to import is
reported (stderr + :func:`load_errors`) but never takes the rest of the
catalog down with it.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
import traceback
from typing import Optional

from .base import Effect


class RegistryError(Exception):
    pass


_REGISTRY: dict[str, type[Effect]] = {}
_ALIASES: dict[str, str] = {}
_LOADED = False
_LOAD_ERRORS: list[tuple[str, str]] = []  # (module, traceback text)


def register(cls: Optional[type] = None, *, replace: bool = False):
    """Class decorator: add an :class:`Effect` subclass to the registry.

    Usage::

        @register
        class Donut(Effect):
            name = "donut"
            ...

    Duplicate names raise :class:`RegistryError` (pass ``replace=True`` to
    intentionally shadow, e.g. a user override of a built-in).
    """
    def _do(c: type) -> type:
        if not (isinstance(c, type) and issubclass(c, Effect)):
            raise RegistryError(f"@register expects an Effect subclass, got {c!r}")
        if not c.name:
            raise RegistryError(f"{c.__name__} must set a non-empty 'name'")
        key = c.name.lower()
        if not replace and (key in _REGISTRY or key in _ALIASES):
            raise RegistryError(f"effect name already registered: {key!r}")
        _REGISTRY[key] = c
        for alias in c.aliases:
            a = alias.lower()
            if not replace and (a in _REGISTRY or a in _ALIASES):
                raise RegistryError(f"alias already registered: {a!r}")
            _ALIASES[a] = key
        return c

    return _do(cls) if cls is not None else _do


def get(name: str) -> type[Effect]:
    """Resolve an effect class by name or alias (case-insensitive). KeyError if absent."""
    load_all()
    key = name.lower().strip()
    key = _ALIASES.get(key, key)
    if key not in _REGISTRY:
        raise KeyError(
            f"unknown effect {name!r}. Known: {', '.join(sorted(_REGISTRY))}")
    return _REGISTRY[key]


def all_effects() -> list[type[Effect]]:
    """Every registered effect class, sorted by name."""
    load_all()
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def by_tag(tag: str) -> list[type[Effect]]:
    """Effects carrying *tag* (case-insensitive)."""
    t = tag.lower().strip()
    return [c for c in all_effects() if t in tuple(x.lower() for x in c.tags)]


def load_errors() -> list[tuple[str, str]]:
    """(module_name, traceback) for every effects module that failed to import."""
    return list(_LOAD_ERRORS)


def load_all(force: bool = False) -> None:
    """Import every module under ``fx.effects`` so ``@register`` runs.

    Idempotent. Broken modules are skipped with a stderr warning; the error is
    kept in :func:`load_errors` for the CLI to surface.
    """
    global _LOADED
    if _LOADED and not force:
        return
    _LOADED = True
    from . import effects as pkg
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue
        mod_name = f"{pkg.__name__}.{info.name}"
        try:
            importlib.import_module(mod_name)
        except Exception:
            tb = traceback.format_exc()
            _LOAD_ERRORS.append((mod_name, tb))
            print(f"[fx] WARNING: effect module {mod_name} failed to load "
                  f"(skipped): {tb.strip().splitlines()[-1]}", file=sys.stderr)
