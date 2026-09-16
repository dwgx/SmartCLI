"""Mutation harness for the negative proofs (T05/T04/T03 and A04-S1).

Restores ONLY the pre-fix logic inside an isolated validation copy; the test files
are never touched. Each mutation is a targeted textual replacement that asserts it
applied exactly once, so a silent no-op (a mutation that "survives" because it
never happened) is impossible.

Usage:  python mutate.py <validation-repo> <mutation-name>
"""
from __future__ import annotations

import pathlib
import sys

CLASS_START = "class _ByteStream(pyte.ByteStream):"
CLASS_END = "class _Screen(pyte.Screen):"

# The pre-T04 class body (chunk-local colon regex) used by the t04 mutation.
OLD_CLASS = '''class _ByteStream(pyte.ByteStream):
    """``pyte.ByteStream`` with NEL dispatch and SGR sub-parameter tolerance."""

    escape = {**pyte.Stream.escape, "E": "next_line"}

    _SGR_COLON = __import__("re").compile(rb"\\x1b\\[([\\d;:]*:[\\d;:]*)m")
    _INCOMPLETE_CSI = __import__("re").compile(rb"\\x1b(\\[[\\d;:]*)?")
    _MAX_PENDING = 512

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._pending: bytes = b""

    def feed(self, data: bytes) -> None:  # type: ignore[override]
        if self._pending:
            data = self._pending + data
            self._pending = b""
        idx = data.rfind(b"\\x1b")
        if idx != -1 and self._INCOMPLETE_CSI.fullmatch(data, idx):
            tail = data[idx:]
            if len(tail) <= self._MAX_PENDING:
                self._pending = tail
                data = data[:idx]
        if not data:
            return
        if b":" in data:
            data = self._SGR_COLON.sub(
                lambda m: b"\\x1b[" + m.group(1).replace(b":", b";") + b"m", data)
        super().feed(data)


'''

T03_OLD_BODY = (
    '    def write(self, data: bytes) -> None:\n'
    '        import os\n\n'
    '        if self._fd is None:\n'
    '            raise RuntimeError("spawn() must be called before write()")\n'
    '        os.write(self._fd, data)\n\n'
)

S1_IGNORE_BUDGET_OLD = (
    '        if max_bytes <= 0:\n'
    '            return b""\n'
    '        out = bytearray()\n'
    '        if self._carry:\n'
    '            take = min(max_bytes, len(self._carry))\n'
    '            out += self._carry[:take]\n'
    '            del self._carry[:take]\n'
    '        while len(out) < max_bytes:\n'
)
S1_IGNORE_BUDGET_NEW = (
    '        if max_bytes <= 0:\n'
    '            return b""\n'
    '        out = bytearray()\n'
    '        if self._carry:\n'
    '            out += self._carry\n'
    '            self._carry.clear()\n'
    '        while True:\n'
)

S1_DRAINED_OLD = '        if len(data) >= max_bytes:\n            return "budget_limited"\n'
S1_DRAINED_NEW = '        if len(data) >= max_bytes:\n            return "drained"\n'

S1_FALLBACK_OLD = (
    '            if not supports_read_budget(self.backend):\n'
    '                raise ReadBudgetUnsupported(\n'
    '                    f"{type(self.backend).__name__} does not implement the budgeted-read "\n'
    '                    "capability (READ_BUDGET_CAPABLE); refusing to read unbounded and slice")\n'
    '            data = self.backend._read_budgeted(max_bytes)\n'
)
S1_FALLBACK_NEW = (
    '            if not supports_read_budget(self.backend):\n'
    '                data = self.backend.read_nonblocking()[:max_bytes]\n'
    '            else:\n'
    '                data = self.backend._read_budgeted(max_bytes)\n'
)


def _replace_once(path: pathlib.Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"mutation anchor found {count} times in {path} (expected 1)")
    path.write_text(text.replace(old, new), encoding="utf-8")


def mutate(repo: pathlib.Path, which: str) -> None:
    core = repo / "smartcli_core"
    if which == "t05-old-slice":
        target = core / "snapshot.py"
        _replace_once(
            target,
            '            text = "".join(c.data for c in line_cells[y][a:b]).strip()',
            '            text = display[y][a:b].strip()',
        )
    elif which == "t04-old-regex":
        target = core / "screen_model.py"
        text = target.read_text(encoding="utf-8")
        start, end = text.index(CLASS_START), text.index(CLASS_END)
        mutated = text[:start] + OLD_CLASS + text[end:]
        if "self._SGR_COLON" not in mutated or "_CSI_CAP" in mutated[start:start + len(OLD_CLASS)]:
            raise SystemExit("mutation produced an unexpected class body")
        target.write_text(mutated, encoding="utf-8")
    elif which == "t03-single-write":
        target = core / "pty_backend.py"
        text = target.read_text(encoding="utf-8")
        # Anchor AFTER the class attribute that only PosixPtyBackend has: the
        # abstract base declares write() with the same signature, so a plain
        # index() would mutate the abstract method and leave the fix in place.
        anchor = text.index("    write_timeout: float = 5.0")
        start = text.index("    def write(self, data: bytes) -> None:", anchor)
        end = text.index("    def resize(self, cols: int, rows: int) -> None:", start)
        mutated = text[:start] + T03_OLD_BODY + text[end:]
        if "view[offset:]" in mutated or mutated.count("os.write(self._fd, data)") != 1:
            raise SystemExit("t03 mutation did not install the single-write body")
        target.write_text(mutated, encoding="utf-8")
    elif which == "a04-s1-ignore-budget":
        target = core / "pty_backend.py"
        _replace_once(target, S1_IGNORE_BUDGET_OLD, S1_IGNORE_BUDGET_NEW)
    elif which == "a04-s1-drained-when-full":
        target = core / "session.py"
        _replace_once(target, S1_DRAINED_OLD, S1_DRAINED_NEW)
    elif which == "a04-s1-silent-fallback":
        target = core / "session.py"
        _replace_once(target, S1_FALLBACK_OLD, S1_FALLBACK_NEW)
    elif which == "a04-s2-no-gate":
        target = core / "readiness.py"
        _replace_once(
            target,
            '    if not io_block:\n        return False\n    if io_block.get("local_cut") not in ("drained", None):',
            '    if not io_block:\n        return False\n    if False and io_block.get("local_cut") not in ("drained", None):',
        )
    elif which == "a04-s4-always-confirmed":
        target = core / "pty_backend.py"
        _replace_once(
            target,
            '        self._closed_confirmed = confirmed\n        self._close_unconfirmed = not confirmed',
            '        self._closed_confirmed = True\n        self._close_unconfirmed = False',
        )
    elif which == "a04-s5-no-backpressure":
        target = core / "pty_backend.py"
        _replace_once(
            target,
            '                while not self._stopping and self._accounted_payload() >= self.QUEUE_PAYLOAD_HIGH:\n                    room.wait(0.25)',
            '                while False:\n                    room.wait(0.25)',
        )
    else:
        raise SystemExit(f"unknown mutation {which!r}")
    print(f"mutated {target}: {which}")


if __name__ == "__main__":
    mutate(pathlib.Path(sys.argv[1]), sys.argv[2])
