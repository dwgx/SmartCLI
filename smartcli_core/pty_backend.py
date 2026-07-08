"""Pluggable PTY backends for SmartCLI.

A :class:`PtyBackend` abstracts spawning a child process attached to a
pseudo-terminal and exchanging bytes with it. Two concrete backends ship:

* :class:`WinptyBackend` -- uses ``pywinpty`` (ConPTY) on Windows. ``pywinpty``
  reads are blocking and return ``str``; a background reader thread drains the
  process into a queue so :meth:`read_nonblocking` never blocks.
* :class:`PosixPtyBackend` -- uses the stdlib ``pty``/``os``/``select`` stack.
  The POSIX-only imports are guarded so this module imports cleanly on Windows.

Both backends normalise their read side to **bytes** so the rest of the core
(screen model, readiness) can feed a single long-lived ``pyte.ByteStream``.

Use :func:`get_default_backend` to obtain the right backend for the host.
"""

from __future__ import annotations

import abc
import queue
import sys
import threading
import time
from typing import Optional, Sequence, Union


class PtyBackend(abc.ABC):
    """Abstract pseudo-terminal backend.

    Implementations own a child process running under a PTY sized ``cols`` x
    ``rows``. All reads are non-blocking and return raw ``bytes`` (possibly
    empty). Writes accept ``bytes``.
    """

    @abc.abstractmethod
    def spawn(self, cmd: Union[str, Sequence[str]], cols: int, rows: int) -> None:
        """Launch ``cmd`` in a PTY of size ``cols`` x ``rows``."""

    @abc.abstractmethod
    def read_nonblocking(self) -> bytes:
        """Return any bytes available right now; ``b""`` if none. Never blocks."""

    @abc.abstractmethod
    def write(self, data: bytes) -> None:
        """Write ``data`` to the child's stdin."""

    @abc.abstractmethod
    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY window to ``cols`` x ``rows``."""

    @abc.abstractmethod
    def is_alive(self) -> bool:
        """Return ``True`` while the child process is running."""

    @abc.abstractmethod
    def terminate(self) -> None:
        """Terminate the child and release resources. Idempotent."""


class WinptyBackend(PtyBackend):
    """PTY backend built on ``pywinpty`` (ConPTY).

    ``pywinpty`` returns already-decoded ``str`` and its ``read`` can block, so a
    daemon reader thread performs blocking reads and pushes UTF-8 encoded chunks
    into a :class:`queue.Queue`. :meth:`read_nonblocking` drains that queue.
    """

    def __init__(self) -> None:
        self._proc = None  # winpty.PtyProcess
        self._queue: "queue.Queue[Optional[bytes]]" = queue.Queue()
        self._reader: Optional[threading.Thread] = None
        self._eof = False

    def spawn(self, cmd: Union[str, Sequence[str]], cols: int, rows: int) -> None:
        import winpty  # imported lazily so non-Windows hosts don't require it

        # winpty.spawn accepts a command string or an argv list; dimensions are
        # (rows, cols).
        self._proc = winpty.PtyProcess.spawn(cmd, dimensions=(rows, cols))
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        """Blocking-read the child until EOF, pushing bytes into the queue."""
        proc = self._proc
        while True:
            try:
                data = proc.read(65536)  # returns str; blocks if nothing ready
            except EOFError:
                break
            except OSError:
                break
            if data:
                self._queue.put(data.encode("utf-8", "replace"))
        self._queue.put(None)  # EOF sentinel

    def read_nonblocking(self) -> bytes:
        out = bytearray()
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                self._eof = True
                break
            out.extend(item)
        return bytes(out)

    def write(self, data: bytes) -> None:
        if self._proc is None:
            raise RuntimeError("spawn() must be called before write()")
        # pywinpty.write expects str.
        self._proc.write(data.decode("utf-8", "replace"))

    def resize(self, cols: int, rows: int) -> None:
        if self._proc is not None:
            self._proc.setwinsize(rows, cols)

    def is_alive(self) -> bool:
        if self._proc is None:
            return False
        try:
            return bool(self._proc.isalive())
        except Exception:
            return False

    def terminate(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate(force=True)
        except Exception:
            pass
        finally:
            self._proc = None


class PosixPtyBackend(PtyBackend):
    """PTY backend built on the stdlib ``pty``/``os``/``select`` stack.

    Only usable on POSIX hosts. The heavy imports happen inside :meth:`spawn`
    (and a small module-level guard) so importing this file on Windows is safe.
    """

    def __init__(self) -> None:
        self._pid: Optional[int] = None
        self._fd: Optional[int] = None
        self._eof = False

    def spawn(self, cmd: Union[str, Sequence[str]], cols: int, rows: int) -> None:
        import fcntl
        import os
        import pty
        import struct
        import termios

        if isinstance(cmd, str):
            argv = ["/bin/sh", "-c", cmd]
        else:
            argv = list(cmd)

        pid, master_fd = pty.fork()
        if pid == 0:  # child
            try:
                os.execvp(argv[0], argv)
            except Exception:
                os._exit(127)
        # parent
        self._pid = pid
        self._fd = master_fd
        os.set_blocking(master_fd, False)
        fcntl.ioctl(
            master_fd,
            termios.TIOCSWINSZ,
            struct.pack("HHHH", rows, cols, 0, 0),
        )

    def read_nonblocking(self) -> bytes:
        import os
        import select

        if self._fd is None:
            return b""
        out = bytearray()
        while True:
            r, _, _ = select.select([self._fd], [], [], 0)
            if not r:
                break
            try:
                chunk = os.read(self._fd, 65536)
            except BlockingIOError:
                break
            except OSError:  # EIO on child exit (Linux)
                self._eof = True
                break
            if not chunk:  # EOF (BSD/mac)
                self._eof = True
                break
            out.extend(chunk)
        return bytes(out)

    def write(self, data: bytes) -> None:
        import os

        if self._fd is None:
            raise RuntimeError("spawn() must be called before write()")
        os.write(self._fd, data)

    def resize(self, cols: int, rows: int) -> None:
        import fcntl
        import struct
        import termios

        if self._fd is not None:
            fcntl.ioctl(
                self._fd,
                termios.TIOCSWINSZ,
                struct.pack("HHHH", rows, cols, 0, 0),
            )

    def is_alive(self) -> bool:
        import os

        if self._pid is None:
            return False
        try:
            pid, _ = os.waitpid(self._pid, os.WNOHANG)
            return pid == 0
        except OSError:
            return False

    def terminate(self) -> None:
        import os
        import signal

        if self._pid is not None:
            try:
                os.kill(self._pid, signal.SIGTERM)
            except OSError:
                pass
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
        self._pid = None
        self._fd = None


def get_default_backend() -> PtyBackend:
    """Return a backend appropriate for the current platform.

    Windows -> :class:`WinptyBackend`; everything else -> :class:`PosixPtyBackend`.
    """
    if sys.platform == "win32":
        return WinptyBackend()
    return PosixPtyBackend()
