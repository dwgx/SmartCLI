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
from collections.abc import Sequence
from typing import Any


class IncompleteWrite(OSError):
    """A PTY write finished short: ``written_bytes`` of ``total_bytes`` landed.

    Raised instead of returning normally so a caller can never mistake a partial
    write for a complete one. It subclasses :class:`OSError`, which is the family
    the backend already raises for transport failures, so existing
    ``except OSError`` handlers keep working while new callers can read the
    progress fields. ``written_bytes`` is ``None`` when the transport could not
    report how much of the payload it consumed -- filling in ``0`` there would
    invite a caller to re-send bytes that may already have reached the child.

    The bytes reported as written really are in the kernel/child; they cannot be
    recalled. Cancellation and timeouts do not roll back input.
    """

    def __init__(self, written_bytes: int | None, total_bytes: int, reason: str) -> None:
        self.written_bytes = written_bytes
        self.total_bytes = total_bytes
        self.reason = reason
        shown = "unknown" if written_bytes is None else str(written_bytes)
        super().__init__(
            f"incomplete PTY write: {shown}/{total_bytes} bytes ({reason})")


class PtyBackend(abc.ABC):
    """Abstract pseudo-terminal backend.

    Implementations own a child process running under a PTY sized ``cols`` x
    ``rows``. All reads are non-blocking and return raw ``bytes`` (possibly
    empty). Writes accept ``bytes``.
    """

    @abc.abstractmethod
    def spawn(self, cmd: str | Sequence[str], cols: int, rows: int) -> None:
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
        # pywinpty is an optional, platform-only import with no bundled stubs.
        self._proc: Any | None = None  # winpty.PtyProcess
        self._queue: queue.Queue[bytes | None] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._eof = False

    def spawn(self, cmd: str | Sequence[str], cols: int, rows: int) -> None:
        import winpty  # imported lazily so non-Windows hosts don't require it

        # Reset per-spawn state so a re-used backend (a second spawn on the same
        # instance) does not inherit the previous child's EOF sentinel or latched
        # _eof — otherwise read_nonblocking would stop draining at the stale None
        # and consumers would see premature EOF. A fresh queue drops any leftover.
        self._queue = queue.Queue()
        self._eof = False
        self._reader = None

        # winpty.spawn accepts a command string or an argv list; dimensions are
        # (rows, cols).
        self._proc = winpty.PtyProcess.spawn(cmd, dimensions=(rows, cols))
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        """Blocking-read the child until EOF, pushing bytes into the queue."""
        proc = self._proc
        if proc is None:
            return
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
        self._pid: int | None = None
        self._fd: int | None = None
        self._eof = False

    def spawn(self, cmd: str | Sequence[str], cols: int, rows: int) -> None:
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

    #: Deadline for one ``write`` call, in seconds. A non-blocking fd that never
    #: becomes writable must fail the call rather than park the owner loop; the
    #: value is a bounded-wait policy, not a performance target.
    write_timeout: float = 5.0

    def write(self, data: bytes) -> None:
        """Write every byte of ``data``, or raise :class:`IncompleteWrite`.

        The fd is non-blocking, so a single ``os.write`` may accept only a
        prefix (or raise ``EAGAIN``); its return value was previously discarded,
        which reported success for input the child never received. This loop
        keeps an offset and only returns once every byte has been accepted,
        waiting for writability between attempts and honouring a deadline.
        ``EINTR`` retries the very same suffix -- never a re-send of the whole
        payload, which would duplicate bytes already delivered.
        """
        import os
        import select
        import time

        if self._fd is None:
            raise RuntimeError("spawn() must be called before write()")
        total = len(data)
        if total == 0:                       # empty payload: explicit no-op
            return

        view = memoryview(data)
        offset = 0
        deadline = time.monotonic() + self.write_timeout
        while offset < total:
            try:
                written = os.write(self._fd, view[offset:])
            except InterruptedError:
                # A signal arrived before any byte was accepted: same suffix.
                if time.monotonic() >= deadline:
                    raise IncompleteWrite(offset, total, "deadline after EINTR") from None
                continue
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise IncompleteWrite(offset, total, "deadline waiting for writability") from None
                # Spurious wakeups are allowed: re-check the same suffix. The
                # call is bounded and never spins.
                select.select([], [self._fd], [], min(remaining, 0.25))
                continue
            except OSError as exc:
                # EPIPE/EIO/bad fd: the previously written prefix is still real,
                # so report the progress instead of pretending nothing landed.
                raise IncompleteWrite(offset, total,
                                      f"{type(exc).__name__}: {exc}") from exc
            if written <= 0:
                # No progress and no error: treat like EAGAIN rather than
                # looping hot on a descriptor that accepted nothing.
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise IncompleteWrite(offset, total, "no progress")
                select.select([], [self._fd], [], min(remaining, 0.25))
                continue
            offset += written

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
        import time

        pid = self._pid
        if pid is not None:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            # REAP the child so it does not linger as a zombie. SIGTERM alone
            # (the old behavior) left a <defunct> process because nothing ever
            # waitpid()'d it — verified on real Linux. Poll briefly for a clean
            # exit, then SIGKILL as a fallback, then reap in both cases.
            reaped = False
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                try:
                    wpid, _ = os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    reaped = True  # already reaped elsewhere
                    break
                except OSError:
                    break
                if wpid == pid:
                    reaped = True
                    break
                time.sleep(0.02)
            if not reaped:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
                # Bounded reap after SIGKILL — do NOT block forever. A child stuck
                # in uninterruptible sleep (D state: wedged NFS/FUSE/driver) will
                # not process even SIGKILL until its syscall returns, so a plain
                # blocking waitpid could hang teardown. Poll briefly and give up;
                # the kernel reaps it once it unwedges (we've closed the fd).
                kill_deadline = time.monotonic() + 1.0
                while time.monotonic() < kill_deadline:
                    try:
                        wpid, _ = os.waitpid(pid, os.WNOHANG)
                    except OSError:
                        break
                    if wpid == pid:
                        break
                    time.sleep(0.02)
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
