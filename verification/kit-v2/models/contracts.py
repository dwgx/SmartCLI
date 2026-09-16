"""Executable design models, not a SmartCLI implementation or a PTY emulator.

All I/O is injected. Passing these tests is E2 model evidence, never native evidence.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass, replace
from typing import Callable


@dataclass(frozen=True)
class InputProgress:
    action_id: str
    generation: str
    total_bytes: int
    written_bytes: int = 0
    outcome: str = "pending"
    app_ack: str = "unknown"
    verification: str = "not_run"
    cancellation_too_late: bool = False
    verification_evidence_id: str | None = None

    def __post_init__(self) -> None:
        if not self.action_id or not self.generation:
            raise ValueError("action and generation must be explicit")
        if not 0 <= self.written_bytes <= self.total_bytes:
            raise ValueError("invalid byte accounting")

    @property
    def write_state(self) -> str:
        if self.written_bytes == self.total_bytes:
            return "written"
        return "partially_written" if self.written_bytes else "accepted"

    @property
    def phase(self) -> str:
        if self.verification == "passed":
            return "verified"
        if self.app_ack == "acknowledged":
            return "app_acknowledged"
        return self.write_state

    def advance(self, n: int) -> InputProgress:
        if self.outcome != "pending" or n <= 0:
            raise ValueError("no write after terminal result or without progress")
        return replace(self, written_bytes=self.written_bytes + n)

    def stop(self, reason: str) -> InputProgress:
        if reason not in {"cancelled", "timeout", "failed"}:
            raise ValueError("unknown stop reason")
        if self.outcome != "pending":
            return self
        if self.write_state == "written":
            return replace(self, cancellation_too_late=(reason == "cancelled"))
        return replace(self, outcome=reason)

    def acknowledge(self, action_id: str, generation: str, status: str) -> InputProgress:
        if (action_id, generation) != (self.action_id, self.generation):
            raise ValueError("stale or unrelated ACK")
        if self.write_state != "written" or status not in {"acknowledged", "ignored"}:
            raise ValueError("ACK lacks completed transport or has invalid status")
        return replace(self, app_ack=status)

    def verify(self, passed: bool, evidence_id: str) -> InputProgress:
        if self.write_state != "written" or not evidence_id:
            raise ValueError("verification needs transport completion and evidence")
        # Deliberately does not manufacture an application ACK.
        return replace(self, verification="passed" if passed else "failed", verification_evidence_id=evidence_id)


class IncompleteWrite(OSError):
    def __init__(self, progress: InputProgress):
        super().__init__(f"{progress.outcome}: {progress.written_bytes}/{progress.total_bytes}")
        self.progress = progress


def write_all_reference(
    payload: bytes,
    write: Callable[[bytes], int],
    wait_writable: Callable[[float], None],
    clock: Callable[[], float],
    deadline: float,
    cancelled: Callable[[], bool] = lambda: False,
    *,
    max_attempts: int = 64,
) -> InputProgress:
    """Bounded demonstrator for injected transports; not production scheduling."""
    progress = InputProgress("model-action", "model-generation", len(payload))
    attempts = 0
    def wait_with_progress() -> None:
        try:
            wait_writable(max(0.0, deadline - clock()))
        except InterruptedError:
            return  # the outer loop checks cancellation and deadline again
        except OSError as exc:
            raise IncompleteWrite(progress.stop("failed")) from exc
    while progress.write_state != "written":
        if cancelled():
            raise IncompleteWrite(progress.stop("cancelled"))
        if clock() >= deadline:
            raise IncompleteWrite(progress.stop("timeout"))
        attempts += 1
        if attempts > max_attempts:
            raise IncompleteWrite(progress.stop("failed"))
        try:
            count = write(payload[progress.written_bytes:])
        except InterruptedError:
            continue
        except BlockingIOError:
            wait_with_progress()
            continue
        except OSError as exc:
            raise IncompleteWrite(progress.stop("failed")) from exc
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise IncompleteWrite(progress.stop("failed"))
        if count > progress.total_bytes - progress.written_bytes:
            raise IncompleteWrite(progress.stop("failed"))
        if count == 0:
            wait_with_progress()
            continue
        progress = progress.advance(count)
    return progress


class BudgetBuffer:
    """Non-threaded bounded payload model. An offer is all-or-nothing."""
    def __init__(self, capacity: int, max_fragment: int):
        if not 0 < max_fragment <= capacity:
            raise ValueError("invalid budget")
        self.capacity = capacity
        self.max_fragment = max_fragment
        self.pending_bytes = 0
        self.max_seen = 0
        self.eof = False
        self.closing = False
        self._chunks: deque[bytes] = deque()

    def offer(self, data: bytes) -> bool:
        if self.eof:
            raise RuntimeError("new bytes after EOF")
        if not isinstance(data, bytes) or not 0 < len(data) <= self.max_fragment:
            raise ValueError("fragment must be bounded nonempty bytes")
        if len(data) > self.capacity - self.pending_bytes:
            return False  # caller retains ownership; this is not a silent drop
        self._chunks.append(data)
        self.pending_bytes += len(data)
        self.max_seen = max(self.max_seen, self.pending_bytes)
        return True

    def consume(self, budget: int) -> bytes:
        if budget <= 0:
            raise ValueError("budget must be positive")
        parts = []
        remaining = budget
        while self._chunks and remaining:
            chunk = self._chunks.popleft()
            head, tail = chunk[:remaining], chunk[remaining:]
            parts.append(head)
            remaining -= len(head)
            self.pending_bytes -= len(head)
            if tail:
                self._chunks.appendleft(tail)
        return b"".join(parts)

    def signal_eof(self) -> None:
        self.eof = True  # not queued behind bytes; consumes no data capacity

    def begin_close(self) -> None:
        # This is a close REQUEST, not transport EOF. A native close may emit
        # final output, so ingress remains open until signal_eof(). A real
        # transport needs a separate bounded close deadline and wake mechanism.
        self.closing = True

    @property
    def drained(self) -> bool:
        return self.eof and self.pending_bytes == 0


def accept_completion_claim(basis: str, requested: str, evidence_id: str | None = None) -> bool:
    """A model oracle: an idle observation is not a command result."""
    if requested == "state_matches":
        return basis == "rendered_text_regex"
    if requested == "command_finished":
        return basis in {"shell_completion", "process_exit"} and bool(evidence_id)
    if requested == "verified":
        return basis == "independent_verifier" and bool(evidence_id)
    return False
