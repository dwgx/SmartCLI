"""A04-P reference model: one byte-budget contract, two platform shapes.

This is a MODEL, not a patch. It contains no thread, no socket, no PTY/ConPTY and
no process: the transport is a finite script, time is a virtual counter, and every
budget is an argument. Its purpose is to make the A04 design falsifiable -- each
invariant below has a matching negative control in test_prototype.py that breaks
the model in the way the real defect would break the daemon.

What it deliberately does NOT claim:
  * that the real Windows reader or POSIX backend behaves like this model;
  * that an infinitely fast producer can never block (backpressure is legal
    overload behaviour; silent stalling is not);
  * that the current daemon supports two independent long waits (it does not --
    a second long wait still queues).
"""
from __future__ import annotations

from collections import deque

# Design starting points from docs/A04_DESIGN.md, shrunk so every bound is
# reached inside a few iterations. They are budget values, not measurements.
DEFAULT_CAP = 12          # ingress payload cap (bytes)
DEFAULT_HIGH = 8          # pause reading at this high-water mark
DEFAULT_LOW = 4           # resume reading below this low-water mark
DEFAULT_FRAGMENT = 4      # largest single read/enqueue unit
DEFAULT_TURN = 8          # bytes one owner turn may parse
DEFAULT_INTERLEAVE_PER_TURN = 2


class Transport:
    """Finite scripted byte source standing in for a platform reader."""

    def __init__(self, fragments, replies=()):
        self._fragments = deque(fragments)
        self._replies = deque(replies)
        self.reads = 0
        self.bytes_read = 0
        self.max_read_size = 0

    def read(self, max_bytes: int) -> bytes:
        """Return at most ``max_bytes``; ``b""`` when the script is exhausted."""
        self.reads += 1
        if not self._fragments:
            return b""
        chunk = self._fragments[0][:max_bytes]
        self._fragments[0] = self._fragments[0][max_bytes:]
        if not self._fragments[0]:
            self._fragments.popleft()
        self.bytes_read += len(chunk)
        self.max_read_size = max(self.max_read_size, len(chunk))
        return chunk

    def take_reply(self) -> bytes:
        return self._replies.popleft() if self._replies else b""


class ByteQueue:
    """Byte-budgeted ingress: the only path from transport to the screen model.

    ``offer`` refuses bytes when full instead of growing: that refusal IS the
    backpressure signal the reader must wait on. A queue bounded by item count
    would not bound anything, since one item may be megabytes.
    """

    def __init__(self, cap: int, high: int, low: int):
        if not 0 < low <= high <= cap:
            raise ValueError("budgets must satisfy 0 < low <= high <= cap")
        self.cap, self.high, self.low = cap, high, low
        self._buf = bytearray()
        self.max_pending = 0
        self.backpressure_events = 0
        self.delivered = bytearray()

    def __len__(self) -> int:
        return len(self._buf)

    def offer(self, data: bytes) -> int:
        room = self.cap - len(self._buf)
        if room <= 0:
            self.backpressure_events += 1
            return 0
        n = min(room, len(data))
        self._buf += data[:n]
        self.max_pending = max(self.max_pending, len(self._buf))
        return n

    def take(self, n: int) -> bytes:
        chunk = bytes(self._buf[:n])
        del self._buf[:n]
        self.delivered += chunk
        return chunk

    def wants_more(self) -> bool:
        return len(self._buf) < self.high


class Reader:
    """Platform reader shape.

    ``mode="windows"`` -- output is already drained into this queue by an existing
    reader; the model only bounds it and adds stop-aware capacity waiting.
    ``mode="posix"`` -- nobody else reads the master fd, so the OWNER has to do it
    (see Owner.service_turn) or the child eventually blocks.
    """

    def __init__(self, transport: Transport, queue: ByteQueue, *, fragment: int, mode: str):
        if mode not in ("windows", "posix"):
            raise ValueError(mode)
        self.transport, self.queue, self.fragment, self.mode = transport, queue, fragment, mode
        self.waits = 0
        self.blocked_at_capacity = 0
        self.replies_sent = 0

    def pump(self, *, stop_aware: bool = True, max_offers: int = 8) -> int:
        """Move bytes transport -> queue, never blocking inside a native read."""
        moved = 0
        for _ in range(max_offers):
            if not self.queue.wants_more():
                self.blocked_at_capacity += 1
                if stop_aware:
                    self.waits += 1          # bounded wait, woken by the owner
                break
            chunk = self.transport.read(self.fragment)
            if not chunk:
                break
            n = self.queue.offer(chunk)
            moved += n
            if n < len(chunk):
                # Partial acceptance is backpressure, not permission to drop the
                # rest: the unaccepted tail must be re-offered, never discarded.
                self.transport._fragments.appendleft(chunk[n:])
                self.blocked_at_capacity += 1
                self.waits += 1
                break
        return moved


class Screen:
    """The screen model stand-in: fed by exactly one owner."""

    def __init__(self):
        self.text = bytearray()
        self.feed_revision = 0
        self.owner_ident = None
        self.feed_calls = 0

    def feed(self, chunk: bytes, owner: str = "owner") -> None:
        if self.owner_ident is not None and self.owner_ident != owner:
            raise AssertionError(f"screen mutated by {owner}, owned by {self.owner_ident}")
        self.owner_ident = owner
        self.text += chunk
        self.feed_revision += 1
        self.feed_calls += 1


class Control:
    """Session control: close/EOF travel beside the data queue, never inside it."""

    def __init__(self):
        self.state = "running"
        self.control_ticks_waiting = 0
        self.eof_observed = False
        self.unconfirmed = False

    def request_close(self, *, eof_via_data_queue: bool, queue: ByteQueue | None = None) -> None:
        self.state = "closing"
        if eof_via_data_queue and queue is not None:
            # The defect being modelled: an EOF sentinel queued behind data can
            # never be reached while the queue stays full.
            accepted = queue.offer(b"\x00EOF")
            if accepted < 5:
                self.control_ticks_waiting += 1
                return
        self.eof_observed = True

    def finish(self) -> None:
        self.state = "exited" if self.eof_observed else "close_unconfirmed"
        self.unconfirmed = not self.eof_observed


class Owner:
    """Single writer of the screen model. Every turn is budgeted."""

    def __init__(self, queue: ByteQueue, screen: Screen, *, turn_bytes: int, fragment: int,
                 reader: Reader | None = None, idle_service: bool = True,
                 interleave_limit: int = DEFAULT_INTERLEAVE_PER_TURN):
        self.queue, self.screen = queue, screen
        self.turn_bytes, self.fragment, self.reader = turn_bytes, fragment, reader
        self.idle_service = idle_service
        self.interleave_limit = interleave_limit
        self.turns = 0
        self.parsed_bytes = 0
        self.observed_revision = -1
        self.max_turn = 0
        self.serviced_without_job = 0

    # -- the one turn ----------------------------------------------------
    def service_turn(self, *, had_job: bool = False) -> int:
        """Read (posix) then parse, both bounded. Never re-enters the owner."""
        self.turns += 1
        if self.reader is not None and self.reader.mode == "posix":
            self.reader.pump(max_offers=1)
        used = 0
        while used < self.turn_bytes:
            chunk = self.queue.take(min(self.fragment, self.turn_bytes - used))
            if not chunk:
                break
            self.screen.feed(chunk)
            used += len(chunk)
        if self.reader is not None:
            reply = self.reader.transport.take_reply()
            if reply:
                # Device-query replies answer the child; they are not screen text
                # and are counted apart from parsed bytes.
                self.reader.replies_sent += 1
        self.parsed_bytes += used
        self.max_turn = max(self.max_turn, used)
        self.observed_revision = self.screen.feed_revision
        if not had_job:
            self.serviced_without_job += 1
        return used

    def service_turn_if_idle(self, *, had_job: bool) -> int:
        """Idle service: parse even when no client is waiting on this session."""
        if had_job or self.idle_service:
            return self.service_turn(had_job=had_job)
        return 0


class FastJob:
    def __init__(self, verb: str, tick: int):
        self.verb, self.arrival_tick, self.served_tick = verb, tick, None


class Daemon:
    """Queue of fast verbs + one optional long wait + resize attribution."""

    def __init__(self, owner: Owner, *, interleave: bool = True,
                 resize_counts_as_action: bool = False):
        self.owner = owner
        self.interleave = interleave
        self.resize_counts_as_action = resize_counts_as_action
        self.pending: deque[FastJob] = deque()
        self.deferred: list[FastJob] = []
        self.resizes = 0
        self.geometry_epoch = 0

    def submit(self, job: FastJob) -> None:
        self.pending.append(job)

    def drain_interleavable(self, tick: int) -> int:
        """Answer fast verbs inside a running wait's poll gap (bounded)."""
        served = 0
        for _ in range(self.owner.interleave_limit):
            if not self.pending:
                break
            job = self.pending.popleft()
            if job.verb in ("snapshot", "alive", "send_text"):
                job.served_tick = tick
                served += 1
            else:
                self.deferred.append(job)     # e.g. a second long wait: stays queued
        return served

    def resize(self, *, during_action_wait: bool = False) -> None:
        self.resizes += 1
        self.geometry_epoch += 1
        self._resize_during_action_wait = during_action_wait

    def action_wait(self, *, want_payload: bytes, deadline: int, start_tick: int) -> dict:
        """Wait for the action's own output; resize must not satisfy it."""
        tick = start_tick
        satisfied_by = None
        while tick < deadline:
            self.owner.service_turn_if_idle(had_job=True)
            if self.interleave:
                self.drain_interleavable(tick)
            if want_payload and want_payload in bytes(self.owner.screen.text):
                satisfied_by = "payload"
                break
            if self.resize_counts_as_action and self.geometry_epoch:
                satisfied_by = "resize"       # the causality violation being modelled
                break
            tick += 1
        return {"tick": tick, "satisfied_by": satisfied_by}


class Observer:
    """A read-only predicate. Observers never touch the transport."""

    def __init__(self, name: str, predicate):
        self.name, self.predicate = name, predicate
        self.transport_reads = 0
        self.last_revision = -1
        self.matched = False
        self.evaluations = 0

    def evaluate(self, owner: Owner, screen: Screen, *, read_transport: bool = False) -> bool:
        if read_transport:
            self.transport_reads += 1          # the defect: a competing reader
        self.evaluations += 1
        self.last_revision = screen.feed_revision
        self.matched = bool(self.predicate(bytes(screen.text)))
        return self.matched


def drive(session, ticks: int) -> None:
    """Idle loop: parse without waiting for a client, with a bounded wake budget."""
    for _ in range(ticks):
        session["owner"].service_turn_if_idle(had_job=False)
        if session["control"].state != "running":
            break
