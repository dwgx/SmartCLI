# A04-P DESIGN_DELTA — symbol-level migration proposal (NOT authorized)

Status: proposal only. The prototype brief authorizes **zero** repository files; nothing
in this document is implemented. Evidence for the model: `prototype.py` +
`test_prototype.py` (17 tests, 17 negative/positive controls, E2-reference-model),
run from `D:/Project/SmartCLI-v2-runs/A04-P`.

## 1. What the model demonstrates, and only that

| Model invariant | Negative control that breaks it | Production mechanism it stands for |
|---|---|---|
| Pending payload never exceeds a byte cap; the reader pauses at the high-water mark and refuses at the cap | unbounded queue+watermark → `max_pending` grows past the design cap | replace `queue.Queue()` (unbounded, item-counted) in `WinptyBackend` with a byte-budgeted buffer |
| The refused tail is re-offered after a drain (no byte is dropped or duplicated) | partial acceptance without re-offer would lose the tail | `read_nonblocking`/`_read_loop` must keep the unaccepted suffix, not discard it |
| One owner turn parses at most N bytes in fragments of ≤4 KiB | a turn without a budget parses everything it finds | `PtySession.pump` needs an optional byte budget |
| The POSIX owner consumes the master fd while idle, and answers device queries then | idle service off → a finite fixture never completes without a client polling | `tui._serve_forever`'s worker currently `continue`s on `queue.Empty` without `sess.pump()` |
| Close/EOF travel beside the data queue | EOF queued behind a full data queue → `close_unconfirmed` forever | control/close must not be an item inside the data queue |
| Fast verbs are answered inside a long wait's poll gap, bounded per turn | interleave off → the fast request waits for the whole wait | the existing `INTERLEAVE_OK` + `_drain_interleavable` must be preserved, with a per-turn job budget |
| Resize never satisfies an action-specific wait | resize counted as an action → recovery cause misattributed | keep the documented `resize` exclusion from the legacy wait path |
| Two read-only observers judge one committed revision; neither reads transport | an observer that reads the transport is detectable in the model | multi-watcher reads committed observations only; the daemon does **not** yet support two independent long waits |

Two facts the model must not be read as proving: it says nothing about Windows
`pywinpty.read` returning `str` (the wire bytes are not recoverable, so `wire_exact` does
not hold there), and nothing about real scheduling, RSS, or latency. Those need the
owner-approved X2/X3 runs.

## 2. Future symbols, with the change each needs

| Symbol | Today (E1, source-read) | Proposed |
|---|---|---|
| `WinptyBackend._read_loop` | blocking `proc.read(65536)` → unbounded `self._queue` | keep the reader thread; write into a byte-budgeted buffer; wait stop-aware when full instead of growing; hold the spawn's queue/proc/generation instead of re-reading `self.*` |
| `WinptyBackend.read_nonblocking` | drains the queue until empty | accept an optional byte budget; return the unparsed remainder accounting |
| `PosixPtyBackend.read_nonblocking` | `select` + drain-until-empty loop | optional byte budget (a budget-truncated read must not be mistaken for a stable screen) |
| `PtySession.pump` | read → `feed` → `drain_replies` → `write(reply)` | optional budget; keep the reply path and its ordering; expose pending/backlog so readiness can tell "quiet" from "not yet read" |
| `tui._serve_forever` worker | `jobs.get(timeout=0.2)` → `continue` (no pump while idle) | one bounded `service_io()` per idle turn that reads (POSIX) and parses; never re-enter the owner from inside a wait |
| `tui._handle` / `on_poll` route | long waits call `read_fn` and drain interleaved fast verbs | same route, with an explicit per-turn job budget so a flood of fast requests cannot consume the poll gap |
| `tui._reply` | `sendall` on the worker thread, `POST_AUTH_TIMEOUT = 60.0` | unchanged this round; recorded as **A06** — a slow peer can still stall the single worker for up to 60 s |

Explicitly out of scope here: a second long wait (still queued), a generic actor
framework, and any claim that ingress budgeting alone gives total fairness.

## 3. Proposed production slice (needs its own approval)

Suggested maximum touch: 7 files, and it should be split further if possible.

1. `smartcli_core/pty_backend.py` — byte-budgeted reader buffer + stop-aware wait
   (Windows), optional read budget (POSIX), refused-tail retention.
2. `smartcli_core/session.py` — `pump(budget=...)`, backlog/pending accessor.
3. `skills/drive-tui/scripts/tui.py` — idle `service_io()` turn + per-turn interleave budget.
4. `skills/drive-tui/_vendor/smartcli_core/{pty_backend,session}.py` — generated twins.
5. `tests/test_a04_idle_service.py` — loopback/fake-backend: no client polling, bounded
   turn, backpressure, close-not-behind-data, interleave preserved, resize excluded.
6. `tests/test_a04_budget_invariants.py` — byte-cap and never-drop invariants under a
   hostile producer.

Remaining risks to keep listed as open: `_reply`'s 60 s worker stall and the unbounded
`jobs`/`readers` structures (**A05/A06**), the Windows `str` re-encoding (no byte-exact
claim), and readiness treating a budget-truncated read as a stable screen.

## 4. Open questions for the owner / next model

1. Should the POSIX budget apply to `read_nonblocking` (transport-level) or only to
   `pump` (consumer-level)? A transport budget changes what "no more data" means for
   readiness and therefore needs the pending/backlog signal first.
2. Is a byte cap the right unit for the Windows path, where `pywinpty.read` returns
   `str`? The cap must be applied to the *re-encoded* payload and reported as such.
3. What is the close policy when the reader cannot be interrupted mid-`read`? The model
   requires a bounded wait plus an explicit `close_unconfirmed`, not a silent success.
