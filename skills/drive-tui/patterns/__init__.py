"""drive-tui patterns -- pluggable interaction paradigms for TUI screens.

A :class:`Pattern` looks at a :class:`smartcli_core.Snapshot` and answers two
questions: "is this MY kind of screen?" (:meth:`Pattern.matches`, 0..1
confidence) and "how do I operate it?" (:meth:`Pattern.drive`, running the
perceive->act->wait loop against a live :class:`smartcli_core.PtySession`).

Add a paradigm = drop a module into ``patterns/recipes/`` with an
``@register``-ed Pattern subclass; :func:`patterns.registry.load_all` imports
the folder automatically, and :func:`patterns.classify.classify` starts
ranking it immediately.
"""
from __future__ import annotations

import os
import sys

# Make smartcli_core importable no matter where the caller sits: the repo root
# is three levels up (patterns/ -> drive-tui/ -> skills/ -> ROOT), overridable
# with SMARTCLI_ROOT.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
for _p in ([os.environ.get("SMARTCLI_ROOT")] if os.environ.get("SMARTCLI_ROOT")
           else []) + [_ROOT]:
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

from .base import Pattern, PatternResult  # noqa: E402
from .registry import all_patterns, get, load_all, register  # noqa: E402
from .classify import classify, explain  # noqa: E402

__all__ = [
    "Pattern", "PatternResult",
    "register", "get", "all_patterns", "load_all",
    "classify", "explain",
]
