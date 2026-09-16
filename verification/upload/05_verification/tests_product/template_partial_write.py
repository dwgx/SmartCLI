"""T03 production-method tests with injected OS writes, NOT native PTY tests.
The worker must add deadline, partial cancellation and failure-receipt tests for
its chosen private helper without changing this byte-exact oracle.
"""
from __future__ import annotations
import argparse
import errno
import os
from pathlib import Path
import select
import sys
import unittest
from unittest.mock import patch

ap = argparse.ArgumentParser(add_help=False)
ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
args, rest = ap.parse_known_args()
sys.dont_write_bytecode = True
sys.path.insert(0, str(args.repo.resolve()))
try:
    from smartcli_core.pty_backend import PosixPtyBackend
    import smartcli_core
    imported = getattr(smartcli_core, "__file__", None)
    if not imported or not Path(imported).resolve().is_relative_to((args.repo.resolve() / "smartcli_core")):
        raise RuntimeError("test imported an unrelated installed SmartCLI")
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2)

class PartialWriteRegression(unittest.TestCase):
    def exercise(self, schedule):
        payload = "A中\x00B\r\n保存".encode()
        received = bytearray(); attempts = 0; fake_fd = 987654
        def write(fd, data):
            nonlocal attempts
            self.assertEqual(fd, fake_fd)
            attempts += 1
            self.assertLessEqual(attempts, 32, "busy-loop attempt budget")
            action = schedule[attempts-1] if attempts <= len(schedule) else len(data)
            if action == "again": raise BlockingIOError(errno.EAGAIN, "injected")
            if action == "intr": raise InterruptedError(errno.EINTR, "injected")
            n = min(action, len(data)); received.extend(data[:n]); return n
        def wait(reads, writes, errors, timeout=None):
            self.assertTrue(all(x == fake_fd for x in [*reads,*writes,*errors]))
            return [], list(writes), []
        backend = PosixPtyBackend(); backend._fd = fake_fd
        try:
            with patch.object(os, "write", write), patch.object(select, "select", wait):
                backend.write(payload)
        finally:
            backend._fd = None
        self.assertEqual(bytes(received), payload, "every byte once, in order")
        self.assertGreater(attempts, 1)

    def test_short_writes_only(self):
        self.exercise([2, 1, 2])

    def test_short_write_eagain_eintr(self):
        self.exercise([2, "again", "intr", 1])

if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
