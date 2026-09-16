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


def _pid_is_gone(pid: int) -> bool:
    """True when the process is gone (no such process, or not ours to signal)."""
    import errno
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return True          # exists but is not ours: not our child to confirm
    except OSError as exc:
        return exc.errno not in (errno.EPERM,)
    return False


class ReadBudgetUnsupported(RuntimeError):
    """A byte-budgeted read was requested from a backend that cannot honour it.

    Raised instead of silently falling back to an unbounded read: reading
    everything and then slicing it would satisfy the caller's *shape* while
    breaking the bound the budget exists to enforce.
    """


def supports_read_budget(backend: "PtyBackend") -> bool:
    """Does ``backend`` implement the private budgeted-read capability?

    The capability is DECLARED by the class (``READ_BUDGET_CAPABLE = True``) and
    is never probed by calling and catching ``TypeError``: a ``TypeError`` raised
    *inside* a backend's read would then look like a signature mismatch, and the
    retry could consume the transport twice or mask a real bug.
    """
    return bool(getattr(backend, "READ_BUDGET_CAPABLE", False))


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
        #: Bytes already popped from the queue but not yet handed to a caller:
        #: a budgeted read may stop in the middle of a chunk, and that suffix is
        #: still our responsibility. It is accounted in read_status() as
        #: `reader_held_payload_bytes` so "queue bounded" cannot hide an
        #: unbounded buffer outside the queue.
        self._carry = bytearray()
        self._generation = 0
        # Close protocol (A04-S4), same vocabulary as the POSIX backend.
        self._close_requested = False
        self._closing = False
        self._closed_confirmed = False
        self._close_unconfirmed = False
        self._last_close_progress: str | None = None

    #: Declares the private budgeted-read capability (see supports_read_budget).
    READ_BUDGET_CAPABLE = True

    #: A04-S5 payload budget for the delivery queue. The reader stops pulling from
    #: ConPTY once the *accounted payload* (queue + held suffix + the chunk in
    #: hand) reaches the high-water mark and resumes below the low mark, so
    #: "bounded" covers everything this runtime owns -- not just the queue, which
    #: is what the old item-counted, unbounded queue could never claim. The cap is
    #: a DESIGN value (the measured X2 backlog was 271 307 B in 7.5 s); it is not
    #: a performance target, and it cannot make the Windows wire byte-exact.
    QUEUE_PAYLOAD_HIGH = int(__import__("os").environ.get("SMARTCLI_WINPTY_HIGH_BYTES",
                                                          str(4 * 1024 * 1024)))
    QUEUE_PAYLOAD_LOW = int(__import__("os").environ.get("SMARTCLI_WINPTY_LOW_BYTES",
                                                         str(1 * 1024 * 1024)))

    def spawn(self, cmd: str | Sequence[str], cols: int, rows: int) -> None:
        import winpty  # imported lazily so non-Windows hosts don't require it

        # Reset per-spawn state so a re-used backend (a second spawn on the same
        # instance) does not inherit the previous child's EOF sentinel or latched
        # _eof — otherwise read_nonblocking would stop draining at the stale None
        # and consumers would see premature EOF. A fresh queue drops any leftover.
        self._queue = queue.Queue()
        self._eof = False
        self._reader = None
        self._carry.clear()
        self._generation += 1
        # Per-spawn flow control: the reader holds THIS generation's queue and stop
        # flag, so a late callback can never write into a later spawn's queue.
        self._room = threading.Condition()
        self._stopping = False
        self._close_requested = False
        self._closing = False
        self._closed_confirmed = False
        self._close_unconfirmed = False
        self._last_close_progress = None

        # winpty.spawn accepts a command string or an argv list; dimensions are
        # (rows, cols).
        self._proc = winpty.PtyProcess.spawn(cmd, dimensions=(rows, cols))
        # NOTE: the locals are NOT named `queue` -- that would shadow the module
        # import used by `self._queue = queue.Queue()` above (UnboundLocalError).
        delivery, room, proc = self._queue, self._room, self._proc
        self._reader = threading.Thread(target=self._read_loop,
                                        args=(proc, delivery, room), daemon=True)
        self._reader.start()

    def _accounted_payload(self) -> int:
        """Payload this backend owns: queued bytes plus the unreturned suffix."""
        return self._queue_payload_bytes() + len(self._carry)

    def _read_loop(self, proc, delivery, room) -> None:
        """Blocking-read the child, pushing payload into a BOUNDED queue.

        A04-S5: the loop stops pulling once the accounted payload reaches the high
        water mark and waits (stop-aware) until the consumer has taken some, so an
        idle daemon cannot accumulate an unbounded backlog (measured: 271 307 B in
        7.5 s before this). The wait is on a Condition, never inside the native
        read; ``terminate`` sets the stop flag and wakes it. If the budget check
        refuses a chunk, the chunk is kept and re-offered -- bytes are never
        dropped, and the reader refuses to grow instead.
        """
        pending: bytes | None = None
        while True:
            with room:
                while not self._stopping and self._accounted_payload() >= self.QUEUE_PAYLOAD_HIGH:
                    room.wait(0.25)
                if self._stopping:
                    break
            if pending is None:
                try:
                    data = proc.read(65536)  # returns str; blocks if nothing ready
                except EOFError:
                    break
                except OSError:
                    break
                if data:
                    pending = data.encode("utf-8", "replace")
            if pending is None:
                continue
            delivery.put(pending)
            pending = None
        delivery.put(None)  # EOF sentinel

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
        if out:
            self._wake_reader()
        return bytes(out)

    def _queue_payload_bytes(self) -> int:
        """Payload currently inside the queue (excludes the held suffix)."""
        with self._queue.mutex:
            return sum(len(i) for i in self._queue.queue if isinstance(i, (bytes, bytearray)))

    def _read_budgeted(self, max_bytes: int) -> bytes:
        """Read at most ``max_bytes`` from the delivery queue.

        A chunk larger than the remaining budget is split: the unreturned suffix
        stays in ``self._carry`` and is delivered by the next call, so a bound on
        this method bounds the caller's work without losing or duplicating a
        byte. The EOF sentinel is consumed here and latched, never returned as
        data.
        """
        if max_bytes <= 0:
            return b""
        out = bytearray()
        if self._carry:
            take = min(max_bytes, len(self._carry))
            out += self._carry[:take]
            del self._carry[:take]
        while len(out) < max_bytes:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                self._eof = True
                break
            room = max_bytes - len(out)
            if len(item) > room:
                out += item[:room]
                self._carry += item[room:]
                break
            out += item
        if out:
            self._wake_reader()
        return bytes(out)

    def _wake_reader(self) -> None:
        """Tell a full-queue reader that room is available (stop-aware)."""
        room = getattr(self, "_room", None)
        if room is None:
            return
        with room:
            room.notify_all()

    def read_status(self) -> dict:
        """What can be said about the transport without reading it."""
        try:
            readable = len(self._carry) > 0 or not self._queue.empty()
        except Exception:
            readable = None
        return {
            "readable_now": readable,
            "eof": self._eof,
            "error": None,
            "queued_payload_bytes": self._queue_payload_bytes(),
            "reader_held_payload_bytes": len(self._carry),
            "generation": self._generation,
        }

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

    def close_state(self) -> dict:
        return {
            "close_requested": self._close_requested,
            "closing": self._closing,
            "closed_confirmed": self._closed_confirmed,
            "close_unconfirmed": self._close_unconfirmed,
            "output_eof": self._eof,
            "last_progress": self._last_close_progress,
            "generation": self._generation,
        }

    def terminate(self) -> None:
        """Ask the child to exit, then CONFIRM it -- bounded, never assumed.

        ``pywinpty``'s ``terminate(force=True)`` returns when the call is done, and
        Microsoft documents that ConPTY may keep producing output while the
        pseudoconsole closes (and that the return behaviour changed around build
        26100). So the native call is only *requested* here; confirmation comes
        from polling ``isalive()`` within a bounded window. When it cannot be
        confirmed the state says ``close_unconfirmed`` with the last progress --
        never a silent success.
        """
        import time

        self._close_requested = True
        self._closing = True
        self._stopping = True
        room = getattr(self, "_room", None)
        if room is not None:
            with room:
                room.notify_all()          # a reader waiting for room must not hang teardown
        if self._proc is None:
            self._closed_confirmed = True
            self._closing = False
            return
        try:
            self._proc.terminate(force=True)
            self._last_close_progress = "terminate(force=True) returned"
        except Exception as exc:
            self._last_close_progress = f"terminate raised {type(exc).__name__}: {exc}"
        deadline = time.monotonic() + 1.0
        confirmed = False
        while time.monotonic() < deadline:
            try:
                if not self._proc.isalive():
                    confirmed = True
                    break
            except Exception:
                confirmed = True     # the handle is gone: that is the strongest signal we get
                break
            time.sleep(0.02)
        self._closed_confirmed = confirmed
        self._close_unconfirmed = not confirmed
        if not confirmed:
            self._last_close_progress = ("child still reported alive 1.0s after "
                                         "terminate(force=True)")
        self._closing = False
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
        self._read_error: str | None = None
        self._generation = 0
        # Close protocol (A04-S4): requested -> closing -> confirmed | unconfirmed.
        self._close_requested = False
        self._closing = False
        self._closed_confirmed = False
        self._close_unconfirmed = False
        self._last_close_progress: str | None = None

    #: Declares the private budgeted-read capability (see supports_read_budget).
    READ_BUDGET_CAPABLE = True

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
        self._eof = False
        self._read_error = None
        self._generation += 1
        self._close_requested = False
        self._closing = False
        self._closed_confirmed = False
        self._close_unconfirmed = False
        self._last_close_progress = None
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
                self._read_error = "OSError on read"
                break
            if not chunk:  # EOF (BSD/mac)
                self._eof = True
                break
            out.extend(chunk)
        return bytes(out)

    def _read_budgeted(self, max_bytes: int) -> bytes:
        """Read at most ``max_bytes`` in this call.

        ``select`` with a zero timeout keeps this non-blocking: an unready fd
        returns ``b""`` and says so through :meth:`read_status`, which is how a
        caller distinguishes "nothing yet" from "budget spent". EOF and read
        errors are latched for the same reason -- an empty result must not be
        mistaken for a completed stream.
        """
        import os
        import select

        if self._fd is None or max_bytes <= 0:
            return b""
        r, _, _ = select.select([self._fd], [], [], 0)
        if not r:
            return b""
        try:
            chunk = os.read(self._fd, max_bytes)
        except BlockingIOError:
            return b""
        except OSError:  # EIO on child exit (Linux)
            self._eof = True
            self._read_error = "OSError on read"
            return b""
        if not chunk:  # EOF (BSD/mac)
            self._eof = True
            return b""
        return chunk

    def read_status(self) -> dict:
        """What can be said about the transport without reading it."""
        import select

        readable: bool | None
        if self._fd is None:
            readable = None
        else:
            try:
                readable = bool(select.select([self._fd], [], [], 0)[0])
            except Exception:
                readable = None
        return {
            "readable_now": readable,
            "eof": self._eof,
            "error": self._read_error,
            "queued_payload_bytes": None,      # the kernel pty buffer is not ours to measure
            "reader_held_payload_bytes": 0,
            "generation": self._generation,
        }

    #: Deadline for one ``write`` call, in seconds. A non-blocking fd that never
    #: becomes writable must fail the call rather than park the owner loop; the
    #: value is a bounded-wait policy, not a performance target.
    write_timeout: float = 5.0

    def _wait_writable(self, deadline: float, offset: int, total: int) -> None:
        """Wait for writability, bounded by ``deadline``.

        ``select.select`` is a syscall and can raise: EINTR means a signal arrived
        (retry the SAME suffix -- never a re-send from zero, which would duplicate
        bytes), and any other OSError must leave the receipt it earned, carrying
        how much of the payload had already been accepted.
        """
        import select
        import time

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise IncompleteWrite(offset, total, "deadline waiting for writability") from None
        try:
            # Spurious wakeups are allowed: the caller re-checks the same suffix.
            select.select([], [self._fd], [], min(remaining, 0.25))
        except InterruptedError:
            return                      # a signal during the wait: try again
        except OSError as exc:
            raise IncompleteWrite(offset, total,
                                  f"select failed: {type(exc).__name__}: {exc}") from exc

    def write(self, data: bytes) -> None:
        """Write every byte of ``data``, or raise :class:`IncompleteWrite`.

        The fd is non-blocking, so a single ``os.write`` may accept only a
        prefix; its return value was previously discarded, which reported success
        for input the child never received. This loop keeps an offset and only
        returns once every byte has been accepted, waiting for writability
        between attempts and honouring a deadline that is re-checked before EVERY
        write -- including the case where every call succeeds with one byte, which
        would otherwise run past the deadline unnoticed. ``EINTR`` retries the
        very same suffix, never a re-send of the whole payload, which would
        duplicate bytes already delivered.
        """
        import os
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
            if time.monotonic() >= deadline:
                # Checked here, not only in the no-progress branches: a trickling
                # writer makes progress on every call and would never reach them.
                raise IncompleteWrite(offset, total, "deadline before next write")
            try:
                written = os.write(self._fd, view[offset:])
            except InterruptedError:
                continue                     # same suffix; the loop re-checks the deadline
            except BlockingIOError:
                self._wait_writable(deadline, offset, total)
                continue
            except OSError as exc:
                # EPIPE/EIO/bad fd: the previously written prefix is still real,
                # so report the progress instead of pretending nothing landed.
                raise IncompleteWrite(offset, total,
                                      f"{type(exc).__name__}: {exc}") from exc
            if written <= 0:
                # No progress and no error: treat like EAGAIN rather than looping
                # hot on a descriptor that accepted nothing.
                self._wait_writable(deadline, offset, total)
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

    #: Close-protocol state (A04-S4). "The native call returned" is not "the child
    #: is gone": the two are reported separately so a receipt can never claim a
    #: confirmed close it did not observe.
    def close_state(self) -> dict:
        return {
            "close_requested": self._close_requested,
            "closing": self._closing,
            "closed_confirmed": self._closed_confirmed,
            "close_unconfirmed": self._close_unconfirmed,
            "output_eof": self._eof,
            "last_progress": self._last_close_progress,
            "generation": self._generation,
        }

    def terminate(self) -> None:
        import os
        import signal
        import time

        self._close_requested = True
        self._closing = True
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
            self._last_close_progress = ("reaped after SIGTERM" if reaped
                                         else "SIGTERM did not reap within 1.0s")
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
        if pid is not None:
            # Ask the kernel, do not assume: kill(pid, 0) succeeding means the pid
            # is still a live process (or a zombie we could not reap).
            self._closed_confirmed = _pid_is_gone(pid)
            self._close_unconfirmed = not self._closed_confirmed
            if self._close_unconfirmed:
                self._last_close_progress = (
                    f"pid {pid} still present after SIGTERM/SIGKILL window; "
                    "the kernel will reap it once it leaves an uninterruptible state")
        else:
            self._closed_confirmed = True
        self._closing = False
        self._pid = None
        self._fd = None


def get_default_backend() -> PtyBackend:
    """Return a backend appropriate for the current platform.

    Windows -> :class:`WinptyBackend`; everything else -> :class:`PosixPtyBackend`.
    """
    if sys.platform == "win32":
        return WinptyBackend()
    return PosixPtyBackend()
