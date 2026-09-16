"""Mutation harness for the T05/T04 negative proofs.

Restores ONLY the pre-fix logic inside an isolated validation copy of the repo's
``smartcli_core``; the test files are never touched. Each mutation is a targeted
textual replacement that asserts it applied exactly once, so a silent no-op
(a mutation that "survives" because it never happened) is impossible.

Usage:
    python mutate.py <validation-repo> t05-old-slice      # restore display[y][a:b]
    python mutate.py <validation-repo> t04-old-regex      # restore the chunk-local regex path
"""
from __future__ import annotations

import pathlib
import sys

OLD_CLASS = '''class _ByteStream(pyte.ByteStream):
    """``pyte.ByteStream`` with NEL dispatch and SGR sub-parameter tolerance."""

    escape = {**pyte.Stream.escape, "E": "next_line"}

    # SGR sub-parameters use ':' as the separator (ITU-T T.416): `ESC[4:3m` is a
    # curly underline, `ESC[38:2::R:G:Bm` a truecolor foreground. pyte's parser
    # does not know ':' at all, so it aborted the sequence and DREW THE REST AS
    # TEXT.
    _SGR_COLON = __import__("re").compile(rb"\\x1b\\[([\\d;:]*:[\\d;:]*)m")

    # Matches a run at the END of a buffer that is still a possibly-incomplete
    # CSI introducer.
    _INCOMPLETE_CSI = __import__("re").compile(rb"\\x1b(\\[[\\d;:]*)?")
    _MAX_PENDING = 512

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._pending: bytes = b""

    # The bytes-vs-str override is pyte's own Liskov violation, not ours.
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

CLASS_START = "class _ByteStream(pyte.ByteStream):"
CLASS_END = "class _Screen(pyte.Screen):"


def _replace_once(path: pathlib.Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"mutation anchor found {count} times in {path} (expected 1)")
    path.write_text(text.replace(old, new), encoding="utf-8")


def mutate(repo: pathlib.Path, which: str) -> None:
    if which == "t05-old-slice":
        snap = repo / "smartcli_core" / "snapshot.py"
        _replace_once(
            snap,
            '            text = "".join(c.data for c in line_cells[y][a:b]).strip()',
            '            text = display[y][a:b].strip()',
        )
        print(f"mutated {snap}: cell aggregation -> display string slice")
    elif which == "t04-old-regex":
        model = repo / "smartcli_core" / "screen_model.py"
        text = model.read_text(encoding="utf-8")
        start = text.index(CLASS_START)
        end = text.index(CLASS_END)
        mutated = text[:start] + OLD_CLASS + text[end:]
        if "self._SGR_COLON" not in mutated or "_CSI_CAP" in mutated[start:start + len(OLD_CLASS)]:
            raise SystemExit("mutation produced an unexpected class body")
        model.write_text(mutated, encoding="utf-8")
        print(f"mutated {model}: streaming filter -> chunk-local colon regex")
    elif which == "t03-single-write":
        backend = repo / "smartcli_core" / "pty_backend.py"
        text = backend.read_text(encoding="utf-8")
        # Anchor AFTER the class attribute that only PosixPtyBackend has: the
        # abstract base declares write() with the same signature, so a plain
        # index() would mutate the abstract method and leave the fix in place.
        anchor = text.index("    write_timeout: float = 5.0")
        start = text.index("    def write(self, data: bytes) -> None:", anchor)
        end = text.index("    def resize(self, cols: int, rows: int) -> None:", start)
        old_body = (
            "    def write(self, data: bytes) -> None:\n"
            "        import os\n\n"
            "        if self._fd is None:\n"
            "            raise RuntimeError(\"spawn() must be called before write()\")\n"
            "        os.write(self._fd, data)\n\n"
        )
        mutated = text[:start] + old_body + text[end:]
        if "view[offset:]" in mutated:
            raise SystemExit("t03 mutation did not remove the bounded loop")
        if mutated.count("os.write(self._fd, data)") != 1:
            raise SystemExit("t03 mutation did not install exactly one single-write call")
        backend.write_text(mutated, encoding="utf-8")
        print(f"mutated {backend}: bounded write loop -> single os.write, return value discarded")
    else:
        raise SystemExit(f"unknown mutation {which!r}")


if __name__ == "__main__":
    mutate(pathlib.Path(sys.argv[1]), sys.argv[2])
