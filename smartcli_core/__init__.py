"""SmartCLI shared core.

A pluggable-PTY + pyte screen model + semantic snapshot + readiness stack for
driving interactive terminal programs. Both SmartCLI skills build on this.

Quick start::

    from smartcli_core import PtySession

    with PtySession(cols=100, rows=30) as sess:
        sess.start("python")
        sess.wait_ready(marker=r">>> $")
        sess.send_line("print('hello')")
        reason, snap = sess.wait_ready(marker=r">>> $")
        print(snap.to_text())
"""

from __future__ import annotations

from .pty_backend import (
    PosixPtyBackend,
    PtyBackend,
    WinptyBackend,
    get_default_backend,
)
from .readiness import wait_for_regex, wait_ready, wait_until_stable
from .screen_model import CellAttrs, ScreenModel
from .session import KEY_MAP, PtySession
from .snapshot import Snapshot, Span, build_snapshot

__all__ = [
    # backends
    "PtyBackend",
    "WinptyBackend",
    "PosixPtyBackend",
    "get_default_backend",
    # screen
    "ScreenModel",
    "CellAttrs",
    # snapshot
    "Snapshot",
    "Span",
    "build_snapshot",
    # readiness
    "wait_until_stable",
    "wait_for_regex",
    "wait_ready",
    # session
    "PtySession",
    "KEY_MAP",
]

__version__ = "0.1.0"
