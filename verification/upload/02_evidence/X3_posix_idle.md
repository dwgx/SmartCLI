# RUN/X3/last.md — POSIX idle progress and device replies measured in a container

Authorization: Owner-supplied Docker. Environment: `python:3.13-slim` on the Windows host's Docker
engine (29.7.2, linux), pyte 0.8.2, real `pty.fork()`; repository mounted at `/repo`.
One PTY per scenario, ≤1 MiB payload, ≤10 s, every session closed by the probe.

## Fixture

Child (`child_writer.py`): writes 512 KiB in 4 KiB steps, rewriting a JSON report **after every step**
(it is its own witness), then sends `ESC[6n` and waits ≤3 s for the terminal's answer.

Parent: scenario A never touches the session for 2 s; scenario B runs the owner loop
(`PtySession.pump()`) until the child reports done + CPR answered.

## Results

### A. Nobody polls (`pumped: false`, 2.0 s)

```json
{"written": 12288, "done": false, "cpr_answered": false, "steps": 3}
```

**The child stopped after 12 288 bytes and never completed.** That is the kernel pty buffer filling
with no reader on the master fd: on this host the effective limit is ~12 KiB of child output. The
device query is never answered either — the replies live in `pump()`.

### B. Owner loop runs (`pumped: true`, 0.957 s)

```json
{"written": 524288, "done": true, "blocked_at": 167936, "steps": 128,
 "cpr_answered": true, "cpr_reply": "\u001b[30;89R", "seconds": 0.926}
```

**All 512 KiB delivered, in 0.93 s, with the CPR query answered** (`ESC[30;89R` — the cursor report
pyte built from its own state). `blocked_at: 167936` shows the child did briefly hit the buffer limit
while the parent was between pump calls, and recovered.

Reading note: `parsed_chars: 3029` in both scenarios is the *visible screen* (30×100 + separators),
not the byte count — 512 KiB of dot-filled lines scroll away. It is not evidence of lost data.

## What this establishes

1. The A04-POSIX defect is **measured, not inferred**: without an owner-side read, a writing child
   stalls at ~12 KiB. Any design that only pumps on request cannot keep a busy session alive.
2. The same measurement pins the *floor* for the design's byte budgets: the kernel buffer here is
   ~12 KiB, so a 256 KiB ingress budget is a consumer-side budget, not a transport one.
3. Device replies (`ESC[6n`) ride the same path: they are emitted only when the owner drains, so
   "answer the program's queries" and "keep the child unblocked" are one mechanism, not two.

## Limits / NOT_RUN

`posix_idle_recovery_after_fix` — NOT_RUN: no A04 fix exists yet (the prototype was design-only), so
this is a **baseline**. `multi_watcher` — NOT_RUN: the public daemon still allows one long wait; the
existing fake-session concurrency test (`test_daemon_concurrency`, exit 0) is the current lock on the
fast-verb interleave. `windows_parity` — see `X2/last.md`. `commit` / `push` — NOT_CREATED /
NOT_REQUESTED.
