#!/usr/bin/env python3
"""Deterministic locks for selection/cursor-aware visual change detection."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smartcli_core import PtySession  # noqa: E402
from smartcli_core.pty_backend import PtyBackend  # noqa: E402

failures = 0


def check(condition: bool, label: str) -> None:
    global failures
    if not condition:
        failures += 1
    print(f"{'PASS' if condition else 'FAIL'}  {label}")


class FakeBackend(PtyBackend):
    def __init__(self) -> None:
        self.queue: list[bytes] = []

    def spawn(self, cmd, cols, rows) -> None:
        pass

    def read_nonblocking(self) -> bytes:
        return self.queue.pop(0) if self.queue else b""

    def write(self, data: bytes) -> None:
        pass

    def resize(self, cols: int, rows: int) -> None:
        pass

    def is_alive(self) -> bool:
        return True

    def terminate(self) -> None:
        pass


def new_session() -> tuple[PtySession, FakeBackend]:
    backend = FakeBackend()
    session = PtySession(cols=20, rows=4, backend=backend)
    session.model.feed(b"first\r\nsecond")
    return session, backend


def test_attribute_only_change() -> None:
    session, backend = new_session()
    text_hash = session.model.content_hash()
    visual_hash = session.model.visual_hash()
    backend.queue.append(b"\x1b[H\x1b[7mfirst\x1b[0m")

    changed, _ = session.wait_visual_change(
        baseline_hash=visual_hash, timeout_ms=100, poll_ms=0
    )
    check(changed, "reverse-video selection changes visual_hash")
    check(session.model.content_hash() == text_hash,
          "selection-only styling leaves content_hash stable")
    check(session.model.visual_hash() != visual_hash,
          "visual_hash records cell attributes")


def test_cursor_only_change() -> None:
    session, backend = new_session()
    text_hash = session.model.content_hash()
    visual_hash = session.model.visual_hash()
    backend.queue.append(b"\x1b[1D")

    changed, _ = session.wait_visual_change(
        baseline_hash=visual_hash, timeout_ms=100, poll_ms=0
    )
    check(changed, "cursor-only movement is detected")
    check(session.model.content_hash() == text_hash,
          "cursor-only movement leaves content_hash stable")


def test_text_wait_ignores_attributes() -> None:
    session, backend = new_session()
    text_hash = session.model.content_hash()
    backend.queue.append(b"\x1b[H\x1b[7mfirst\x1b[0m")

    changed, _ = session.wait_change(
        baseline_hash=text_hash, timeout_ms=20, poll_ms=0
    )
    check(not changed, "wait_change retains text-only stability semantics")


def main() -> int:
    test_attribute_only_change()
    test_cursor_only_change()
    test_text_wait_ignores_attributes()
    print()
    if failures:
        print(f"{failures} FAILURE(S)")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
